"""Texts in several languages. The page uses these very same files: web/i18n/<language>.json.

To add a language, copy en.json under another name (for example fr.json) and translate it.
"""
import json
import locale
import os
import sys
import threading

from .paths import RESOURCES

FOLDER = os.path.join(RESOURCES, "web", "i18n")
FALLBACK = "en"
# Windows primary language identifiers → our language codes
WINDOWS_LANGUAGES = {0x0A: "es", 0x09: "en"}

_lock = threading.Lock()
_cache = {}
_language = None


def _load(code):
    with _lock:
        if code not in _cache:
            try:
                with open(os.path.join(FOLDER, f"{code}.json"), encoding="utf-8") as f:
                    _cache[code] = json.load(f)
            except (OSError, ValueError):
                _cache[code] = {}
        return _cache[code]


def available():
    codes = sorted(name[:-5] for name in os.listdir(FOLDER) if name.endswith(".json"))
    return [{"code": code, "name": _load(code).get("_name", code)} for code in codes]


def is_available(code):
    return any(language["code"] == code for language in available())


def system_language():
    """The Windows display language when we have it; English otherwise."""
    code = ""
    if sys.platform == "win32":
        try:
            import ctypes

            code = WINDOWS_LANGUAGES.get(ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF, "")
        except (AttributeError, OSError):
            code = ""
    if not code:
        code = (locale.getlocale()[0] or "").split("_")[0].lower()[:2]
    return code if is_available(code) else FALLBACK


def set_language(code):
    global _language
    _language = code if is_available(code) else FALLBACK


def language():
    if _language is None:
        set_language(system_language())
    return _language


def t(key, **values):
    """Text for `key` in the current language, with {placeholders} filled in from `values`."""
    text = _load(language()).get(key) or _load(FALLBACK).get(key) or key
    for name, value in values.items():
        text = text.replace("{" + name + "}", str(value))
    return text
