"""YouMixer's local server: it serves the page and its API, and only listens on this PC.

Run it with `python server.py` (or YouMixer.exe once packaged). Options:
  --no-browser        don't open the page
  --quit              turn off a YouMixer that is already running, and exit (used by the installer)
Environment variables, meant for testing:
  YOUMIXER_DATA       folder for the data (default: ./data, or %APPDATA%\YouMixer when installed)
  YOUMIXER_PORT       port to listen on (default: 8787)
  YOUMIXER_TRAY=0     no icon next to the clock
  YOUMIXER_NO_LAUNCH=1  never open browser windows
"""
import json
import os
import re
import socket
import sys
import threading
import time
import traceback
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from youmixer import i18n, launcher, log, tray
from youmixer.config import Config
from youmixer.i18n import t
from youmixer.paths import RESOURCES, data_dir
from youmixer.profiles import ActiveStore, Profiles
from youmixer.service import GENRES, Service, UserError
from youmixer.updates import Updates
from youmixer.version import VERSION

WEB = os.path.join(RESOURCES, "web")
DATA = data_dir()
PORT = int(os.environ.get("YOUMIXER_PORT") or 8787)
LOG_MAX_BYTES = 1_000_000
BODY_MAX_BYTES = 5_000_000
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/sw.js": ("sw.js", "text/javascript; charset=utf-8"),
}
LANGUAGE_FILE = re.compile(r"/i18n/([a-z]{2}(?:-[a-z]{2})?)\.json")
EVENT_TYPES = ("play", "finish", "skip")


class NotFound(Exception):
    pass


def make_handler(service, port):
    """Builds the request handler around a service. The routes are plain functions: body in, JSON out."""
    store, yt, config = service.store, service.yt, service.config
    url = f"http://localhost:{port}/"
    allowed_hosts = {f"localhost:{port}", f"127.0.0.1:{port}"}

    def active_profile():
        return service.profiles.active if service.profiles else None

    def bootstrap():
        """Everything the page needs to draw itself when it loads."""
        running = service.startup_job and service.startup_job["status"] == "running"
        return {
            **service.queue_state(),
            "sources": store.sources(),
            "reactions": store.reactions(),
            "genres": list(GENRES),
            "ui": store.get("ui", {}),
            "auto_job": service.startup_job["id"] if running else None,
            "settings": settings(),
            "profile": active_profile(),
        }

    def ping():
        """Polled by every open page: is the server on, and has anything changed elsewhere?"""
        return {
            "profile": (active_profile() or {}).get("id"),
            "language": i18n.language(),
            "last_import": service.last_import,
        }

    def settings():
        check_updates = config.get("check_updates", True)
        return {
            "lastfm": bool(config.get("lastfm_key")),
            "youtube": bool(config.get("youtube_key")),
            "account": bool(yt.account),
            "tray": config.get("tray", True),
            "tray_available": tray.available(),
            "language": i18n.language(),
            "languages": i18n.available(),
            "open_mode": config.get("open_mode", "browser"),
            "window_available": launcher.window_available(),
            "version": VERSION,
            "check_updates": check_updates,
            "update": service.updates.info() if service.updates and check_updates else None,
        }

    def save_settings(body):
        values = {key: str(body[key]).strip() for key in ("lastfm_key", "youtube_key") if key in body}
        if "tray" in body:
            values["tray"] = bool(body["tray"])
            if service.tray:
                service.tray.show() if values["tray"] else service.tray.hide()
        if "open_mode" in body:
            values["open_mode"] = body["open_mode"] if body["open_mode"] in launcher.MODES else "browser"
        if "check_updates" in body:
            values["check_updates"] = bool(body["check_updates"])
            if values["check_updates"] and service.updates:
                service.updates.check_in_background()
        if "language" in body:
            if not i18n.is_available(body["language"]):
                raise UserError(t("err.bad_language"))
            values["language"] = body["language"]
            i18n.set_language(body["language"])
            if service.tray:
                service.tray.refresh()
        config.update(values)
        return settings()

    def login(body):
        try:
            yt.login(body.get("headers", ""))
        except Exception as error:
            yt.logout()
            raise UserError(t("err.account", error=error)) from error
        return settings()

    def logout(_):
        yt.logout()
        return settings()

    def event(body):
        if body.get("video_id") and body.get("type") in EVENT_TYPES:
            store.log_event(body["video_id"], body["type"], body.get("position", 0), body.get("duration", 0))
        return {}

    def react(body):
        if body.get("video_id"):
            store.react(body["video_id"], int(body.get("value", 0)))
        return {}

    def forget(body):
        if body.get("event_id"):
            store.delete_event(int(body["event_id"]))
            return {}
        return service.forget_artist(body.get("artist", ""))

    def import_tracks(body):
        """Used by the bookmarklet. Noted down so every open page, wherever it is, finds out through ping."""
        result = service.import_tracks(body.get("name"), body.get("tracks") or [])
        service.last_import = {**result, "at": time.time(), "profile": (active_profile() or {}).get("id")}
        return result

    def open_elsewhere(body):
        launcher.open_ui(url, body.get("mode") if body.get("mode") in launcher.MODES else "browser")
        return {}

    def save_ui(body):
        store.put("ui", {**store.get("ui", {}), **body})
        return {}

    def source_action(source_id, action, body):
        if action == "refresh":
            return service.jobs.start(service.refresh, source_id)
        if action == "rename":
            return service.rename_source(source_id, body.get("name"))
        if action == "auto":
            return service.set_auto_update(source_id, bool(body.get("value")))
        if action == "play":
            return service.play_source(source_id, bool(body.get("shuffle")))
        store.delete_source(source_id)
        return {}

    routes_get = {
        "/api/bootstrap": bootstrap,
        "/api/ping": ping,
        "/api/history": lambda: store.history(),  # looked up on every call: the store follows the profile in use
        "/api/profile": service.profile,
        "/api/profiles": service.profiles_state,
    }
    routes_post = {
        # Lists
        "/api/import": lambda b: service.jobs.start(service.import_url, b.get("url", ""), b.get("name")),
        "/api/import-tracks": import_tracks,
        "/api/import-account": lambda b: service.jobs.start(service.import_account),
        "/api/generate": lambda b: service.jobs.start(service.generate, b),
        # Queue and player
        "/api/shuffle": lambda b: service.shuffle(b.get("source_ids", []), b.get("avoid_recent", False)),
        "/api/queue/order": lambda b: service.reorder(bool(b.get("shuffle")), b.get("video_id")),
        "/api/queue/save": lambda b: {"source_id": service.save_queue(b.get("name") or t("name.my_queue"))},
        "/api/state": lambda b: service.save_player(b.get("index", 0), b.get("time", 0)),
        "/api/error": lambda b: service.report_error(b.get("video_id"), int(b.get("code", 0))),
        # Learning
        "/api/event": event,
        "/api/react": react,
        "/api/forget": forget,
        "/api/artist-pref": lambda b: service.set_artist_pref(b.get("artist", ""), b.get("name", ""), int(b.get("value", 0))),
        # Profiles
        "/api/profiles/switch": lambda b: service.switch_profile(b.get("id", "")),
        "/api/profiles/create": lambda b: service.create_profile(b.get("name", ""), bool(b.get("copy_lists"))),
        "/api/profiles/rename": lambda b: service.rename_profile(b.get("id", ""), b.get("name", "")),
        "/api/profiles/delete": lambda b: service.delete_profile(b.get("id", "")),
        # Settings and the app itself
        "/api/settings": save_settings,
        "/api/login": login,
        "/api/logout": logout,
        "/api/ui": save_ui,
        "/api/open": open_elsewhere,
        "/api/updates/check": lambda b: service.updates.check() if service.updates else {},
    }

    def api_get(path):
        if path in routes_get:
            return routes_get[path]()
        match = re.fullmatch(r"/api/jobs/(\d+)", path)
        if match:
            return service.jobs.get(int(match[1])) or {"status": "error", "message": t("err.job_lost")}
        match = re.fullmatch(r"/api/year/([\w-]{11})", path)
        if match:
            return service.track_year(match[1])
        raise NotFound

    def api_post(path, body):
        if path in routes_post:
            return routes_post[path](body)
        match = re.fullmatch(r"/api/sources/(\d+)/(refresh|rename|delete|play|auto)", path)
        if match:
            return source_action(int(match[1]), match[2], body)
        raise NotFound

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # one line per request would bury what matters in the log

        def _send(self, status, body, content_type="application/json; charset=utf-8", headers=()):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for name, value in headers:
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, value, status=200):
            self._send(status, json.dumps(value, ensure_ascii=False).encode("utf-8"))

        def _file(self, path, content_type):
            with open(path, "rb") as f:
                self._send(200, f.read(), content_type)

        def _allowed(self):
            """Keeps any other website open in the browser from calling the app."""
            origin = self.headers.get("Origin", "")
            return self.headers.get("Host") in allowed_hosts and (
                not origin or origin.split("://", 1)[-1] in allowed_hosts
            )

        def _api(self, fn):
            """Runs an API route and answers with its result, or with an error the page can show."""
            if not self._allowed():
                return self._json({"error": t("err.origin")}, 403)
            try:
                self._json(fn())
            except NotFound:
                self._json({"error": t("err.not_found")}, 404)
            except UserError as error:
                self._json({"error": str(error)}, 400)
            except Exception as error:
                traceback.print_exc()
                self._json({"error": t("err.unexpected", error=error)}, 500)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in STATIC:
                name, content_type = STATIC[path]
                return self._file(os.path.join(WEB, name), content_type)
            match = LANGUAGE_FILE.fullmatch(path)
            if match and i18n.is_available(match[1]):
                return self._file(os.path.join(WEB, "i18n", f"{match[1]}.json"), "application/json; charset=utf-8")
            if path == "/api/export":
                return self._export()
            self._api(lambda: api_get(path))

        def _export(self):
            if not self._allowed():
                return self._json({"error": t("err.origin")}, 403)
            body = json.dumps(store.export(), ensure_ascii=False, indent=1).encode("utf-8")
            name = time.strftime("youmixer-%Y%m%d.json")
            self._send(200, body, headers=[("Content-Disposition", f'attachment; filename="{name}"')])

        def do_POST(self):
            path = self.path.split("?")[0]
            length = int(self.headers.get("Content-Length") or 0)
            if length > BODY_MAX_BYTES:
                return self._json({"error": t("err.bad_json")}, 413)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                return self._json({"error": t("err.bad_json")}, 400)
            if not isinstance(body, dict):
                return self._json({"error": t("err.bad_json")}, 400)
            if path == "/api/shutdown":
                if not self._allowed():
                    return self._json({"error": t("err.origin")}, 403)
                self._json({})
                log("Turned off from the page")
                # From another thread: shutdown() waits for the request loop, and we are inside it
                return threading.Thread(target=self.server.shutdown).start()
            self._api(lambda: api_post(path, body))

    return Handler


def running_instance(port):
    """'youmixer' if YouMixer already answers on the port, 'other' if another program has it, None if it is free."""
    with socket.socket() as probe:
        probe.settimeout(0.5)
        if probe.connect_ex(("127.0.0.1", port)) != 0:
            return None
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=3) as response:
            return "youmixer" if "profile" in json.load(response) else "other"
    except (OSError, ValueError):
        return "other"


def alert(text):
    """A message the user must see even when there is no console (started with pythonw)."""
    log(text)
    if sys.platform == "win32" and os.environ.get("YOUMIXER_NO_LAUNCH") != "1":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, "YouMixer", 0x30)


def quit_running(port):
    """Asks a YouMixer that is already running to turn itself off. True if one was there."""
    if running_instance(port) != "youmixer":
        return False
    request = urllib.request.Request(
        f"http://localhost:{port}/api/shutdown", data=b"{}", headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(request, timeout=5).read()
    except OSError:
        return False
    for _ in range(40):  # up to 10 s for it to let go of the port
        time.sleep(0.25)
        if running_instance(port) is None:
            break
    return True


def log_to_file():
    """Without a window (pythonw) there is no console: messages and errors go to data/youmixer.log."""
    os.makedirs(DATA, exist_ok=True)
    path = os.path.join(DATA, "youmixer.log")
    if os.path.exists(path) and os.path.getsize(path) > LOG_MAX_BYTES:
        os.replace(path, path + ".old")
    sys.stdout = sys.stderr = open(path, "a", encoding="utf-8", buffering=1)


def main():
    if sys.stdout is None:
        log_to_file()
    else:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    if "--quit" in sys.argv:
        quit_running(PORT)
        return
    open_page_on_start = "--no-browser" not in sys.argv
    url = f"http://localhost:{PORT}/"
    config = Config(os.path.join(DATA, "config.json"))
    i18n.set_language(config.get("language") or i18n.system_language())

    running = running_instance(PORT)
    if running == "youmixer":
        # Already on: opening it again just shows the page
        if open_page_on_start:
            launcher.open_ui(url, config.get("open_mode", "browser"))
        return
    if running == "other":
        return alert(t("err.port_busy", port=PORT))

    from youmixer.ytclient import YT  # imported late: it is the slow one, and not needed above

    profiles = Profiles(DATA)
    store = ActiveStore(profiles)
    service = Service(store, YT(store, DATA, config), config)
    service.profiles = profiles
    service.updates = Updates()
    service.startup_job = service.jobs.start(service.auto_update, background=True)
    if config.get("check_updates", True):
        service.updates.check_in_background()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), make_handler(service, PORT))

    def quit_from_tray():
        log("Turned off from the tray icon")
        threading.Thread(target=server.shutdown).start()

    def switch_from_tray(profile_id):
        try:
            service.switch_profile(profile_id)
        except UserError as error:
            log("Profile switch from the tray icon refused:", error)

    def open_page(mode=None):
        launcher.open_ui(url, mode or config.get("open_mode", "browser"))

    service.tray = tray.Tray({
        "open": open_page,
        "on_quit": quit_from_tray,
        "profiles": lambda: (profiles.data["active"], list(profiles.data["profiles"])),
        "switch_profile": switch_from_tray,
        "window_available": launcher.window_available,
    })
    # Tests set YOUMIXER_TRAY=0: a killed instance would leave a ghost icon next to the clock
    if config.get("tray", True) and os.environ.get("YOUMIXER_TRAY") != "0":
        service.tray.show()
    log(f"YouMixer {VERSION} running at {url}")
    if open_page_on_start:
        threading.Timer(0.5, open_page).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        service.tray.hide()
        service.jobs.stop()
        profiles.close_all()


if __name__ == "__main__":
    main()
    # A task may still be waiting between retries with YouTube; don't keep the process alive for it
    os._exit(0)
