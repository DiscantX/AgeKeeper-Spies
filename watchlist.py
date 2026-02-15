from pathlib import Path
import json

from aoe2api import aoe2api

DEFAULT_AVATAR_PATH = "spies/assets/default_avatar.png"
WATCHLIST_PATH = Path("spies/watchlist.json")


class Watchlist:
    """Manages watchlist loading, indexing, and persistence."""

    def __init__(
        self,
        watchlist_path: Path = WATCHLIST_PATH,
        default_avatar_path: str = DEFAULT_AVATAR_PATH,
    ):
        self.watchlist_path = watchlist_path
        self.default_avatar_path = default_avatar_path
        self.by_id = {}

    def create_empty(self) -> None:
        if self.watchlist_path.exists():
            return
        self.watchlist_path.parent.mkdir(parents=True, exist_ok=True)
        template = [
            {
                "userName": "",
                "profileid": "",
                "avatar_filepath": self.default_avatar_path,
            }
        ]
        with open(self.watchlist_path, "w", encoding="utf-8") as f:
            json.dump(template, f, indent=2)
        print(f"Created watchlist template at {self.watchlist_path}")

    def load_entries(self):
        if not self.watchlist_path.exists():
            self.create_empty()
            return []

        with open(self.watchlist_path, "r", encoding="utf-8") as f:
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
                entry["avatar_filepath"] = self.default_avatar_path

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
            self.save_entries(normalized)

        return normalized

    def save_entries(self, entries) -> None:
        with open(self.watchlist_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2)

    def load_index(self):
        entries = self.load_entries()
        self.by_id = {
            str(entry.get("profileid")): entry
            for entry in entries
            if entry.get("profileid")
        }
        return self.by_id

    def save_index(self, by_id=None) -> None:
        index = self.by_id if by_id is None else by_id
        self.save_entries(list(index.values()))

    def get_profile_ids(self):
        profile_ids = list(self.by_id.keys())
        if not profile_ids:
            print("Watchlist is empty. Add profile IDs to spies/watchlist.json to start spying.")
        return profile_ids

    def get_entry(self, profile_id, default=None):
        return self.by_id.get(str(profile_id), default)
