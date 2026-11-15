"""What the app does: import lists, build queues, generate mixes and learn from listening."""
import collections
import itertools
import time
from concurrent.futures import ThreadPoolExecutor

from . import engine, log
from .config import Config
from .i18n import t
from .profiles import ProfileError

SEEDS_PER_MIX = 6
RECENT_DAYS = 3
AUTO_UPDATE_EVERY = 6 * 3600
BLOCK_CODES = {100, 101, 150}  # player errors that mean "this video can't be played here"
AVOID_BELOW = -3  # artists scoring this low are left out of what YouMixer picks
DISCOVERY_EXPLORE = 80  # from this share of new songs up, a mix without topics is a "discovery"
# Genres: id → YouTube search. The visible name comes from the language files (genre.<id>).
GENRES = {
    "ost": "movie soundtrack",
    "games": "video game soundtrack",
    "anime": "anime songs",
    "kpop": "kpop hits",
    "pop": "pop hits",
    "2000s": "2000s hits",
}


def term_label(term):
    return t(f"genre.{term}") if term in GENRES else term


class UserError(Exception):
    """A failure whose message can be shown to the user as it is."""


class Jobs:
    """Long tasks, one at a time so they don't step on each other's pauses with YouTube."""

    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.jobs = {}
        self.ids = itertools.count(1)

    def start(self, fn, *args, background=False):
        job = {"id": next(self.ids), "status": "running", "message": t("job.queued"), "result": None, "background": background}
        self.jobs[job["id"]] = job

        def progress(message):
            job["message"] = message

        def run():
            try:
                job["result"] = fn(progress, *args)
                job["status"] = "done"
            except Exception as error:
                job["status"] = "error"
                job["message"] = str(error) or type(error).__name__

        self.pool.submit(run)
        return job

    def busy(self):
        """Tasks the user started; the automatic background ones don't count."""
        return any(job["status"] == "running" and not job["background"] for job in self.jobs.values())

    def get(self, job_id):
        return self.jobs.get(job_id)

    def stop(self):
        self.pool.shutdown(wait=False, cancel_futures=True)


class Service:
    def __init__(self, store, yt, config=None):
        self.store = store
        self.yt = yt
        self.config = config or Config()
        self.jobs = Jobs()
        # Set by the server once everything is running
        self.startup_job = None
        self.tray = None
        self.profiles = None
        self.updates = None
        self.last_import = None

    # Importing
    def import_url(self, progress, text, name=None):
        target = engine.parse_url(text)
        if not target:
            raise UserError(t("err.not_youtube"))
        ref = target.get("list") or f"RD{target['video']}"
        existing = self.store.source_by_ref(ref)
        if existing:
            return self.refresh(progress, existing["id"])
        kind, title, tracks = self._read(progress, target)
        if not tracks:
            raise UserError(t("err.no_songs_found"))
        source_id = self.store.create_source(kind, name or title, ref, tracks, {"target": target})
        return {"source_id": source_id, "count": len(tracks)}

    def _read(self, progress, target):
        progress(t("job.reading"))
        if target["kind"] == "playlist":
            title, tracks = self.yt.playlist(target["list"])
            return "playlist", title, tracks
        if target["kind"] == "mix":
            tracks = self.yt.mix(target["list"], target["video"])
        else:
            tracks = self.yt.radio(target["video"])
        return "mix", t("name.mix", title=tracks[0]["title"]) if tracks else t("name.mix_plain"), tracks

    def refresh(self, progress, source_id, store=None):
        """Re-reads a list from YouTube. If it comes back empty (deleted, private), the saved copy is kept."""
        store = store or self.store
        source = store.source(source_id)
        target = source and source["meta"].get("target")
        if not target:
            raise UserError(t("err.not_from_youtube"))
        _, _, tracks = self._read(progress, target)
        if tracks:
            store.replace_source_tracks(source_id, tracks)
        return {"source_id": source_id, "count": len(tracks)}

    def rename_source(self, source_id, name):
        name = str(name or "").strip()
        if not name:
            raise UserError(t("err.name_required"))
        self.store.rename_source(source_id, name)
        return {}

    def set_auto_update(self, source_id, value):
        source = self.store.source(source_id)
        if not source:
            raise UserError(t("err.list_gone"))
        self.store.set_source_meta(source_id, {**source["meta"], "auto_update": value})
        return {}

    def auto_update(self, progress):
        """When the app opens, brings up to date the lists marked for it that haven't been updated for a while."""
        # The concrete profile, so a profile switch halfway can't send lists to the wrong one
        store = self.store.concrete() if hasattr(self.store, "concrete") else self.store
        due = [
            source for source in store.sources()
            if source["auto_update"] and source["meta"].get("target")
            and time.time() - source["updated_at"] > AUTO_UPDATE_EVERY
        ]
        updated, failed = [], []
        for index, source in enumerate(due, 1):
            progress(t("job.updating", index=index, total=len(due), name=source["name"]))
            try:
                self.refresh(lambda _: None, source["id"], store)
                updated.append(source["name"])
            except Exception as error:
                failed.append(source["name"])
                log(f"Auto-update of '{source['name']}' failed:", error)
        return {"count": len(updated), "failed": failed}

    def import_tracks(self, name, items):
        """Saves a list exactly as the bookmarklet saw it on YouTube, whatever account it belongs to."""
        tracks = engine.dedupe([
            {
                "video_id": item[0],
                "title": str(item[1] or t("name.untitled"))[:300],
                "artist": str(item[2] or "")[:200],
                "duration": 0,
                "thumb": f"https://i.ytimg.com/vi/{item[0]}/mqdefault.jpg",
            }
            for item in items
            if isinstance(item, list) and len(item) >= 3 and isinstance(item[0], str) and engine.VIDEO_ID.match(item[0])
        ])
        if not tracks:
            raise UserError(t("err.no_tracks_received"))
        name = str(name or "").strip()[:200] or t("name.saved_mix")
        source_id = self.store.create_source("mix", name, None, tracks, {"origin": "browser"})
        return {"source_id": source_id, "count": len(tracks), "name": name}

    def import_account(self, progress):
        if not self.yt.account:
            raise UserError(t("err.connect_first"))
        progress(t("job.reading_likes"))
        liked = self.yt.liked_songs()
        existing = self.store.source_by_ref("LM")
        if existing:
            self.store.replace_source_tracks(existing["id"], liked)
        else:
            self.store.create_source("playlist", t("name.my_likes"), "LM", liked)
        lists = [p for p in self.yt.account_playlists() if p.get("playlistId") not in (None, "LM", "SE")]
        for index, playlist in enumerate(lists, 1):
            progress(t("job.importing", index=index, total=len(lists), name=playlist.get("title", "")))
            try:
                self.import_url(lambda _: None, playlist["playlistId"], playlist.get("title"))
            except Exception as error:
                log(f"Import of account playlist {playlist['playlistId']} failed:", error)
        return {"count": len(lists) + 1}

    # Profiles
    def _profiles(self):
        if not self.profiles:
            raise UserError(t("err.profiles_unavailable"))
        return self.profiles

    def _profile_call(self, fn, *args):
        try:
            result = fn(*args)
        except ProfileError as error:
            raise UserError(str(error)) from error
        if self.tray:
            self.tray.refresh()
        return result

    def profiles_state(self):
        return self._profiles().list()

    def switch_profile(self, profile_id):
        profiles = self._profiles()
        if self.jobs.busy():
            raise UserError(t("err.busy"))
        self._profile_call(profiles.switch, profile_id)
        self.startup_job = self.jobs.start(self.auto_update, background=True)
        return profiles.list()

    def create_profile(self, name, copy_lists):
        profiles = self._profiles()
        if self.jobs.busy():
            raise UserError(t("err.busy"))
        profile_id = self._profile_call(profiles.create, name, copy_lists)
        return self.switch_profile(profile_id)

    def rename_profile(self, profile_id, name):
        self._profile_call(self._profiles().rename, profile_id, name)
        return self.profiles_state()

    def delete_profile(self, profile_id):
        self._profile_call(self._profiles().delete, profile_id)
        return self.profiles_state()

    # Queue
    @staticmethod
    def _playable(tracks):
        return [track for track in tracks if not track["unplayable"]]

    def _player(self):
        return self.store.get("player", {"index": 0, "time": 0, "source_ids": []})

    def queue_state(self):
        return {"queue": self.store.queue(), "player": self._player()}

    def _play(self, tracks, source_ids):
        self.store.set_queue([track["video_id"] for track in tracks])
        self.store.put("player", {"index": 0, "time": 0, "source_ids": source_ids})
        return self.queue_state()

    def shuffle(self, source_ids, avoid_recent=False):
        """True shuffle of one or several lists. `avoid_recent` keeps what just played away from the start."""
        tracks = engine.dedupe(self._playable(self.store.tracks_of_sources(source_ids)))
        if not tracks:
            raise UserError(t("err.nothing_to_shuffle"))
        avoid = [track["video_id"] for track in self.store.queue()[-20:]] if avoid_recent else ()
        return self._play(engine.true_shuffle(tracks, avoid), source_ids)

    def play_source(self, source_id, shuffle=False):
        tracks = self._playable(self.store.source_tracks(source_id))
        if not tracks:
            raise UserError(t("err.list_empty"))
        return self._play(engine.true_shuffle(engine.dedupe(tracks)) if shuffle else tracks, [source_id])

    def reorder(self, shuffle, current_id):
        """Turns shuffle on or off without interrupting the song that is playing."""
        player = self._player()
        queue = self.store.queue()
        tracks = engine.dedupe(self._playable(self.store.tracks_of_sources(player.get("source_ids", [])))) or queue
        current = next((track for track in queue if track["video_id"] == current_id), None)
        if shuffle:
            rest = [track for track in tracks if track["video_id"] != current_id]
            ordered = ([current] if current else []) + engine.true_shuffle(rest)
        elif current is None or any(track["video_id"] == current_id for track in tracks):
            ordered = tracks
        else:
            ordered = [current] + tracks
        index = next((i for i, track in enumerate(ordered) if track["video_id"] == current_id), 0)
        self.store.set_queue([track["video_id"] for track in ordered])
        self.store.put("player", {**player, "index": index})
        return self.queue_state()

    def save_player(self, index, position):
        self.store.put("player", {**self._player(), "index": index, "time": position})
        return {}

    def save_queue(self, name):
        tracks = self.store.queue()
        if not tracks:
            raise UserError(t("err.queue_empty"))
        return self.store.create_source("saved", name, None, tracks)

    # Generating mixes and discoveries
    def generate(self, progress, params):
        """Builds a mix from topics, lists or the user's taste: radios of a few seed songs,
        scored by how often each candidate shows up and how well it fits what the user likes."""
        terms = [term.strip() for term in params.get("terms", []) if term.strip()]
        source_ids = params.get("source_ids", [])
        size = max(10, min(200, int(params.get("size", 50))))
        explore = max(0, min(100, int(params.get("explore", 50))))

        reactions = self.store.reactions()
        events = self.store.events()
        finished = {event["video_id"] for event in events if event["type"] == "finish"}
        selected = self._playable(self.store.tracks_of_sources(source_ids))

        on_topic = {}
        for term in terms:
            progress(t("job.searching", term=term_label(term)))
            for track in self.yt.term_pool(GENRES.get(term, term)):
                on_topic[track["video_id"]] = track
        self.store.upsert_tracks(list(on_topic.values()))

        # Where to start from: what was asked for; failing that, what the user likes; failing that, everything
        base = selected + list(on_topic.values())
        if not base:
            liked = [video_id for video_id, value in reactions.items() if value > 0]
            base = self._playable(self.store.tracks_by_ids(liked + list(finished)))
        if not base:
            base = self._playable(self.store.tracks_of_sources([source["id"] for source in self.store.sources()]))
        if not base:
            raise UserError(t("err.no_base"))

        seeds = engine.pick_seeds(base, reactions, finished, self.store.seed_uses(), SEEDS_PER_MIX)
        overlap = collections.Counter()
        found = {}
        for index, seed in enumerate(seeds, 1):
            progress(t("job.exploring", index=index, total=len(seeds)))
            try:
                radio = self.yt.radio(seed["video_id"])
            except Exception:
                continue
            for track in radio:
                found[track["video_id"]] = track
                overlap[track["video_id"]] += 1
        self.store.mark_seeds([seed["video_id"] for seed in seeds])
        self.store.upsert_tracks(list(found.values()))
        for track in on_topic.values():
            found.setdefault(track["video_id"], track)

        progress(t("job.choosing"))
        known_ids = self.store.library_ids() | self.store.played_ids()
        by_id = {
            track["video_id"]: track
            for track in self.store.tracks_by_ids(set(found) | {event["video_id"] for event in events} | set(reactions))
        }
        affinity = engine.artist_affinity(events, reactions, by_id, prefs=self._artist_prefs())
        similar = self._similar(seeds, affinity)

        # Anonymous radios slip in unrelated hits of the moment, so only artists close to
        # what was asked for are accepted, or those that show up in several radios.
        related = {engine.normalize(track["artist"]) for track in base} | set(similar)
        scored = []
        for video_id, track in found.items():
            stored = by_id.get(video_id, {})
            artist = engine.normalize(track["artist"])
            if video_id in known_ids or reactions.get(video_id, 0) < 0 or stored.get("unplayable"):
                continue
            if affinity[artist] <= AVOID_BELOW:
                continue
            is_related = artist in related
            if video_id not in on_topic and not is_related and (terms or overlap[video_id] < 2):
                continue
            score = engine.score_candidate(
                overlap[video_id], video_id in on_topic, is_related, affinity[artist], similar.get(artist, 0)
            )
            scored.append((score, stored or track))
        candidates = engine.pick_weighted(scored, size, artist_limit=max(2, size // 12))

        # Familiar songs, leaving what was played in the last days for the end
        recent = self.store.recent_ids(time.time() - RECENT_DAYS * 86400)
        familiar = [
            track for track in engine.dedupe(base)
            if track["video_id"] in known_ids and reactions.get(track["video_id"], 0) >= 0
        ]
        familiar = engine.true_shuffle(familiar)
        familiar.sort(key=lambda track: track["video_id"] in recent)

        tracks = engine.compose(candidates, familiar, size, explore)
        if not tracks:
            raise UserError(t("err.no_new_songs"))
        name = params.get("name") or self._default_name(terms, explore)
        meta = {"params": {**params, "size": size, "explore": explore}, "seeds": [seed["video_id"] for seed in seeds]}
        source_id = self.store.create_source("generated", name, None, tracks, meta)
        state = self._play(self.store.source_tracks(source_id), [source_id])
        return {"source_id": source_id, "count": len(tracks), "name": name, **state}

    @staticmethod
    def _default_name(terms, explore):
        if terms:
            label = " + ".join(map(term_label, terms))
        else:
            label = t("name.discovery" if explore >= DISCOVERY_EXPLORE else "name.my_mix")
        return f"{label} · {time.strftime('%d/%m %H:%M')}"

    def _similar(self, seeds, affinity):
        artists = [artist for artist, score in affinity.most_common(5) if score > 0]
        artists += [seed["artist"] for seed in seeds]
        similar = {}
        for artist in artists:
            for name, match in self.yt.similar_artists(artist).items():
                similar[name] = max(similar.get(name, 0), match)
        return similar

    # Player
    def track_year(self, video_id):
        """Year shown on the display. Asked to YouTube once per song and then remembered."""
        track = self.store.track(video_id)
        if not track:
            raise UserError(t("err.song_unknown"))
        if track["year_kind"] is None:
            try:
                year, kind = self.yt.release_year(video_id)
            except Exception as error:
                log(f"Year of {video_id} not available:", error)
                return {"year": 0, "kind": None}  # not remembered: it will be asked again another day
            track["year"], track["year_kind"] = year or 0, kind or "none"
            self.store.set_year(video_id, track["year"], track["year_kind"])
        return {"year": track["year"], "kind": track["year_kind"]}

    def report_error(self, video_id, code):
        """The player couldn't play a video: look for another upload of the song, or give it up."""
        track = self.store.track(video_id)
        if not track:
            return {"action": "skip"}
        self.store.log_event(video_id, "error", detail=str(code))
        if code not in BLOCK_CODES:
            return {"action": "skip", "code": code}  # a browser or network problem, not the video's fault
        if track["alt_video_id"]:
            self.store.mark_unplayable(video_id)  # the alternative failed too
            return {"action": "skip", "code": code}
        try:
            alternative = self.yt.find_alternative(track)
        except Exception:
            return {"action": "skip", "code": code}
        if not alternative:
            self.store.mark_unplayable(video_id)
            return {"action": "skip", "code": code}
        self.store.upsert_tracks([alternative])
        self.store.set_alternative(video_id, alternative["video_id"])
        return {"action": "alt", "play_id": alternative["video_id"], "code": code}

    # What YouMixer has learned
    def _artist_prefs(self):
        return {artist: pref["value"] for artist, pref in self.store.artist_prefs().items()}

    def set_artist_pref(self, key, name, value):
        """The user's own choice for an artist: 1 keep, -1 avoid, 0 none. It overrides what was learned."""
        if value not in (-1, 0, 1) or not key:
            raise UserError(t("err.bad_pref"))
        self.store.set_artist_pref(key, name or key, value)
        return {}

    def forget_artist(self, key):
        ids = {event["video_id"] for event in self.store.events()} | set(self.store.reactions())
        matches = [track["video_id"] for track in self.store.tracks_by_ids(ids) if engine.normalize(track["artist"]) == key]
        self.store.forget_tracks(matches)
        self.store.set_artist_pref(key, "", 0)
        return {"count": len(matches)}

    def profile(self):
        """Summary for the Activity panel: favourite and avoided artists, and a few totals."""
        events = self.store.events()
        reactions = self.store.reactions()
        by_id = {
            track["video_id"]: track
            for track in self.store.tracks_by_ids({event["video_id"] for event in events} | set(reactions))
        }
        names = {engine.normalize(track["artist"]): track["artist"] for track in by_id.values()}
        pinned = self.store.artist_prefs()
        names.update({artist: pref["name"] for artist, pref in pinned.items()})
        prefs = {artist: pref["value"] for artist, pref in pinned.items()}
        ordered = engine.artist_affinity(events, reactions, by_id, prefs=prefs).most_common()

        def entry(artist, score):
            return {"key": artist, "artist": names.get(artist, artist), "score": round(score, 1), "pinned": artist in prefs}

        # What the user chose always shows; of what was learned, only the first few
        top = [entry(artist, score) for artist, score in ordered if prefs.get(artist) == 1]
        top += [entry(artist, score) for artist, score in ordered if score > 0 and artist not in prefs][:12]
        avoid = [entry(artist, score) for artist, score in ordered[::-1] if prefs.get(artist) == -1]
        avoid += [entry(artist, score) for artist, score in ordered[::-1] if score < 0 and artist not in prefs][:8]
        return {
            "top": top,
            "avoid": avoid,
            "likes": sum(value > 0 for value in reactions.values()),
            "finished": sum(event["type"] == "finish" for event in events),
            "skipped": sum(event["type"] == "skip" for event in events),
        }
