"""Main runtime for the Spies watcher service.

Coordinates watchlist monitoring, lobby/spectate match tracking, toast payload
construction, alert delivery, and startup/CLI behavior.
"""

from pathlib import Path                            #Creating path objects
import os
import sys
from windows_toasts import (                        #Creating the Windows toasts
    InteractableWindowsToaster,
    Toast,
    ToastAudio,
    ToastDuration,
    ToastDisplayImage,
    ToastImagePosition,
)
import asyncio                                      #Asyncronous functions
import time                                         #Getting/parsing current time
from functools import partial

# Allow running this file directly (e.g., via pythonw spies/spies.py).
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.chdir(Path(__file__).resolve().parent.parent)

from lobby import lobby
from lobby.match_book import MatchBook
from lobby.utils import extract_player_status_update
from spies.watchlist import DEFAULT_AVATAR_PATH, Watchlist
from spies.avatar import (
    add_player_avatar_to_toast,
    resolve_avatar_filepath
    )
from spies.audio import play_alert_audio
from spies.cli import build_cli_parser, handle_task_cli
from shared.process_guard import acquire_single_instance_lock
from spies.toast_queue import ToastQueueManager
from spies.logging_utils import configure_rotating_logger, resolve_log_file, tail_logs
from spies.toast_handlers import (
    configure_toast_launch_action,
    log_toast_dismissal,
    log_toast_failure,
)

# Assign default variables
default_avatar_path = DEFAULT_AVATAR_PATH
PROJECT_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
SPIES_ASSETS_DIR = Path(__file__).resolve().parent / "assets"
SPIES_LOG_FILE = resolve_log_file()

# Set logger 
logger, SPIES_LOG_FILE = configure_rotating_logger(
    logger_name="agekeeper.spies",
    preferred_log_file=SPIES_LOG_FILE,
    fallback_log_file=Path(__file__).resolve().parent / "logs" / "spies.log",
)

# Instantiate the toaster object for later use
toaster = InteractableWindowsToaster("AOE2: Spies")

# Instantiate the player watchlist object
watchlist = Watchlist()

# Instantiation happens in main_async().
toast_queue_manager = None

def _log_player_status_update(player_id: str, status: str, match_id) -> None:
    """Log one incoming player status update."""
    player_entry = watchlist.get_entry(player_id, {})
    player_name = player_entry.get("userName") or str(player_id)
    logger.info("%s's status: %s, matchid: %s", player_name, status, match_id)

def _build_toast_payload(player_id: str, match, status: str, match_id):
    """Create payload data used by the toast queue worker."""
    player_entry = watchlist.get_entry(player_id, {})
    player_name = player_entry.get("userName") or str(player_id)
    avatar_filepath = resolve_avatar_filepath(
        player_entry, match, watchlist.by_id, watchlist.save_index
    )
    return {
        "player_name": player_name,
        "match": match,
        "status": status,
        "avatar_filepath": avatar_filepath,
    }

def _display_toast_payload(payload) -> None:
    """Render one queued payload as a Windows toast."""
    display_toast(
        player_name=payload["player_name"],
        match=payload["match"],
        status=payload["status"],
        avatar_filepath=payload["avatar_filepath"],
    )

def display_toast(
    player_name: str,
    match,
    status: str,
    avatar_filepath: str = default_avatar_path,
    left_match: bool = False,
):
    """Build and display a spy alert toast with map, civ, and avatar details."""
    spy_toast = Toast("Spy Alert")
    configure_toast_launch_action(spy_toast, status, match, logger)

    # Register toast callbacks
    spy_toast.on_dismissed = partial(log_toast_dismissal, logger=logger)
    spy_toast.on_failed = partial(log_toast_failure, logger=logger)
    
    # Ser toast duration so they display for a long time
    spy_toast.duration = ToastDuration.Long
    
    # Prepare all of the required data that will be used when displaying the toast
    player_data = lobby.get_player_slot(player_name, match)
    if player_data:
        player_civ_name = lobby.get_civ_name(player_data.get("civilization", -1))
    else:
        player_civ_name = "Player Unavailable"

    created_time = match.get("created_time", int(time.time()))
    match_time_alive = int(time.time()) - created_time
    subscription_description = "Unknown"
    match status:
        case "lobby":
            subscription_description = "lobby"
        case "spectate":
            subscription_description = "game"
            
    activity_text = (
        f"{player_name[:25]} left {subscription_description}:\n"
        f"{match.get('description', f'a {subscription_description}')}"
        if left_match
        else f"{player_name[:25]} is in {subscription_description}:\n"
        f"{match.get('description', f'a {subscription_description}')}"
    )
    toast_fields = [
        activity_text,
        f"Map: {match.get('map_name', 'Unknown Map')} | Playing as: {player_civ_name}",
        f"Started: {match_time_alive}s ago | {match.get('slots_taken', -1)} Player{'s' if match.get('slots_taken', -1) != 1 else ''} in {subscription_description}",
    ]
    
    #Attach the data that is to be displayed to the toast
    spy_toast.text_fields = toast_fields
    banner_path = PROJECT_ASSETS_DIR / "AgeKeeperBanner_Cropped.png"
    audio_path = SPIES_ASSETS_DIR / "16_enemy_sighted.mp3"
    spy_toast.AddImage(
        ToastDisplayImage.fromPath(
            str(banner_path),
            position=ToastImagePosition.Hero,
        )
    )
    add_player_avatar_to_toast(spy_toast, avatar_filepath)
    # Disable native toast audio to avoid the default Windows ding.
    # We play our custom alert explicitly right after showing the toast.
    # BUG: The built in ToastAudio was not playing the .mp3 file for some reason,
    # so instead we play the audio file ourselves.
    spy_toast.audio = ToastAudio(silent=True)
    toaster.show_toast(spy_toast)
    play_alert_audio(audio_path)

    logger.info("New Spy Alert\n%s\n%s\nStart time: %s", "=" * 40, "\n".join(toast_fields), time.ctime(time.time()))

def _handle_matchbook_player_remove(player_id: str, status: str, match_id, match) -> None:
    if watchlist.get_entry(player_id) is None:
        return

    payload = _build_toast_payload(player_id, match, status, match_id)
    if not payload:
        return

    _log_player_status_update(player_id, f"left_{status}", match_id)
    display_toast(
        player_name=payload["player_name"],
        match=payload["match"],
        status=payload["status"],
        avatar_filepath=payload["avatar_filepath"],
        left_match=True,
    )

def spy(event, **kwargs):
    """Dispatch incoming subscription events to the relevant spy handlers."""
    response_type = lobby.get_response_type(event)
    match response_type:
        case "player_status":
            # Fast-path for the only response type currently used by this module.
            parsed_status = extract_player_status_update(event)
            if parsed_status is None:
                return
            player_id, status, match_id = parsed_status
            MatchBook.resolve_pending_lobby_leave_from_player_status(player_id, status, match_id)
            toast_queue_manager.handle_player_status_update(player_id, status, match_id)

async def main_async():
    """Initialize state, subscribe to watchlist players, and run indefinitely."""
    # Instantiate MatchBook instances.
    lobby_matches = MatchBook("lobby", on_player_remove=_handle_matchbook_player_remove)
    spectate_matches = MatchBook("spectate", on_player_remove=_handle_matchbook_player_remove)

    def get_match_from_book(status: str, match_id, print_match_count: bool = False):
        """Return a match by id from the status-specific match book."""
        if status == "lobby":
            match_book = lobby_matches
        elif status == "spectate":
            match_book = spectate_matches
        else:
            return None
        if print_match_count:
            match_book.print_number_of_matches()
        return match_book.get_match_by_id(match_id)

    global toast_queue_manager
    toast_queue_manager = ToastQueueManager(
        get_match=get_match_from_book,
        build_toast_payload=_build_toast_payload,
        display_payload=_display_toast_payload,
        status_logger=_log_player_status_update,
    )

    # Start the MatchBook instances. This will cause them to connect to their subscriptions
    # and begin updating their internal lists of matches.
    lobby_matches.start()
    spectate_matches.start()
    
    # Load and index the list of players to watch from watchlist.json.
    watchlist.load_index()
    profile_ids = watchlist.get_profile_ids()
    if not profile_ids:
        return

    # Start the toast queue worker before subscription events begin arriving.
    toast_queue_manager.start()
    
    # Subscribe to the "players" subscription. This allows us to see when a player's status
    # has changed. Subscriptions to "lobby" and "spectate" have already occurred when their
    # MatchBook(s) were instantiated, so no need to do it again.
    subscriptions = lobby.subscribe(["players"], player_ids=profile_ids)
    lobby.connect_to_subscriptions(subscriptions, spy, create_task=True)
    
    # Keep the async process alive indefinitely.
    try:
        await asyncio.Event().wait()
    finally:
        await toast_queue_manager.stop()
    
def main():
    """Program entry point for running the spies event loop."""
    # Check for other instances running. Not strictly necessary,
    # but useful when running in background.
    if not acquire_single_instance_lock("AgeKeeper.Spies"):
        logger.warning("Another Spies instance is already running. Exiting.")
        return
    logger.info(f"{time.ctime(time.time())} | Starting spies process. Log file: {SPIES_LOG_FILE}")
    
    # Run the main async process
    asyncio.run(main_async())

if __name__ == "__main__":
    # CLI handling
    cli_args = build_cli_parser().parse_args()
    task_cli_result = handle_task_cli(cli_args)
    if task_cli_result is not None:
        raise SystemExit(task_cli_result)
    
    # Rather than run the main_async process, tail (display) the log file.
    # Most useful for when a seperate process is already running the script.
    if cli_args.tail_logs:
        raise SystemExit(
            tail_logs(
                log_file=SPIES_LOG_FILE,
                lines=cli_args.tail_lines,
                follow=not cli_args.no_follow,
            )
        )
    main()
