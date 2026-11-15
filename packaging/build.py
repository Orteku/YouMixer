"""Builds the Windows downloads: YouMixer.exe, the portable .zip and the installer.

Usage (from the project folder):  .venv\\Scripts\\python.exe packaging\\build.py [--no-installer]
Needs requirements-dev.txt installed, and Inno Setup 6 for the installer.
"""
import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from youmixer.tray import make_image  # noqa: E402  (after the path tweak)
from youmixer.version import VERSION  # noqa: E402

BUILD = os.path.join(ROOT, "build")
DIST = os.path.join(ROOT, "dist")
APP = os.path.join(DIST, "YouMixer")
ICON = os.path.join(BUILD, "icon.ico")
VERSION_INFO = os.path.join(BUILD, "version_info.txt")
INNO_PATHS = [
    r"%LocalAppData%\Programs\Inno Setup 6\ISCC.exe",
    r"%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe",
    r"%ProgramFiles%\Inno Setup 6\ISCC.exe",
]


def make_icon():
    os.makedirs(BUILD, exist_ok=True)
    image = make_image().resize((256, 256))
    image.save(ICON, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def make_version_info():
    """The details Windows shows in the file's properties (and that antivirus tools glance at)."""
    numbers = (list(map(int, VERSION.split("."))) + [0, 0, 0, 0])[:4]
    tuple_text = ", ".join(map(str, numbers))
    with open(VERSION_INFO, "w", encoding="utf-8") as f:
        f.write(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({tuple_text}), prodvers=({tuple_text}), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Orteku'),
      StringStruct('FileDescription', 'YouMixer'),
      StringStruct('FileVersion', '{VERSION}'),
      StringStruct('InternalName', 'YouMixer'),
      StringStruct('LegalCopyright', 'MIT License'),
      StringStruct('OriginalFilename', 'YouMixer.exe'),
      StringStruct('ProductName', 'YouMixer'),
      StringStruct('ProductVersion', '{VERSION}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""")


def run(*command):
    print(">", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def build_exe():
    shutil.rmtree(APP, ignore_errors=True)
    run(
        sys.executable, "-m", "PyInstaller", "server.py",
        "--noconfirm", "--clean", "--windowed",
        "--name", "YouMixer", "--icon", ICON, "--version-file", VERSION_INFO,
        "--distpath", DIST, "--workpath", os.path.join(BUILD, "pyinstaller"), "--specpath", BUILD,
        "--add-data", f"{os.path.join(ROOT, 'web')}{os.pathsep}web",
        "--collect-data", "ytmusicapi",
        "--hidden-import", "pystray._win32",
        "--exclude-module", "tkinter",
    )
    shutil.copy(os.path.join(ROOT, "LICENSE"), APP)


def build_portable():
    """The same program plus a portable.txt: its data then stays in a data folder beside it."""
    target = os.path.join(DIST, f"YouMixer-{VERSION}-portable.zip")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for folder, _, files in os.walk(APP):
            for name in files:
                path = os.path.join(folder, name)
                archive.write(path, os.path.join("YouMixer", os.path.relpath(path, APP)))
        archive.writestr("YouMixer/portable.txt", "Delete this file to keep the data in %APPDATA%\\YouMixer instead.\n")
    return target


def build_installer():
    iscc = next((os.path.expandvars(p) for p in INNO_PATHS if os.path.exists(os.path.expandvars(p))), shutil.which("ISCC"))
    if not iscc:
        sys.exit("Inno Setup 6 was not found. Install it (winget install JRSoftware.InnoSetup) or use --no-installer.")
    run(iscc, f"/DAppVersion={VERSION}", f"/DSourceDir={APP}", f"/DOutputDir={DIST}",
        os.path.join(ROOT, "packaging", "YouMixer.iss"))


if __name__ == "__main__":
    make_icon()
    make_version_info()
    build_exe()
    print("Portable:", build_portable())
    if "--no-installer" not in sys.argv:
        build_installer()
