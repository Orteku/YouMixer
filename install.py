"""Installs or removes YouMixer's integration with Windows, for the current user only.

Usage: python install.py install | uninstall
"""
import os
import subprocess
import sys
import winreg

from youmixer.i18n import t

ROOT = os.path.dirname(os.path.abspath(__file__))
PYTHONW = os.path.join(ROOT, ".venv", "Scripts", "pythonw.exe")
SERVER = os.path.join(ROOT, "server.py")
PROTOCOL_KEY = r"Software\Classes\youmixer"
SHORTCUT = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs", "YouMixer.lnk")


def register_protocol():
    """youmixer:// lets the page's power key start YouMixer."""
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, PROTOCOL_KEY) as key:
        winreg.SetValueEx(key, None, 0, winreg.REG_SZ, "URL:YouMixer")
        winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, PROTOCOL_KEY + r"\shell\open\command") as key:
        winreg.SetValueEx(key, None, 0, winreg.REG_SZ, f'"{PYTHONW}" "{SERVER}" --no-browser "%1"')


def create_shortcut():
    """Start menu shortcut that opens YouMixer without a console window."""
    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:YM_LNK);"
        "$s.TargetPath = $env:YM_PYTHONW; $s.Arguments = '\"' + $env:YM_SERVER + '\"';"
        "$s.WorkingDirectory = $env:YM_ROOT; $s.Description = 'YouMixer'; $s.Save()"
    )
    env = {**os.environ, "YM_LNK": SHORTCUT, "YM_PYTHONW": PYTHONW, "YM_SERVER": SERVER, "YM_ROOT": ROOT}
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], env=env, check=True)


def install():
    register_protocol()
    print(t("install.protocol"))
    create_shortcut()
    print(t("install.shortcut"))


def uninstall():
    removed = subprocess.run(["reg", "delete", "HKCU\\" + PROTOCOL_KEY, "/f"], capture_output=True).returncode == 0
    print(t("install.protocol_removed" if removed else "install.protocol_absent"))
    if os.path.exists(SHORTCUT):
        os.remove(SHORTCUT)
        print(t("install.shortcut_removed"))


if __name__ == "__main__":
    actions = {"install": install, "uninstall": uninstall}
    if len(sys.argv) != 2 or sys.argv[1] not in actions:
        sys.exit(__doc__)
    actions[sys.argv[1]]()
