"""Opens the page in the browser or in its own window (Edge or Chrome in app mode, with no address bar)."""
import os
import subprocess
import webbrowser

from . import log

MODES = ("browser", "window")
WINDOW_SIZE = "1440,900"
APP_BROWSERS = [
    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
    r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
    r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
]


def app_browser():
    for path in APP_BROWSERS:
        path = os.path.expandvars(path)
        if os.path.exists(path):
            return path
    return None


def window_available():
    return app_browser() is not None


def open_ui(url, mode="browser"):
    """The app window is opened with ?window=1 so the page knows where it is running."""
    if os.environ.get("YOUMIXER_NO_LAUNCH") == "1":  # tests: never open real windows
        log("launch", mode, url)
        return
    browser = app_browser() if mode == "window" else None
    if browser:
        subprocess.Popen([browser, f"--app={url}?window=1", f"--window-size={WINDOW_SIZE}"])
    else:
        webbrowser.open(url)
