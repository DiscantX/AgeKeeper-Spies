from pathlib import Path
import ctypes
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
from spies.watchlist import DEFAULT_AVATAR_PATH, load_watchlist, save_watchlist
from spies.avatar import add_player_avatar_to_toast, resolve_avatar_filepath, remove_image

default_avatar_path = DEFAULT_AVATAR_PATH
toaster = InteractableWindowsToaster("AOE2: Spies")
spyToast = Toast("Spy Alert")
PROJECT_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
SPIES_ASSETS_DIR = Path(__file__).resolve().parent / "assets"
WINMM = ctypes.windll.winmm
MCI_ALIAS = "AgeKeeperSpyAlert"

def resolve_asset_path(filename: str, *candidate_dirs: Path) -> Path:
    for base_dir in candidate_dirs:
        asset_path = base_dir / filename
        if asset_path.exists():
            return asset_path
    return candidate_dirs[0] / filename


def play_alert_audio(audio_path: Path) -> None:
    # Toast custom file audio can be ignored in some desktop app contexts.
    # Use the Windows MCI API to play the local media file directly.
    if not audio_path.exists():
        print(f"Audio file not found: {audio_path}")
        return

    path_str = str(audio_path.resolve()).replace('"', '""')
    WINMM.mciSendStringW(f"close {MCI_ALIAS}", None, 0, None)
    open_result = WINMM.mciSendStringW(
        f'open "{path_str}" type mpegvideo alias {MCI_ALIAS}',
        None,
        0,
        None,
    )
    if open_result != 0:
        print(f"Failed to open alert audio with MCI (code: {open_result})")
        return

    play_result = WINMM.mciSendStringW(f"play {MCI_ALIAS}", None, 0, None)
    if play_result != 0:
        print(f"Failed to play alert audio with MCI (code: {play_result})")

watchlist_by_id = {}
watchlist_profile_ids = []
watchlist_entries = []

lobby_matches = MatchBook("lobby")
spectate_matches = MatchBook("spectate")
pending_match_tasks = {}
notified_match_keys = set()


def _get_match_from_book(status: str, match_id):
    if status == "lobby":
        match_book = lobby_matches
    elif status == "spectate":
        match_book = spectate_matches
    else:
        return None
    return next(
        (match for match in match_book if str(match.get("matchid")) == str(match_id)),
        None,
    )


def _show_toast_for_player_match(player_id: str, match, status: str, match_id) -> None:
    key = (str(player_id), str(match_id), status)
    if key in notified_match_keys:
        return

    player_entry = watchlist_by_id.get(str(player_id), {})
    player_name = player_entry.get("userName") or str(player_id)
    avatar_filepath = resolve_avatar_filepath(
        player_entry, match, watchlist_entries, save_watchlist
    )
    display_toast(
        player_name=player_name,
        match=match,
        status=status,
        avatar_filepath=avatar_filepath,
    )
    notified_match_keys.add(key)


async def _wait_for_match_and_toast(
    player_id: str,
    status: str,
    match_id,
    timeout_seconds: float = 12.0,
    poll_interval_seconds: float = 0.4,
) -> None:
    key = (str(player_id), str(match_id), status)
    start = time.monotonic()
    while time.monotonic() - start < timeout_seconds:
        match = _get_match_from_book(status, match_id)
        if match:
            _show_toast_for_player_match(player_id, match, status, match_id)
            break
        await asyncio.sleep(poll_interval_seconds)
    pending_match_tasks.pop(key, None)

def activated_callback(
    activatedEventArgs: ToastActivatedEventArgs, short_response_type: str, match_id: str
):
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
    print(f"Toast dismissed reason: {dismissedEventArgs.reason}")
    remove_image()

def failed_callback(failedEventArgs: ToastFailedEventArgs):
    print(f"Toast failed: {failedEventArgs.reason}")

def display_toast(player_name: str, match, status: str, avatar_filepath: str = default_avatar_path):
    short_response_type = status
    player_data = lobby.get_player_slot(player_name, match)
    if player_data:
        player_civ_name = lobby.get_civ_name(player_data.get("civilization", -1))
    else:
        player_civ_name = "Player Unavailable"

    # Server time is approx 7 seconds ahead of local time.
    time_dilation = 0
    created_time = match.get("created_time", int(time.time())) - time_dilation
    match_time_alive = int(time.time()) - created_time
    subscription_description = "Unkown"
    match short_response_type:
        case "lobby":
            subscription_description = "lobby"
        case "spectate":
            subscription_description = "game"
            
    toast_fields = [
        f"{player_name[:25]} is in {subscription_description}:\n{match.get('description', f'a {subscription_description}')}",
        f"Map: {match.get('map_name', 'Unknown Map')} | Playing as: {player_civ_name}",
        f"Started: {match_time_alive}s ago | {match.get('slots_taken', -1)} Player{'s' if match.get('slots_taken', -1) != 1 else ''} in {subscription_description}",
    ]

    spyToast.on_activated = partial(activated_callback,short_response_type=short_response_type,match_id=match.get("matchid", -1),)
    spyToast.on_dismissed = dismissed_callback
    spyToast.on_failed = failed_callback
    # spyToast.scenario = ToastScenario.IncomingCall
    spyToast.text_fields = toast_fields
    banner_path = resolve_asset_path("AgeKeeperBanner_Cropped.png", PROJECT_ASSETS_DIR, SPIES_ASSETS_DIR)
    audio_path = resolve_asset_path("16_enemy_sighted.mp3", SPIES_ASSETS_DIR, PROJECT_ASSETS_DIR)
    spyToast.AddImage(
        ToastDisplayImage.fromPath(
            str(banner_path),
            position=ToastImagePosition.Hero,
        )
    )
    add_player_avatar_to_toast(spyToast, avatar_filepath)
    # Disable native toast audio to avoid the default Windows ding.
    # We play our custom alert explicitly right after showing the toast.
    spyToast.audio = ToastAudio(silent=True)
    toaster.show_toast(spyToast)
    time.sleep(0.1)
    play_alert_audio(audio_path)

    print("\nNew Spy Alert:")
    print("=" * 40)
    print("\n".join(toast_fields))
    print(f"Start time: {time.ctime(time.time())}\n")

def spy(event, **kwargs):
    response_type = lobby.get_response_type(event)
    match response_type:
        case "player_status":
            player_status = event.get("player_status", {})
            player_id = list(player_status.keys())[0] if player_status else None
            if player_id is None:
                print("No player status found in event.")
                return

            match = None
            status = player_status.get(player_id, None).get("status", None)
            match_id = player_status.get(player_id, None).get("matchid", None)
            player_entry = watchlist_by_id.get(str(player_id), {})
            player_name = player_entry.get("userName") or str(player_id)
            print(f"{player_name}'s status: {status}, matchid: {match_id}")

            if status == "lobby":
                if len(lobby_matches) > 0:
                    match = _get_match_from_book(status, match_id)
                    lobby_matches.print_number_of_matches()
                else:
                    match = None
            if status == "spectate":
                if len(spectate_matches) > 0:
                    match = _get_match_from_book(status, match_id)
                    spectate_matches.print_number_of_matches()
                else:
                    match = None

            key = (str(player_id), str(match_id), status)
            pending_task = pending_match_tasks.get(key)

            if match:
                if pending_task and not pending_task.done():
                    pending_task.cancel()
                _show_toast_for_player_match(player_id, match, status, match_id)
            elif status in ("lobby", "spectate"):
                if pending_task is None or pending_task.done():
                    pending_match_tasks[key] = asyncio.create_task(
                        _wait_for_match_and_toast(player_id, status, match_id)
                    )


async def main_async():
    lobby_matches.start()
    spectate_matches.start()
    watchlist = load_watchlist()
    global watchlist_by_id
    global watchlist_profile_ids
    global watchlist_entries
    watchlist_entries = watchlist
    watchlist_by_id = {
        str(entry.get("profileid")): entry
        for entry in watchlist
        if entry.get("profileid")
    }
    watchlist_profile_ids = list(watchlist_by_id.keys())
    if not watchlist_profile_ids:
        print("Watchlist is empty. Add profile IDs to spies/watchlist.json to start spying.")
        return

    subscriptions = lobby.subscribe(["players"], player_ids=watchlist_profile_ids)
    lobby.connect_to_subscriptions_task(subscriptions, spy)
    await asyncio.Event().wait()

def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
