"""YouMixer's tests. They never touch the network: YouTube is replaced by FakeYT.

Run them with: .venv\Scripts\python.exe -m unittest discover -s tests
"""
import collections
import json
import os
import random
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from http.server import ThreadingHTTPServer

from server import make_handler
from youmixer import engine, i18n
from youmixer.service import Service, UserError
from youmixer.store import Store


def track(n, artist=None, title=None):
    return {"video_id": f"v{n:010d}", "title": title or f"Tema {n}", "artist": artist or f"Artista {n}", "duration": 200, "thumb": ""}


class FakeYT:
    account = None

    def __init__(self, radio_tracks=(), block_alt=None):
        self.radio_tracks = list(radio_tracks)
        self.block_alt = block_alt

    def playlist(self, playlist_id):
        return "Lista", [track(i) for i in range(1, 6)]

    def mix(self, playlist_id, video_id):
        return [track(i) for i in range(10, 13)]

    def radio(self, video_id):
        return self.radio_tracks

    def term_pool(self, term):
        return [track(i, "Tema") for i in range(300, 305)]

    def similar_artists(self, artist):
        return {}

    def find_alternative(self, item):
        return self.block_alt



class ParseUrl(unittest.TestCase):
    def test_links(self):
        cases = {
            "https://www.youtube.com/playlist?list=PLabc123": ("playlist", "PLabc123"),
            "https://music.youtube.com/playlist?list=OLAK5uy_abc": ("playlist", "OLAK5uy_abc"),
            "https://www.youtube.com/watch?v=3kMbTzomh94&list=RD3kMbTzomh94&start_radio=1": ("mix", "RD3kMbTzomh94"),
            "https://www.youtube.com/watch?v=3kMbTzomh94&list=PLabc123": ("playlist", "PLabc123"),
        }
        for url, (kind, ref) in cases.items():
            result = engine.parse_url(url)
            self.assertEqual((result["kind"], result["list"]), (kind, ref))

    def test_video_and_mix_id(self):
        self.assertEqual(engine.parse_url("https://youtu.be/3kMbTzomh94?si=x")["video"], "3kMbTzomh94")
        self.assertEqual(engine.parse_url("3kMbTzomh94")["kind"], "video")
        self.assertEqual(engine.parse_url("https://www.youtube.com/watch?list=RD3kMbTzomh94")["video"], "3kMbTzomh94")

    def test_rejects_others(self):
        self.assertIsNone(engine.parse_url("https://example.com/watch?v=3kMbTzomh94"))
        self.assertIsNone(engine.parse_url("https://notyoutube.com/watch?v=3kMbTzomh94"))

    def test_curated_playlists_are_playlists(self):
        self.assertEqual(engine.parse_url("RDCLAK5uy_abc")["kind"], "playlist")
        self.assertEqual(engine.parse_url("https://music.youtube.com/playlist?list=RDCLAK5uy_abc")["kind"], "playlist")
        self.assertIsNone(engine.parse_url(""))


i18n.set_language("es")  # some tests check specific texts


class Languages(unittest.TestCase):
    def test_all_languages_have_the_same_keys_and_placeholders(self):
        import re

        files = {lang["code"]: i18n._load(lang["code"]) for lang in i18n.available()}
        self.assertIn("es", files)
        self.assertIn("en", files)
        reference = files["en"]
        for code, texts in files.items():
            self.assertEqual(set(texts), set(reference), code)
            for key, text in texts.items():
                self.assertEqual(set(re.findall(r"{(\w+)}", text)), set(re.findall(r"{(\w+)}", reference[key])), f"{code}: {key}")

    def test_welcome_tour_has_texts_and_pictures(self):
        web = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
        texts = i18n._load("en")
        for step in (1, 2, 3):
            self.assertIn(f"welcome.s{step}_title", texts)
            self.assertIn(f"welcome.s{step}_text", texts)
            # English is what the page falls back to when a language has no pictures of its own
            self.assertTrue(os.path.exists(os.path.join(web, "welcome", f"en-{step}.png")), step)

    def test_translation_and_fallback(self):
        i18n.set_language("en")
        try:
            self.assertEqual(i18n.t("job.searching", term="Rock"), "Searching “Rock”…")
            self.assertEqual(i18n.t("no.such.key"), "no.such.key")
        finally:
            i18n.set_language("es")
        self.assertEqual(i18n.t("tray.open"), "Abrir YouMixer")


class ReleaseYear(unittest.TestCase):
    def page(self, description, upload="2019-05-01"):
        return f'"shortDescription":{json.dumps(description)},"uploadDate":"{upload}T00:00:00"'

    def test_copyright_wins(self):
        html = self.page("Provided to YouTube\n\n℗ 2017 Square Enix\n\nReleased on: 2018-02-24")
        self.assertEqual(engine.release_year(html), (2017, "copyright"))

    def test_release_when_copyright_has_no_year(self):
        html = self.page("℗ Sandfall Interactive under license\n\nReleased on: 2025-04-24")
        self.assertEqual(engine.release_year(html), (2025, "released"))

    def test_upload_as_last_resort(self):
        self.assertEqual(engine.release_year(self.page("Official video")), (2019, "upload"))
        self.assertEqual(engine.release_year("nada"), (None, None))


class ConfigFile(unittest.TestCase):
    def test_settings_survive_restart_and_bad_files(self):
        from youmixer.config import Config

        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "data", "config.json")
            config = Config(path)
            self.assertEqual(config.get("tray", True), True)
            config.update({"tray": False, "language": "en"})
            self.assertEqual(Config(path).get("language"), "en")
            self.assertFalse(os.path.exists(path + ".tmp"))
            with open(path, "w", encoding="utf-8") as f:
                f.write("{broken")
            self.assertEqual(Config(path).get("tray", True), True)

    def test_memory_only(self):
        from youmixer.config import Config

        config = Config()
        config.update({"a": 1})
        self.assertEqual(config.get("a"), 1)


class Shuffle(unittest.TestCase):
    def test_keeps_every_song_once(self):
        tracks = [track(i) for i in range(200)]
        result = engine.true_shuffle(tracks)
        self.assertEqual(sorted(t["video_id"] for t in result), sorted(t["video_id"] for t in tracks))

    def test_is_uniform(self):
        tracks = [track(i) for i in range(4)]
        firsts = collections.Counter(engine.true_shuffle(tracks, rng=random.Random(i))[0]["video_id"] for i in range(4000))
        for count in firsts.values():
            self.assertAlmostEqual(count / 4000, 0.25, delta=0.03)

    def test_spaces_artists(self):
        tracks = [track(i, "A") for i in range(5)] + [track(i, f"B{i}") for i in range(5, 25)]
        result = engine.true_shuffle(tracks)
        for first, second in zip(result, result[1:]):
            self.assertFalse(first["artist"] == second["artist"] == "A")

    def test_avoid_moves_recent_out_of_the_start(self):
        tracks = [track(i) for i in range(100)]
        avoid = [t["video_id"] for t in tracks[:20]]
        result = engine.true_shuffle(tracks, avoid)
        self.assertFalse(set(avoid) & {t["video_id"] for t in result[:30]})

    def test_dedupe_versions(self):
        tracks = [track(1, "X", "Lemon"), track(2, "X", "Lemon (Official Video)"), track(1, "Y", "Otra"), track(3, "X", "Otra")]
        self.assertEqual([t["video_id"] for t in engine.dedupe(tracks)], [tracks[0]["video_id"], tracks[3]["video_id"]])


class Recommend(unittest.TestCase):
    def test_affinity_rewards_and_punishes(self):
        by_id = {t["video_id"]: t for t in [track(1, "Bueno"), track(2, "Malo")]}
        now = time.time()
        events = [
            {"video_id": track(1)["video_id"], "type": "finish", "at": now, "position": 200, "duration": 200},
            {"video_id": track(2)["video_id"], "type": "skip", "at": now, "position": 5, "duration": 200},
            {"video_id": track(2)["video_id"], "type": "skip", "at": now, "position": 150, "duration": 200},
        ]
        scores = engine.artist_affinity(events, {track(1)["video_id"]: 1}, by_id, now)
        self.assertEqual(scores["bueno"], 4)
        self.assertEqual(scores["malo"], -1.5)

    def test_seeds_rotate(self):
        pool = [track(i) for i in range(30)]
        used = {t["video_id"]: time.time() for t in pool[:24]}
        seeds = engine.pick_seeds(pool, {}, set(), used, 6, rng=random.Random(1))
        self.assertGreaterEqual(sum(t["video_id"] not in used for t in seeds), 4)

    def test_compose_respects_ratio_and_fills_gaps(self):
        new = [track(i) for i in range(50)]
        old = [track(i) for i in range(100, 150)]
        mixed = engine.compose(new, old, 10, 30)
        self.assertEqual(sum(t in new for t in mixed), 3)
        self.assertEqual(len(mixed), 10)
        self.assertEqual(len(engine.compose(new[:2], old, 10, 100)), 10)
        self.assertEqual(len(engine.compose(new, old[:1], 10, 0)), 10)


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.dir.name, "test.db"))
        self.yt = FakeYT()
        self.service = Service(self.store, self.yt)
        self.addCleanup(self.dir.cleanup)
        self.addCleanup(self.store.close)
        self.addCleanup(self.service.jobs.pool.shutdown)

    def source(self, tracks, kind="playlist"):
        return self.store.create_source(kind, "Lista", None, tracks)


class ServiceFlow(Base):
    def test_shuffle_several_sources_without_repeats(self):
        a = self.source([track(i) for i in range(10)])
        b = self.source([track(i) for i in range(5, 15)])
        queue = self.service.shuffle([a, b])["queue"]
        self.assertEqual(len({t["video_id"] for t in queue}), 15)

    def test_import_twice_updates_instead_of_duplicating(self):
        url = "https://www.youtube.com/playlist?list=PLabc"
        first = self.service.import_url(lambda _: None, url)
        second = self.service.import_url(lambda _: None, url)
        self.assertEqual(first["source_id"], second["source_id"])
        self.assertEqual(len(self.store.sources()), 1)

    def test_auto_update_defaults_and_runs_only_when_due(self):
        noop = lambda _: None
        playlist = self.service.import_url(noop, "https://www.youtube.com/playlist?list=PLabc")["source_id"]
        mix = self.service.import_url(noop, "https://www.youtube.com/watch?v=3kMbTzomh94&list=RD3kMbTzomh94")["source_id"]
        flags = {s["id"]: s["auto_update"] for s in self.store.sources()}
        self.assertEqual((flags[playlist], flags[mix]), (True, False))

        self.yt.playlist = lambda _: ("Lista", [track(i) for i in range(1, 9)])
        self.assertEqual(self.service.auto_update(noop)["count"], 0)
        self.store.db.execute("UPDATE sources SET updated_at=0")
        self.assertEqual(self.service.auto_update(noop)["count"], 1)
        self.assertEqual(len(self.store.source_tracks(playlist)), 8)
        self.assertEqual(len(self.store.source_tracks(mix)), 3)

        self.service.set_auto_update(playlist, False)
        self.service.set_auto_update(mix, True)
        self.store.db.execute("UPDATE sources SET updated_at=0")
        flags = {s["id"]: s["auto_update"] for s in self.store.sources()}
        self.assertEqual((flags[playlist], flags[mix]), (False, True))
        self.assertEqual(self.service.auto_update(noop)["count"], 1)

    def test_import_tracks_from_browser(self):
        items = [["3kMbTzomh94", "Une vie", "Lorien"], ["3kMbTzomh94", "Repe", "X"], ["mal", "x", "y"],
                 ["iqizXvvWnmM", "Lumière", "Lorien"], "basura"]
        result = self.service.import_tracks("  Mi mix  ", items)
        self.assertEqual((result["name"], result["count"]), ("Mi mix", 2))
        source = self.store.sources()[0]
        self.assertEqual((source["kind"], source["auto_update"]), ("mix", False))
        with self.assertRaises(UserError):
            self.service.import_tracks("x", [])

    def test_mix_snapshot_survives_when_source_is_gone(self):
        result = self.service.import_url(lambda _: None, "https://www.youtube.com/watch?v=3kMbTzomh94&list=RD3kMbTzomh94")
        self.yt.mix = lambda *_: []
        self.service.refresh(lambda _: None, result["source_id"])
        self.assertEqual(len(self.store.source_tracks(result["source_id"])), 3)

    def test_discovery_excludes_known_and_disliked(self):
        library = [track(i) for i in range(10)]
        self.source(library)
        fresh = [track(i, f"Nuevo {i}") for i in range(100, 160)]
        self.yt.radio_tracks = library + fresh + [track(500, "Odiado"), track(501, "Odiado")]
        self.store.upsert_tracks([track(500, "Odiado")])
        self.store.react(track(500)["video_id"], -1)
        result = self.service.generate(lambda _: None, {"explore": 100, "size": 30})
        ids = {t["video_id"] for t in result["queue"]}
        self.assertEqual(len(ids), 30)
        self.assertFalse(ids & {t["video_id"] for t in library})
        self.assertNotIn(track(500)["video_id"], ids)
        self.assertEqual(len(self.store.seed_uses()), 6)

    def test_generate_without_anything_explains(self):
        with self.assertRaises(UserError):
            self.service.generate(lambda _: None, {"explore": 100})

    def test_generate_from_terms(self):
        result = self.service.generate(lambda _: None, {"terms": ["Expedition 33"], "explore": 100, "size": 10})
        self.assertEqual(len(result["queue"]), 5)

    def test_blocked_video_gets_alternative_then_gives_up(self):
        self.store.upsert_tracks([track(1)])
        self.yt.block_alt = track(2)
        video_id = track(1)["video_id"]
        self.assertEqual(self.service.report_error(video_id, 150)["play_id"], track(2)["video_id"])
        self.assertEqual(self.service.report_error(video_id, 150)["action"], "skip")
        self.assertEqual(self.store.track(video_id)["unplayable"], 1)

    def test_browser_errors_do_not_condemn_the_video(self):
        self.store.upsert_tracks([track(1)])
        self.service.report_error(track(1)["video_id"], 153)
        self.assertEqual(self.store.track(track(1)["video_id"])["unplayable"], 0)

    def test_shuffle_toggle_keeps_current_song(self):
        a = self.source([track(i) for i in range(30)])
        self.service.play_source(a, shuffle=True)
        current = self.store.queue()[7]["video_id"]
        ordered = self.service.reorder(False, current)
        self.assertEqual([t["video_id"] for t in ordered["queue"]], [track(i)["video_id"] for i in range(30)])
        self.assertEqual(ordered["queue"][ordered["player"]["index"]]["video_id"], current)
        shuffled = self.service.reorder(True, current)
        self.assertEqual(shuffled["player"]["index"], 0)
        self.assertEqual(shuffled["queue"][0]["video_id"], current)
        self.assertEqual(len(shuffled["queue"]), 30)

    def test_forget_artist_and_single_entry(self):
        self.store.upsert_tracks([track(1, "Pruebas"), track(2, "Pruebas"), track(3, "Otro")])
        for n in (1, 2, 3):
            self.store.log_event(track(n)["video_id"], "skip", 3, 200)
        self.store.react(track(1)["video_id"], -1)
        self.assertTrue(any(a["key"] == "pruebas" for a in self.service.profile()["avoid"]))
        self.assertEqual(self.service.forget_artist("pruebas")["count"], 2)
        self.assertFalse(any(a["key"] == "pruebas" for a in self.service.profile()["avoid"]))
        self.assertEqual(self.store.reactions(), {})
        self.store.delete_event(self.store.history()[0]["id"])
        self.assertEqual(self.store.history(), [])

    def test_artist_pref_overrides_learning(self):
        self.store.upsert_tracks([track(1, "Destripando"), track(2, "Destripando"), track(3, "Otro")])
        for n in (1, 2):
            self.store.log_event(track(n)["video_id"], "skip", 5, 300)
        for _ in range(8):
            self.store.log_event(track(3)["video_id"], "finish", 200, 200)
        profile = self.service.profile()
        self.assertEqual([a["key"] for a in profile["avoid"]], ["destripando"])

        self.service.set_artist_pref("destripando", "Destripando", 1)
        profile = self.service.profile()
        self.assertEqual(profile["avoid"], [])
        self.assertTrue(next(a for a in profile["top"] if a["key"] == "destripando")["pinned"])

        self.service.set_artist_pref("otro", "Otro", -1)
        profile = self.service.profile()
        self.assertEqual([a["key"] for a in profile["avoid"]], ["otro"])
        self.assertNotIn("otro", [a["key"] for a in profile["top"]])

        self.service.forget_artist("otro")
        self.assertNotIn("otro", self.store.artist_prefs())
        self.assertEqual(self.service.profile()["avoid"], [])

    def test_discovery_respects_avoided_artist(self):
        self.source([track(i) for i in range(5)])
        self.yt.radio_tracks = [track(i, "Vetado") for i in range(100, 110)] + [track(i, f"Bueno {i}") for i in range(200, 230)]
        self.service.set_artist_pref("vetado", "Vetado", -1)
        result = self.service.generate(lambda _: None, {"explore": 100, "size": 20})
        self.assertFalse([t for t in result["queue"] if t["artist"] == "Vetado"])

    def test_year_failure_is_not_remembered(self):
        self.store.upsert_tracks([track(1)])
        video_id = track(1)["video_id"]

        def broken(_):
            raise RuntimeError("no network")

        self.yt.release_year = broken
        self.assertEqual(self.service.track_year(video_id), {"year": 0, "kind": None})
        self.assertIsNone(self.store.track(video_id)["year_kind"])
        self.yt.release_year = lambda _: (2017, "copyright")
        self.assertEqual(self.service.track_year(video_id), {"year": 2017, "kind": "copyright"})
        self.yt.release_year = broken
        self.assertEqual(self.service.track_year(video_id)["year"], 2017)

    def test_many_tracks_by_ids_and_export(self):
        tracks = [track(n) for n in range(1200)]
        self.store.upsert_tracks(tracks)
        self.assertEqual(len(self.store.tracks_by_ids([t["video_id"] for t in tracks])), 1200)
        self.store.set_artist_pref("x", "X", 1)
        self.assertEqual(self.store.export()["artist_prefs"][0]["artist"], "x")

    def test_unplayable_is_left_out(self):
        a = self.source([track(1), track(2)])
        self.store.mark_unplayable(track(1)["video_id"])
        self.assertEqual(len(self.service.shuffle([a])["queue"]), 1)


class ProfilesTest(unittest.TestCase):
    def setUp(self):
        from youmixer.profiles import ActiveStore, Profiles

        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.profiles = Profiles(self.dir.name)
        self.addCleanup(self.profiles.close_all)
        self.store = ActiveStore(self.profiles)
        self.service = Service(self.store, FakeYT())
        self.service.profiles = self.profiles
        self.addCleanup(self.service.jobs.pool.shutdown)

    def test_main_profile_keeps_existing_database(self):
        self.assertEqual(self.profiles.active["name"], "Principal")
        self.assertTrue(os.path.exists(os.path.join(self.dir.name, "youmixer.db")))

    def test_profiles_are_isolated_and_copy_only_lists(self):
        self.store.create_source("playlist", "Mi lista", None, [track(1), track(2)])
        self.store.log_event(track(1)["video_id"], "finish", 200, 200)
        self.store.react(track(1)["video_id"], 1)

        self.service.create_profile("Con amigos", copy_lists=True)
        self.assertEqual(self.profiles.active["name"], "Con amigos")
        self.assertEqual([s["name"] for s in self.store.sources()], ["Mi lista"])
        self.assertEqual(len(self.store.source_tracks(self.store.sources()[0]["id"])), 2)
        self.assertEqual(self.store.events(), [])
        self.assertEqual(self.store.reactions(), {})

        self.store.react(track(2)["video_id"], -1)
        self.service.switch_profile("principal")
        self.assertEqual(self.store.reactions(), {track(1)["video_id"]: 1})

        self.service.create_profile("Rock", copy_lists=False)
        self.assertEqual(self.store.sources(), [])

    def test_copied_lists_keep_their_order(self):
        for name in ("Primera", "Segunda", "Tercera"):
            self.store.create_source("playlist", name, None, [track(1)])
            time.sleep(0.01)
        before = [source["name"] for source in self.store.sources()]
        self.service.create_profile("Copia", copy_lists=True)
        self.assertEqual([source["name"] for source in self.store.sources()], before)

    def test_rename_and_delete(self):
        self.service.create_profile("Rock", copy_lists=False)
        rock = self.profiles.active["id"]
        with self.assertRaises(UserError):
            self.service.delete_profile(rock)
        with self.assertRaises(UserError):
            self.service.delete_profile("principal")
        self.service.switch_profile("principal")
        with self.assertRaises(UserError):
            self.service.create_profile("rock", copy_lists=False)
        self.service.rename_profile(rock, "Rock clásico")
        self.assertEqual(self.profiles.find(rock)["name"], "Rock clásico")
        self.service.delete_profile(rock)
        self.assertNotIn(rock, [p["id"] for p in self.profiles.list()["profiles"]])
        self.assertEqual(len(os.listdir(os.path.join(self.dir.name, "backups", "deleted"))), 1)

    def test_active_profile_survives_restart(self):
        from youmixer.profiles import Profiles

        self.service.create_profile("Para trabajar", copy_lists=False)
        self.profiles.close_all()
        again = Profiles(self.dir.name)
        self.addCleanup(again.close_all)
        self.assertEqual(again.active["name"], "Para trabajar")


class Persistence(Base):
    def test_everything_survives_restart(self):
        a = self.source([track(1), track(2)])
        self.service.shuffle([a])
        self.store.react(track(1)["video_id"], 1)
        self.store.log_event(track(1)["video_id"], "finish", 200, 200)
        self.store.put("player", {"index": 1, "time": 42, "source_ids": [a]})
        self.store.close()
        reopened = Store(self.store.path)
        self.addCleanup(reopened.close)
        self.store = reopened
        self.service.store = reopened
        self.assertEqual(len(reopened.queue()), 2)
        self.assertEqual(reopened.get("player")["time"], 42)
        self.assertEqual(reopened.reactions(), {track(1)["video_id"]: 1})
        self.assertEqual(len(reopened.events()), 1)

    def test_backup_rotates_and_restores(self):
        self.source([track(1)])
        folder = os.path.join(self.dir.name, "backups")
        for i in range(12):
            with open(os.path.join(folder if os.path.isdir(folder) else self._mk(folder), f"youmixer-2020010{i:02d}.db"), "w"):
                pass
        target = self.store.backup(folder)
        self.assertEqual(len(os.listdir(folder)), 10)
        restored = Store(target)
        self.addCleanup(restored.close)
        self.assertEqual(len(restored.sources()), 1)

    @staticmethod
    def _mk(folder):
        os.makedirs(folder)
        return folder


class Http(Base):
    def setUp(self):
        super().setUp()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.service, 0))
        self.server.RequestHandlerClass = make_handler(self.service, self.server.server_port)
        self.port = self.server.server_port
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def call(self, path, body=None, headers=None):
        request = urllib.request.Request(
            f"http://localhost:{self.port}{path}",
            data=None if body is None else json.dumps(body).encode(),
            headers=headers or {},
        )
        with urllib.request.urlopen(request) as response:
            return json.load(response)

    def test_import_job_and_bootstrap(self):
        job = self.call("/api/import", {"url": "https://www.youtube.com/playlist?list=PLabc"})
        for _ in range(100):
            job = self.call(f"/api/jobs/{job['id']}")
            if job["status"] != "running":
                break
            time.sleep(0.02)
        self.assertEqual(job["status"], "done")
        self.assertEqual(self.call("/api/bootstrap")["sources"][0]["count"], 5)

    def test_rejects_other_origins(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.call("/api/bootstrap", headers={"Origin": "https://evil.example"})
        self.assertEqual(caught.exception.code, 403)

    def test_routes_follow_the_profile_in_use_and_unknown_ones_are_404(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.call("/api/nothing-here")
        self.assertEqual(caught.exception.code, 404)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.call("/api/sources/1/rename", {"name": "  "})
        self.assertEqual(caught.exception.code, 400)
        self.assertEqual(self.call("/api/history"), [])

    def test_user_errors_are_readable(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.call("/api/shuffle", {"source_ids": []})
        self.assertEqual(caught.exception.code, 400)
        self.assertIn("mezclar", json.load(caught.exception)["error"])


if __name__ == "__main__":
    unittest.main()


class UpdatesAndTray(unittest.TestCase):
    def test_version_comparison(self):
        from youmixer import updates

        self.assertTrue(updates.is_newer("v1.0.1", "1.0.0"))
        self.assertTrue(updates.is_newer("1.1", "1.0.9"))
        self.assertFalse(updates.is_newer("v1.0.0", "1.0.0"))
        self.assertFalse(updates.is_newer("0.9.9", "1.0.0"))
        self.assertEqual(updates.parse("v2"), (2, 0, 0))

    def test_tray_menu_has_profiles_and_follows_language(self):
        from youmixer import tray

        if not tray.available():
            self.skipTest("pystray no instalado")
        switched = []
        icon = tray.Tray({
            "open": lambda mode: None, "on_quit": lambda: None, "window_available": lambda: True,
            "profiles": lambda: ("rock", [{"id": "principal", "name": "Principal"}, {"id": "rock", "name": "Rock"}]),
            "switch_profile": switched.append,
        })
        menu = icon._menu()
        self.assertEqual([item.text for item in menu.items if item.text][:3],
                         ["Abrir YouMixer", "Abrir en el navegador", "Abrir en ventana propia"])
        profiles = [item for item in menu.items if item.text == "Perfil"][0].submenu
        names = [(item.text, item.checked) for item in profiles.items]
        self.assertEqual(names, [("Principal", False), ("Rock", True)])
        profiles.items[0](None)
        self.assertEqual(switched, ["principal"])
        i18n.set_language("en")
        try:
            self.assertEqual(menu.items[0].text, "Open YouMixer")
        finally:
            i18n.set_language("es")
