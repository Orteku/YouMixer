"""Where things live, whether YouMixer runs from source or as the packaged YouMixer.exe.

- RESOURCES: the program's own files (the web/ folder).
- APP_DIR: the folder of the program itself.
- data_dir(): where the user's data goes.
"""
import os
import sys

FROZEN = getattr(sys, "frozen", False)
RESOURCES = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.dirname(sys.executable) if FROZEN else RESOURCES
PORTABLE_MARKER = "portable.txt"


def is_portable():
    """The portable zip ships a portable.txt next to the exe: its data then stays beside it."""
    return FROZEN and os.path.exists(os.path.join(APP_DIR, PORTABLE_MARKER))


def data_dir():
    if os.environ.get("YOUMIXER_DATA"):
        return os.environ["YOUMIXER_DATA"]
    if not FROZEN or is_portable():
        return os.path.join(APP_DIR, "data")
    return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "YouMixer")  # installed: like any other program
