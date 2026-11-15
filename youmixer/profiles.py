"""Profiles: each one has its own lists, history and learning, in its own database.

Keys, the YouTube account and the other settings are shared by all of them (data/config.json).
"""
import json
import os
import re
import shutil
import threading
import time
import unicodedata

from .i18n import t
from .store import Store

MAIN = "principal"  # id of the profile that always exists; its data is data/youmixer.db
NAME_MAX = 40


class ProfileError(Exception):
    """A failure whose message can be shown to the user as it is."""


def slugify(name):
    """Profile name → safe file name for its database."""
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:30] or "profile"


class Profiles:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.index_path = os.path.join(data_dir, "profiles.json")
        self.lock = threading.RLock()
        self.stores = {}
        self.data = self._load()
        self.current = self.store(self.data["active"])

    def _load(self):
        try:
            with open(self.index_path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        profiles = [p for p in data.get("profiles", []) if p.get("id") and p.get("name")]
        if not any(p["id"] == MAIN for p in profiles):
            profiles.insert(0, {"id": MAIN, "name": t("profile.main")})
        active = data.get("active")
        if not any(p["id"] == active for p in profiles):
            active = MAIN
        return {"active": active, "profiles": profiles}

    def _save(self):
        os.makedirs(self.data_dir, exist_ok=True)
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def db_path(self, profile_id):
        if profile_id == MAIN:
            return os.path.join(self.data_dir, "youmixer.db")
        return os.path.join(self.data_dir, "profiles", f"{profile_id}.db")

    def store(self, profile_id):
        """Opens a profile's database (once per session, making its backup)."""
        with self.lock:
            if profile_id not in self.stores:
                store = Store(self.db_path(profile_id))
                folder = os.path.join(self.data_dir, "backups")
                store.backup(folder if profile_id == MAIN else os.path.join(folder, profile_id))
                self.stores[profile_id] = store
            return self.stores[profile_id]

    def find(self, profile_id):
        profile = next((p for p in self.data["profiles"] if p["id"] == profile_id), None)
        if not profile:
            raise ProfileError(t("err.profile_missing"))
        return profile

    @property
    def active(self):
        return self.find(self.data["active"])

    def list(self):
        return {"active": self.data["active"], "main": MAIN, "profiles": self.data["profiles"]}

    @staticmethod
    def _clean_name(name):
        name = " ".join(str(name or "").split())[:NAME_MAX]
        if not name:
            raise ProfileError(t("err.profile_name"))
        return name

    def _name_taken(self, name, except_id=None):
        return any(p["name"].lower() == name.lower() and p["id"] != except_id for p in self.data["profiles"])

    def create(self, name, copy_lists=False):
        """New profile; with `copy_lists` it starts with the current profile's lists, never with its learning."""
        with self.lock:
            name = self._clean_name(name)
            if self._name_taken(name):
                raise ProfileError(t("err.profile_taken"))
            base = slugify(name)
            taken = {p["id"] for p in self.data["profiles"]}
            profile_id = base if base not in taken else next(f"{base}-{n}" for n in range(2, 1000) if f"{base}-{n}" not in taken)
            new = self.store(profile_id)
            if copy_lists:
                # Oldest first, so the copies keep the same order (lists are shown newest first)
                for source in reversed(self.current.sources()):
                    tracks = self.current.source_tracks(source["id"])
                    new.create_source(source["kind"], source["name"], source["ref"], tracks, source["meta"])
            self.data["profiles"].append({"id": profile_id, "name": name})
            self._save()
            return profile_id

    def switch(self, profile_id):
        with self.lock:
            self.find(profile_id)
            self.current = self.store(profile_id)
            self.data["active"] = profile_id
            self._save()

    def rename(self, profile_id, name):
        with self.lock:
            name = self._clean_name(name)
            if self._name_taken(name, except_id=profile_id):
                raise ProfileError(t("err.profile_taken"))
            self.find(profile_id)["name"] = name
            self._save()

    def delete(self, profile_id):
        """The profile isn't lost for good: its database is moved to data/backups/deleted."""
        with self.lock:
            if profile_id == MAIN:
                raise ProfileError(t("err.profile_main"))
            if profile_id == self.data["active"]:
                raise ProfileError(t("err.profile_active"))
            self.find(profile_id)
            store = self.stores.pop(profile_id, None)
            if store:
                store.close()
            path = self.db_path(profile_id)
            if os.path.exists(path):
                folder = os.path.join(self.data_dir, "backups", "deleted")
                os.makedirs(folder, exist_ok=True)
                shutil.move(path, os.path.join(folder, time.strftime(f"{profile_id}-%Y%m%d-%H%M%S.db")))
            for suffix in ("-wal", "-shm"):
                if os.path.exists(path + suffix):
                    os.remove(path + suffix)
            self.data["profiles"] = [p for p in self.data["profiles"] if p["id"] != profile_id]
            self._save()

    def close_all(self):
        with self.lock:
            for store in self.stores.values():
                store.close()
            self.stores.clear()


class ActiveStore:
    """Used like a plain Store, but always pointing at the profile in use."""

    def __init__(self, profiles):
        self._profiles = profiles

    def concrete(self):
        """The Store of the profile in use right now, for long tasks that must not follow a profile switch."""
        return self._profiles.current

    def __getattr__(self, name):
        return getattr(self._profiles.current, name)
