from windows_toasts import(
        InteractableWindowsToaster, Toast,
        ToastDisplayImage, ToastImagePosition,
        ToastActivatedEventArgs, ToastDismissedEventArgs, ToastFailedEventArgs
    )
from lobby import lobby
from lobby.match_book import MatchBook
from aoe2api import aoe2api
import urllib.request
import urllib.parse
import time
from webbrowser import open_new as web_open
from pathlib import Path
import json
from functools import partial
import asyncio

temp_file_path = "spies/temp_files/temp_image.png" 
default_avatar_path = "spies/assets/default_avatar.png"
watchlist_path = Path("spies/watchlist.json")
avatars_dir = Path("spies/avatars")
toaster = InteractableWindowsToaster('AOE2: Spies')
spyToast = Toast('Spy Alert')

watchlist_by_id = {}
watchlist_profile_ids = []
watchlist_entries = []

lobby_matches = MatchBook("lobby")
spectate_matches = MatchBook("spectate")

def create_empty_watchlist():
    if not watchlist_path.exists():
        watchlist_path.parent.mkdir(parents=True, exist_ok=True)
        template = [
            {
                "userName": "",
                "profileid": "",
                "avatar_filepath": default_avatar_path,
            }
        ]
        with open(watchlist_path, "w", encoding="utf-8") as f:
            json.dump(template, f, indent=2)
        print(f"Created watchlist template at {watchlist_path}")

def load_watchlist():
    if not watchlist_path.exists():
        create_empty_watchlist()
        return []

    with open(watchlist_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("Watchlist JSON must be a list of player entries or profile IDs.")

    normalized = []
    ids_missing_usernames = []
    usernames_missing_ids = []
    for item in raw:
        entry = {}
        if isinstance(item, (int, str)):
            entry["profileid"] = str(item)
        elif isinstance(item, dict):
            entry = dict(item)
            if "profileid" in entry and entry["profileid"] is not None:
                entry["profileid"] = str(entry["profileid"])
        else:
            continue

        if "avatar_filepath" not in entry or not entry.get("avatar_filepath"):
            entry["avatar_filepath"] = default_avatar_path

        if entry.get("profileid") and not entry.get("userName"):
            ids_missing_usernames.append(entry["profileid"])

        if entry.get("userName") and not entry.get("profileid"):
            usernames_missing_ids.append(entry["userName"])

        normalized.append(entry)

    updated = False
    if ids_missing_usernames:
        usernames = aoe2api.get_usernames_from_ids(ids_missing_usernames)
        id_to_username = dict(zip(ids_missing_usernames, usernames))
        for entry in normalized:
            pid = entry.get("profileid")
            if pid in id_to_username and not entry.get("userName"):
                entry["userName"] = id_to_username.get(pid) or ""
                updated = True

    if usernames_missing_ids:
        ids = aoe2api.get_ids_from_usernames(usernames_missing_ids)
        username_to_id = dict(zip(usernames_missing_ids, ids))
        for entry in normalized:
            username = entry.get("userName")
            if username in username_to_id and not entry.get("profileid"):
                entry["profileid"] = str(username_to_id.get(username) or "")
                updated = True

    if updated:
        with open(watchlist_path, "w", encoding="utf-8") as f:
            json.dump(normalized, f, indent=2)

    return normalized

def save_watchlist(entries):
    with open(watchlist_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)

def avatar_url_to_path(avatar_url: str) -> Path:
    parsed = urllib.parse.urlparse(avatar_url)
    filename = Path(parsed.path).name
    if not filename:
        filename = urllib.parse.quote(avatar_url, safe="")
    return avatars_dir / filename

def resolve_avatar_filepath(player_entry: dict, match) -> str:
    player_name = player_entry.get("userName") or ""
    avatar_url = None
    player_slot = lobby.get_player_slot(player_name, match) if player_name else None
    if player_slot:
        avatar_url = player_slot.get("steam_avatar", None)

    if not avatar_url:
        print("No avatar URL found, using fallback avatar.")
        return player_entry.get("avatar_filepath") or default_avatar_path

    avatar_path = avatar_url_to_path(avatar_url)
    if not avatar_path.exists():
        download_image(avatar_url, filepath=str(avatar_path))

    avatar_filepath = str(avatar_path)
    if player_entry.get("avatar_filepath") != avatar_filepath:
        old_path = Path(player_entry.get("avatar_filepath") or "")
        if old_path.exists() and avatars_dir in old_path.parents:
            try:
                old_path.unlink()
            except OSError:
                pass
        player_entry["avatar_filepath"] = avatar_filepath
        save_watchlist(watchlist_entries)

    return avatar_filepath

def add_player_avatar_to_toast(avatar_filepath: str):
    spyToast.AddImage(ToastDisplayImage.fromPath(avatar_filepath, position = ToastImagePosition.AppLogo))

# Helper function to download an image and return local path
def download_image(url, filepath=temp_file_path):
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    path, _ = urllib.request.urlretrieve(url, filepath)
    return str(Path(path).resolve())

def remove_image(filepathh=temp_file_path):
    try:
        Path(filepathh).unlink()
        print("Avatar image removed.")
    except FileNotFoundError:
        pass

def on_toast_dismissed():
    print("Toast dismissed.")

def activated_callback(activatedEventArgs: ToastActivatedEventArgs, short_response_type: str, match_id: str):
    print(f"Toast activated for {short_response_type} with Match ID: {match_id}")
    if short_response_type == "Lobby":
        response_type_id = 0
    elif short_response_type == "Spectate":
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

    time_dilation = 7 # Server time is approx 7 seconds ahead of local time, so we subtract 7 seconds from the match creation time to get a more accurate "time alive" for the match
    created_time = match.get("created_time", int(time.time())) - time_dilation
    match_time_alive = int(time.time()) - created_time
            
    toast_fields = [
        f"{player_name[:25]} joined {short_response_type.lower()}:\n{match.get('description', 'a {short_response_type.lower()}')}",
        f"Map: {match.get('map_name', 'Unknown Map')} | Playing as: {player_civ_name}",
        f"Started: {match_time_alive}s ago | {match.get('slots_taken', -1)} Player{"s" if match.get("slots_taken", -1) != 1 else ""} in {short_response_type.lower()}"
        ]
     
    spyToast.on_activated = partial(activated_callback, short_response_type=short_response_type, match_id=match.get("matchid", -1))
    spyToast.on_dismissed = dismissed_callback
    spyToast.on_failed = failed_callback
    spyToast.text_fields = toast_fields
    spyToast.AddImage(ToastDisplayImage.fromPath('assets/AgeKeeperBanner_Cropped.png', position = ToastImagePosition.Hero))
    add_player_avatar_to_toast(avatar_filepath)
    
    toaster.show_toast(spyToast)
    
    print("\nNew Spy Alert:")
    print("="*40)
    print("\n".join(toast_fields))
    
def spy(event, **kwargs):
    match = None
    status = None
    response_type = lobby.get_response_type(event)
    match response_type:  
        case "player_status":
            player_status = event.get('player_status', {})
            player_id = list(player_status.keys())[0] if player_status else None
            if player_id is None:
                print("No player status found in event.")
                return
            
            status = player_status.get(player_id, None).get('status', None)
            match_id = player_status.get(player_id, None).get('matchid', None)
            player_entry = watchlist_by_id.get(str(player_id), {})
            player_name = player_entry.get("userName") or str(player_id)
            print(f"{player_name}'s status: {status}, matchid: {match_id}")
            
            if status == "lobby":
                if len(lobby_matches) > 0:
                    # print(f"Searching for match ID {match_id} in lobby matches...")
                    match = next((m for m in lobby_matches if str(m.get("matchid")) == str(match_id)), None)
                    lobby_matches.print_number_of_matches()
            if status == "spectate":
                if len(spectate_matches) > 0:
                    # print(f"Searching for match ID {match_id} in spectate matches...")
                    match = next((m for m in spectate_matches if str(m.get("matchid")) == str(match_id)), None)
                    spectate_matches.print_number_of_matches()
                
    if match:
        player_entry = watchlist_by_id.get(str(player_id), {})
        player_name = player_entry.get("userName") or str(player_id)
        avatar_filepath = resolve_avatar_filepath(player_entry, match)
        display_toast(player_name=player_name, match=match, status=status, avatar_filepath=avatar_filepath)

async def main_async():
    lobby_matches.start()
    spectate_matches.start()
    watchlist = load_watchlist()
    global watchlist_by_id
    global watchlist_profile_ids
    global watchlist_entries
    watchlist_entries = watchlist
    watchlist_by_id = {str(entry.get("profileid")): entry for entry in watchlist if entry.get("profileid")}
    watchlist_profile_ids = list(watchlist_by_id.keys())
    if not watchlist_profile_ids:
        print("Watchlist is empty. Add profile IDs to spies/watchlist.json to start spying.")
        return

    subscriptions = lobby.subscribe(["spectate", "players"], player_ids = watchlist_profile_ids)
    lobby.connect_to_subscriptions_task(subscriptions, spy)
    await asyncio.Event().wait()

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
