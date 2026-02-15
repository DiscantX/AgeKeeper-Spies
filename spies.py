from pathlib import Path                            #Creating path objects
import os
import sys
import argparse
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
from spies import task_registration
from shared.process_guard import acquire_single_instance_lock
from spies.toast_queue import ToastQueueManager
from spies.logging_utils import configure_rotating_logger, resolve_log_file, tail_logs
from spies.toast_handlers import log_toast_dismissal, log_toast_failure

# Assign default variables
default_avatar_path = DEFAULT_AVATAR_PATH
PROJECT_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
SPIES_ASSETS_DIR = Path(__file__).resolve().parent / "assets"

SPIES_LOG_FILE = resolve_log_file()


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgeKeeper spies runner.")
    parser.add_argument(
        "--tail-logs",
        action="store_true",
        help="Tail the spies log file instead of starting the spies process.",
    )
    parser.add_argument(
        "--tail-lines",
        type=int,
        default=100,
        help="How many recent lines to print before following logs (default: 100).",
    )
    parser.add_argument(
        "--no-follow",
        action="store_true",
        help="When used with --tail-logs, print lines and exit without follow mode.",
    )
    parser.add_argument(
        "--task-register",
        action="store_true",
        help="Register spies as a Windows Scheduled Task (headless startup).",
    )
    parser.add_argument(
        "--task-deregister",
        action="store_true",
        help="Remove the scheduled task registration.",
    )
    parser.add_argument(
        "--task-status",
        action="store_true",
        help="Show scheduled task status.",
    )
    parser.add_argument(
        "--task-start",
        action="store_true",
        help="Start the scheduled task now.",
    )
    parser.add_argument(
        "--task-stop",
        action="store_true",
        help="Stop the scheduled task if it is running.",
    )
    parser.add_argument(
        "--task-name",
        default=task_registration.DEFAULT_TASK_NAME,
        help=f"Scheduled task name (default: {task_registration.DEFAULT_TASK_NAME}).",
    )
    parser.add_argument(
        "--task-python",
        default=task_registration._default_pythonw(),
        help="Python executable used for task registration (default: pythonw when available).",
    )
    return parser


def _handle_task_cli(cli_args) -> int | None:
    actions = [
        cli_args.task_register,
        cli_args.task_deregister,
        cli_args.task_status,
        cli_args.task_start,
        cli_args.task_stop,
    ]
    selected = sum(bool(action) for action in actions)
    if selected == 0:
        return None
    if selected > 1:
        print(
            "Choose only one task action: --task-register, --task-deregister, "
            "--task-status, --task-start, --task-stop"
        )
        return 2

    if cli_args.task_register:
        return task_registration.register_task(
            task_name=cli_args.task_name,
            python_exe=cli_args.task_python,
        )
    if cli_args.task_deregister:
        return task_registration.deregister_task(task_name=cli_args.task_name)
    if cli_args.task_start:
        return task_registration.start_task(task_name=cli_args.task_name)
    if cli_args.task_stop:
        return task_registration.stop_task(task_name=cli_args.task_name)
    return task_registration.show_status(task_name=cli_args.task_name)


logger, SPIES_LOG_FILE = configure_rotating_logger(
    logger_name="agekeeper.spies",
    preferred_log_file=SPIES_LOG_FILE,
    fallback_log_file=Path(__file__).resolve().parent / "logs" / "spies.log",
)

# Instantiate the toaster object for later use
toaster = InteractableWindowsToaster("AOE2: Spies")

# Instantiate the player watchlist object
watchlist = Watchlist()

#Instantiate the MatchBooks, which will store current matches/lobbies
lobby_matches = MatchBook("lobby")
spectate_matches = MatchBook("spectate")

def display_toast(player_name: str, match, status: str, avatar_filepath: str = default_avatar_path):
    """Build and display a spy alert toast with map, civ, and avatar details."""
    spy_toast = Toast("Spy Alert")
    match status:
        case "lobby":
            response_type_id = 0
        case "spectate":
            response_type_id = 1
        case _:
            logger.warning("Unknown response type %s, cannot configure toast activation.", status)
            response_type_id = None

    if response_type_id is not None:
        match_id = match.get("matchid", -1)
        protocol_link = f"aoe2de://{response_type_id}/{match_id}"
        # Use protocol launch on the toast itself to avoid intermittent WinRT callback drops.
        spy_toast.launch_action = protocol_link
        logger.info("Toast launch action configured: %s", protocol_link)

    # Register toast callbacks
    spy_toast.on_dismissed = partial(log_toast_dismissal, logger=logger)
    spy_toast.on_failed = partial(log_toast_failure, logger=logger)
    
    # Prefer standard long-duration toasts over IncomingCall scenario; this is
    # more reliable for repeated click activation behavior.
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
            
    toast_fields = [
        f"{player_name[:25]} is in {subscription_description}:\n{match.get('description', f'a {subscription_description}')}",
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

def _get_match_from_book(status: str, match_id, print_match_count: bool = False):
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


def _log_player_status_update(player_id: str, status: str, match_id) -> None:
    """Log one incoming player status update."""
    player_entry = watchlist.get_entry(player_id, {})
    player_name = player_entry.get("userName") or str(player_id)
    logger.info("%s's status: %s, matchid: %s", player_name, status, match_id)


toast_queue_manager = ToastQueueManager(
    get_match=_get_match_from_book,
    build_toast_payload=_build_toast_payload,
    display_payload=_display_toast_payload,
    status_logger=_log_player_status_update,
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
            toast_queue_manager.handle_player_status_update(player_id, status, match_id)

async def main_async():
    """Initialize state, subscribe to watchlist players, and run indefinitely."""
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
    # but can help when running in background.
    if not acquire_single_instance_lock("AgeKeeper.Spies"):
        logger.warning("Another Spies instance is already running. Exiting.")
        return
    logger.info(f"{time.ctime(time.time())} | Starting spies process. Log file: {SPIES_LOG_FILE}")
    asyncio.run(main_async())

if __name__ == "__main__":
    cli_args = build_cli_parser().parse_args()
    task_cli_result = _handle_task_cli(cli_args)
    if task_cli_result is not None:
        raise SystemExit(task_cli_result)
    if cli_args.tail_logs:
        raise SystemExit(
            tail_logs(
                log_file=SPIES_LOG_FILE,
                lines=cli_args.tail_lines,
                follow=not cli_args.no_follow,
            )
        )
    main()
