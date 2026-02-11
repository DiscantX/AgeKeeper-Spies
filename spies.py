from windows_toasts import(
        InteractableWindowsToaster, Toast,
        ToastDisplayImage, ToastImagePosition,
        ToastActivatedEventArgs, ToastDismissedEventArgs, ToastFailedEventArgs
    )
from lobby import lobby
import urllib.request
import time
from webbrowser import open_new as web_open
from pathlib import Path
from functools import partial

lobby_rooms = []
spectate_matches = []

temp_file_path = "spies/temp_files/temp_image.png" 
default_avatar_path = "spies/assets/default_avatar.png"
toaster = InteractableWindowsToaster('AOE2: Spies')
spyToast = Toast('Spy Alert')

player_name = "Necron99"
profileid = 10056062

class Rooms:
    def __init__(self, lobby_rooms):
       self._rooms = []
       
    def __iter__(self):
        return iter(self._rooms)
    
    def __len__(self):
        return len(self._rooms)

    def __getitem__(self, index):
        return self._rooms[index]
    
    def add(self, room):
        self._rooms.append(room)
    
    def clear(self):
        self._rooms.clear()
        
    def update(self, event, response_type):  
        received_lobby_rooms = [event.get(response_type, {}).get(match_id, {}) for match_id in event.get(response_type, [])]
        removed_lobby_rooms = [room for room in lobby_rooms if room.get("matchid") not in [m.get("matchid") for m in received_lobby_rooms]]
        self._rooms = removed_lobby_rooms + received_lobby_rooms


def get_player_avatar(player_name: str, match):
    avatar_url = None
    player_slot = lobby.get_player_slot(player_name, match)
    if player_slot:
        avatar_url = player_slot.get("steam_avatar", None)
    if avatar_url:
        avatar_filepath = download_image(avatar_url)
    else:
        print("No avatar URL found, using default avatar.")
        avatar_filepath = default_avatar_path
    return avatar_filepath

def add_player_avatar_to_toast(player_name: str, match):
    filepath = get_player_avatar(player_name, match)
    spyToast.AddImage(ToastDisplayImage.fromPath(filepath, position = ToastImagePosition.AppLogo))

# Helper function to download an image and return local path
def download_image(url, filepath=temp_file_path):
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

def display_toast(player_name: str, match, status: str):  
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
    add_player_avatar_to_toast(player_name, match)
    
    toaster.show_toast(spyToast)
    
    print("\nNew Spy Alert:")
    print("="*40)
    print("\n".join(toast_fields))

def update_lobby_rooms(event, response_type: str):
    global lobby_rooms
    received_lobby_rooms = [event.get(response_type, {}).get(match_id, {}) for match_id in event.get(response_type, [])]
    removed_lobby_rooms = [room for room in lobby_rooms if room.get("matchid") not in [m.get("matchid") for m in received_lobby_rooms]]
    lobby_rooms = removed_lobby_rooms + received_lobby_rooms

def update_spectate_matches(event, response_type: str):
    global spectate_matches
    received_spectate_matches = [event.get(response_type, {}).get(match_id, {}) for match_id in event.get(response_type, [])]
    removed_spectate_matches = [match for match in spectate_matches if match.get("matchid") not in [m.get("matchid") for m in received_spectate_matches]]
    spectate_matches = removed_spectate_matches + received_spectate_matches
    print(f"Number of spectate matches: {len(spectate_matches)}")
    
def spy(event, **kwargs):
    match = None
    response_type = lobby.get_response_type(event)
    match response_type:
        case "lobby_match_all":
            update_lobby_rooms(event, response_type)
        case "lobby_match_update":
            update_lobby_rooms(event, response_type)     
        case "spectate_match_all":
            update_spectate_matches(event, response_type)
            match = lobby.search_matches_for_player(player_name, spectate_matches)
            status = "spectate"
            match_id = match.get("matchid", None) if match else None
        case "spectate_match_update":
            update_spectate_matches(event, response_type)   
            match = lobby.search_matches_for_player(player_name, spectate_matches)
            status = "spectate"
            match_id = match.get("matchid", None) if match else None
        case "player_status":
            player_status = event.get('player_status', {})
            player_id = list(player_status.keys())[0] if player_status else None
            if player_id is None:
                print("No player status found in event.")
                return
            
            status = player_status.get(player_id, None).get('status', None)
            match_id = player_status.get(player_id, None).get('matchid', None)
            print(f"{player_name}'s status: {status}, matchid: {match_id}")
            
            if status == "lobby":
                if len(lobby_rooms) > 0:
                    print(f"Searching for match ID {match_id} in lobby rooms...")
                    match = next((m for m in lobby_rooms if str(m.get("matchid")) == str(match_id)), None)
            if status == "spectate":
                if len(spectate_matches) > 0:
                    print(f"Searching for match ID {match_id} in spectate matches...")
                    match = next((m for m in spectate_matches if str(m.get("matchid")) == str(match_id)), None)
                
    if match:
        print(f"Displaying toast for {player_name} in match ID {match_id} with status {status}.")
        display_toast(player_name=player_name, match=match, status=status)

def main():
    subscriptions = lobby.subscribe(["lobby", "spectate", "players"], player_ids = [profileid])
    lobby.connect_to_subscriptions(subscriptions, spy)

if __name__ == "__main__":
    main()
