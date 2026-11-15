"""Checks on GitHub whether a newer version has been published. It only reads; nothing is downloaded."""
import json
import re
import threading
import time
import urllib.error
import urllib.request

from .version import REPOSITORY, VERSION


def parse(version):
    """'v1.2.3' or '1.2' → (1, 2, 3) / (1, 2, 0). Anything that isn't a number is ignored."""
    numbers = [int(n) for n in re.findall(r"\d+", str(version))[:3]]
    return tuple(numbers + [0] * (3 - len(numbers)))


def is_newer(latest, current=VERSION):
    return parse(latest) > parse(current)


class Updates:
    def __init__(self, repository=REPOSITORY):
        self.url = f"https://api.github.com/repos/{repository}/releases/latest"
        self.lock = threading.Lock()
        self.state = {"current": VERSION, "status": "unknown", "latest": None, "page": None, "checked_at": None}

    def check(self):
        """Status: available, current, none (no version published yet) or error."""
        request = urllib.request.Request(self.url, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"YouMixer/{VERSION}",
        })
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                release = json.load(response)
            latest = release.get("tag_name", "").lstrip("vV")
            result = {"status": "available" if is_newer(latest) else "current", "latest": latest, "page": release.get("html_url")}
        except urllib.error.HTTPError as error:
            result = {"status": "none" if error.code == 404 else "error", "latest": None, "page": None}
        except (OSError, ValueError):
            result = {"status": "error", "latest": None, "page": None}
        with self.lock:
            self.state.update(result, checked_at=time.time())
            return dict(self.state)

    def info(self):
        with self.lock:
            return dict(self.state)

    def check_in_background(self):
        threading.Thread(target=self.check, daemon=True).start()
