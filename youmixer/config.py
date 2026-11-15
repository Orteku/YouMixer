"""Settings shared by every profile (keys, language, tray icon...), stored in data/config.json."""
import json
import os
import threading


class Config:
    def __init__(self, path=None):
        """`path=None` keeps the settings in memory only, which is what the tests use."""
        self.path = path
        self.lock = threading.Lock()
        self.values = self._load()

    def _load(self):
        if not self.path:
            return {}
        try:
            with open(self.path, encoding="utf-8") as f:
                values = json.load(f)
            return values if isinstance(values, dict) else {}
        except (OSError, ValueError):
            return {}

    def get(self, key, default=None):
        with self.lock:
            return self.values.get(key, default)

    def update(self, values):
        with self.lock:
            self.values.update(values)
            if not self.path:
                return
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            # Written to a temporary file first, so a crash mid-write can't leave a broken config
            temporary = self.path + ".tmp"
            with open(temporary, "w", encoding="utf-8") as f:
                json.dump(self.values, f, indent=2)
            os.replace(temporary, self.path)
