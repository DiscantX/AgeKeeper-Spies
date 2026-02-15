from pathlib import Path
from windows_toasts import (
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
import asyncio
import time
from functools import partial
from webbrowser import open_new as web_open

from lobby import lobby
from lobby.match_book import MatchBook
from spies.watchlist import DEFAULT_AVATAR_PATH, Watchlist
from spies.avatar import add_player_avatar_to_toast, resolve_avatar_filepath, remove_image
from spies.audio import play_alert_audio

# Assign default variables
default_avatar_path = DEFAULT_AVATAR_PATH
PROJECT_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
SPIES_ASSETS_DIR = Path(__file__).resolve().parent / "assets"

# Create the toast/toaster objects for later use
toaster = InteractableWindowsToaster("AOE2: Spies")
spyToast = Toast("Spy Alert")

watchlist = Watchlist()

lobby_matches = MatchBook("lobby")
spectate_matches = MatchBook("spectate")
toast_queue = asyncio.Queue()
pending_wait_tasks = {}
toast_status_by_key = {}

def activated_callback(
    activatedEventArgs: ToastActivatedEventArgs, short_response_type: str, match_id: str
):
    """Open AoE2 with the selected lobby/spectate target when toast is clicked."""
    print(short_response_type)
    print(f"Toast activated for {short_response_type} with Match ID: {match_id}")
    if short_response_type == "lobby":
        response_type_id = 0
    elif short_response_type == "spectate":
        response_type_id = 1
    else:
        print("Unknown response type, cannot open game.")
        return
    response = web_open(f"aoe2de://{response_type_id}/{match_id}")
    print(f"Web open response: {response}")
    remove_image()

def dismissed_callback(dismissedEventArgs: ToastDismissedEventArgs):
    """Handle toast dismissal and clean up the temporary avatar image."""
    print(f"Toast dismissed reason: {dismissedEventArgs.reason}")
    remove_image()

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

#<--------------------------------- Toast queue --------------------------------------->
# In order to solve a race condition issue in which a player's status updates before the match infomation
# is received, we enqueue ready toast payloads and process them through one worker.
# Each (player_id, match_id, status) key is tracked so it is only queued/displayed once.

def _build_toast_key(player_id: str, match_id, status: str):
    """Build a stable key used to dedupe toast lifecycle states."""
    return (str(player_id), str(match_id), status)


def _enqueue_toast_for_player_match(player_id: str, match, status: str, match_id) -> None:
    """Queue one toast payload per (player, match, status) key."""
    key = _build_toast_key(player_id, match_id, status)
    if toast_status_by_key.get(key) in ("queued", "shown"):
        return
    # Claim the key before any expensive work so concurrent paths cannot double-enqueue.
    toast_status_by_key[key] = "queued"

    try:
        player_entry = watchlist.get_entry(player_id, {})
        player_name = player_entry.get("userName") or str(player_id)
        avatar_filepath = resolve_avatar_filepath(
            player_entry, match, watchlist.by_id, watchlist.save_index
        )
        toast_queue.put_nowait(
            {
                "key": key,
                "player_name": player_name,
                "match": match,
                "status": status,
                "avatar_filepath": avatar_filepath,
            }
        )
    except Exception:
        # Release failed queue claims so future updates can retry.
        if toast_status_by_key.get(key) == "queued":
            toast_status_by_key.pop(key, None)
        raise


async def _toast_queue_worker() -> None:
    """Display queued toasts sequentially."""
    while True:
        payload = await toast_queue.get()
        key = payload["key"]
        try:
            display_toast(
                player_name=payload["player_name"],
                match=payload["match"],
                status=payload["status"],
                avatar_filepath=payload["avatar_filepath"],
            )
            toast_status_by_key[key] = "shown"
        finally:
            toast_queue.task_done()


async def _wait_for_match_and_enqueue_toast(
    player_id: str,
    status: str,
    match_id,
    timeout_seconds: float = 12.0,
    poll_interval_seconds: float = 0.4,
) -> None:
    """Poll for a match for a short window, then enqueue a toast when available."""
    key = _build_toast_key(player_id, match_id, status)
    start = time.monotonic()
    while time.monotonic() - start < timeout_seconds:
        match = _get_match_from_book(status, match_id)
        if match:
            _enqueue_toast_for_player_match(player_id, match, status, match_id)
            break
        await asyncio.sleep(poll_interval_seconds)
    pending_wait_tasks.pop(key, None)
    if toast_status_by_key.get(key) == "waiting":
        toast_status_by_key.pop(key, None)


def _cancel_pending_match_task(key) -> None:
    """Cancel and remove a pending wait task for a key, if one exists."""
    pending_task = pending_wait_tasks.get(key)
    if pending_task and not pending_task.done():
        pending_task.cancel()
    pending_wait_tasks.pop(key, None)


def _show_or_queue_player_match(player_id: str, status: str, match_id) -> None:
    """Queue toast immediately when match exists, otherwise start a single waiter."""
    key = _build_toast_key(player_id, match_id, status)
    state = toast_status_by_key.get(key)
    if state in ("queued", "shown"):
        return

    match = _get_match_from_book(status, match_id, print_match_count=True)
    if match:
        _cancel_pending_match_task(key)
        _enqueue_toast_for_player_match(player_id, match, status, match_id)
        return

    if status not in ("lobby", "spectate"):
        return
    if key in pending_wait_tasks and not pending_wait_tasks[key].done():
        return

    toast_status_by_key[key] = "waiting"
    pending_wait_tasks[key] = asyncio.create_task(
        _wait_for_match_and_enqueue_toast(player_id, status, match_id)
    )

def _extract_player_status_update(event):
    """Extract player_id/status/match_id tuple from a player_status event."""
    player_status = event.get("player_status", {})
    player_id = list(player_status.keys())[0] if player_status else None
    if player_id is None:
        print("No player status found in event.")
        return None

    player_state = player_status.get(player_id) or {}
    status = player_state.get("status")
    match_id = player_state.get("matchid")
    return player_id, status, match_id

def _handle_player_status_update(player_id: str, status: str, match_id) -> None:
    """Handle a single player status update and decide toast queue actions."""
    player_entry = watchlist.get_entry(player_id, {})
    player_name = player_entry.get("userName") or str(player_id)
    print(f"{player_name}'s status: {status}, matchid: {match_id}")
    _show_or_queue_player_match(player_id, status, match_id)

def spy(event, **kwargs):
    """Dispatch incoming subscription events to the relevant spy handlers."""
    response_type = lobby.get_response_type(event)
    match response_type:
        case "player_status":
            # Fast-path for the only response type currently used by this module.
            parsed_status = _extract_player_status_update(event)
            if parsed_status is None:
                return
            player_id, status, match_id = parsed_status
            _handle_player_status_update(player_id, status, match_id)

async def main_async():
    """Initialize state, subscribe to watchlist players, and run indefinitely."""
    # Start the MatchBook instances. This will casue them to connect to their subscriptions
    # and begin updating their internal lists of matches.
    lobby_matches.start()
    spectate_matches.start()
    
    # Load and index the list of players to watch from watchlist.json.
    watchlist.load_index()
    profile_ids = watchlist.get_profile_ids()
    if not profile_ids:
        return

    # Start the toast queue worker before subscription events begin arriving.
    toast_worker_task = asyncio.create_task(_toast_queue_worker())
    
    # Subscribe to the "players" subscription. This allows us to see when a players status
    # has changed. Subscriptions to "lobby" and "spectate" have already occurred when their
    # MatchBook(s) were instantiated, so no need to do it again.
    subscriptions = lobby.subscribe(["players"], player_ids=profile_ids)
    lobby.connect_to_subscriptions(subscriptions, spy, create_task=True)
    
    # Keep the async process alive indefinitely.
    try:
        await asyncio.Event().wait()
    finally:
        toast_worker_task.cancel()
    
def main():
    """Program entry point for running the spies event loop."""
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
