import urllib.parse
import urllib.request
from pathlib import Path

from windows_toasts import ToastDisplayImage, ToastImagePosition

from lobby import lobby

TEMP_FILE_PATH = "spies/temp_files/temp_image.png"
DEFAULT_AVATAR_PATH = "spies/assets/default_avatar.png"
AVATARS_DIR = Path("spies/avatars")

def avatar_url_to_path(avatar_url: str, avatars_dir: Path = AVATARS_DIR) -> Path:
    parsed = urllib.parse.urlparse(avatar_url)
    filename = Path(parsed.path).name
    if not filename:
        filename = urllib.parse.quote(avatar_url, safe="")
    return avatars_dir / filename


def resolve_avatar_filepath(
    player_entry: dict,
    match,
    watchlist_by_id,
    save_watchlist,
    default_avatar_path: str = DEFAULT_AVATAR_PATH,
    avatars_dir: Path = AVATARS_DIR,
) -> str:
    player_name = player_entry.get("userName") or ""
    avatar_url = None
    player_slot = lobby.get_player_slot(player_name, match) if player_name else None
    if player_slot:
        avatar_url = player_slot.get("steam_avatar", None)

    if not avatar_url:
        print("No avatar URL found, using fallback avatar.")
        return player_entry.get("avatar_filepath") or default_avatar_path

    avatar_path = avatar_url_to_path(avatar_url, avatars_dir=avatars_dir)
    if not avatar_path.exists():
        full_avatar_url = avatar_url.split(".jpg")[0] + "_full.jpg"
        download_image(full_avatar_url, filepath=str(avatar_path))

    avatar_filepath = str(avatar_path)
    if player_entry.get("avatar_filepath") != avatar_filepath:
        old_path = Path(player_entry.get("avatar_filepath") or "")
        if old_path.exists() and avatars_dir in old_path.parents:
            try:
                old_path.unlink()
            except OSError:
                pass
        player_entry["avatar_filepath"] = avatar_filepath
        save_watchlist(watchlist_by_id)

    return avatar_filepath


def add_player_avatar_to_toast(spy_toast, avatar_filepath: str):
    spy_toast.AddImage(ToastDisplayImage.fromPath(avatar_filepath, position=ToastImagePosition.AppLogo))


def download_image(url, filepath=TEMP_FILE_PATH):
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    path, _ = urllib.request.urlretrieve(url, filepath)
    return str(Path(path).resolve())


def remove_image(filepath=TEMP_FILE_PATH):
    try:
        Path(filepath).unlink()
        print("Avatar image removed.")
    except FileNotFoundError:
        pass
