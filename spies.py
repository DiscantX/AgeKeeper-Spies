from pathlib import Path                            #Creating path objects
from windows_toasts import (                        #Creating the Windows toasts
    InteractableWindowsToaster,
    Toast,
    ToastAudio,
    ToastDisplayImage,
    ToastImagePosition,
    ToastScenario,
    ToastActivatedEventArgs,
    ToastDismissedEventArgs,
    ToastFailedEventArgs,
)
import asyncio                                      #Asyncronous functions
import time                                         #Getting/parsing current time
from functools import partial                       #Passing extra params to callback
from webbrowser import open_new as web_open         #Opening protocol link

from lobby import lobby
from lobby.match_book import MatchBook
from lobby.utils import extract_player_status_update
from spies.watchlist import DEFAULT_AVATAR_PATH, Watchlist
from spies.avatar import (
    add_player_avatar_to_toast,
    resolve_avatar_filepath
    )
from spies.audio import play_alert_audio
from spies.toast_queue import ToastQueueManager

# Assign default variables
default_avatar_path = DEFAULT_AVATAR_PATH
PROJECT_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
SPIES_ASSETS_DIR = Path(__file__).resolve().parent / "assets"

# Instantiate the toast & toaster objects for later use
toaster = InteractableWindowsToaster("AOE2: Spies")
spyToast = Toast("Spy Alert")

# Instantiate the player watchlist object
watchlist = Watchlist()

#Instantiate the MatchBooks, which will store current matches/lobbies
lobby_matches = MatchBook("lobby")
spectate_matches = MatchBook("spectate")

def activated_callback(activatedEventArgs: ToastActivatedEventArgs, short_response_type: str, match_id: str):
    """Open AoE2 with the selected lobby/spectate target when toast is clicked."""
    print(f"Toast activated for {short_response_type} with Match ID: {match_id}")
    match short_response_type:
        case "lobby":
            response_type_id = 0
        case "spectate":
            response_type_id = 1
        case _:
            print("Unknown response type, cannot open game.")
            return
    protocol_link = f"aoe2de://{response_type_id}/{match_id}"
    response = web_open(protocol_link)
    print(f"Opened {protocol_link} with response: {response}")

def dismissed_callback(dismissedEventArgs: ToastDismissedEventArgs):
    """Handle toast dismissal and clean up the temporary avatar image."""
    dismissal_reasons = {
        0: "UserCanceled",
        1: "ApplicationHidden",
        2: "TimedOut",
    }
    reason = dismissedEventArgs.reason
    reason_value = int(reason)
    reason_name = dismissal_reasons.get(reason_value, str(reason))
    print(f"Toast dismissed reason: {reason_name} ({reason_value})")

def failed_callback(failedEventArgs: ToastFailedEventArgs):
    """Log toast delivery failures reported by the Windows toast API."""
    print(f"Toast failed: {failedEventArgs.reason}")

def display_toast(player_name: str, match, status: str, avatar_filepath: str = default_avatar_path):
    """Build and display a spy alert toast with map, civ, and avatar details."""
    # Register toast callbacks
    spyToast.on_activated = partial(activated_callback, status=status, match_id=match.get("matchid", -1), )
    spyToast.on_dismissed = dismissed_callback
    spyToast.on_failed = failed_callback
    
    # Causes toast to not timeout by mimicking an incoming call
    # TODO/BUG: The toast sometimes does not receive the click that triggers the activated callback.
    # May not be related to this specific line, but rather something with the focus of the toast.
    # Could be an outside issue. Need further investigation.
    spyToast.scenario = ToastScenario.IncomingCall
    
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
    spyToast.text_fields = toast_fields
    banner_path = PROJECT_ASSETS_DIR / "AgeKeeperBanner_Cropped.png"
    audio_path = SPIES_ASSETS_DIR / "16_enemy_sighted.mp3"
    spyToast.AddImage(
        ToastDisplayImage.fromPath(
            str(banner_path),
            position=ToastImagePosition.Hero,
        )
    )
    add_player_avatar_to_toast(spyToast, avatar_filepath)
    # Disable native toast audio to avoid the default Windows ding.
    # We play our custom alert explicitly right after showing the toast.
    # BUG: The built in ToastAudio was not playing the .mp3 file for some reason,
    # so instead we play the audio file ourselves.
    spyToast.audio = ToastAudio(silent=True)
    toaster.show_toast(spyToast)
    play_alert_audio(audio_path)

    # Print alert info to console
    print("\nNew Spy Alert:")
    print("=" * 40)
    print("\n".join(toast_fields))
    print(f"Start time: {time.ctime(time.time())}\n")

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
    print(f"{player_name}'s status: {status}, matchid: {match_id}")


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
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
