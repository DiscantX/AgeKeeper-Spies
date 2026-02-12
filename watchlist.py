from pathlib import Path
import json

from aoe2api import aoe2api

DEFAULT_AVATAR_PATH = "spies/assets/default_avatar.png"
WATCHLIST_PATH = Path("spies/watchlist.json")


def create_empty_watchlist(
    watchlist_path: Path = WATCHLIST_PATH,
    default_avatar_path: str = DEFAULT_AVATAR_PATH,
):
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


def load_watchlist(
    watchlist_path: Path = WATCHLIST_PATH,
    default_avatar_path: str = DEFAULT_AVATAR_PATH,
):
    if not watchlist_path.exists():
        create_empty_watchlist(watchlist_path=watchlist_path, default_avatar_path=default_avatar_path)
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

def save_watchlist(entries, watchlist_path: Path = WATCHLIST_PATH):
    with open(watchlist_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)
