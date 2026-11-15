"""SQLite persistence: everything a profile does is kept in its database (data/youmixer.db for the main one)."""
import glob
import json
import os
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks(
    video_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    artist TEXT NOT NULL DEFAULT '',
    duration INTEGER NOT NULL DEFAULT 0,
    thumb TEXT NOT NULL DEFAULT '',
    alt_video_id TEXT,
    unplayable INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sources(
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    ref TEXT,
    meta TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS source_tracks(
    source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    pos INTEGER NOT NULL,
    video_id TEXT NOT NULL REFERENCES tracks(video_id),
    PRIMARY KEY(source_id, pos)
);
CREATE INDEX IF NOT EXISTS idx_source_tracks_video ON source_tracks(video_id);
CREATE TABLE IF NOT EXISTS events(
    id INTEGER PRIMARY KEY,
    video_id TEXT NOT NULL,
    type TEXT NOT NULL,
    position REAL NOT NULL DEFAULT 0,
    duration REAL NOT NULL DEFAULT 0,
    detail TEXT,
    at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_video ON events(video_id);
CREATE TABLE IF NOT EXISTS reactions(
    video_id TEXT PRIMARY KEY,
    value INTEGER NOT NULL,
    at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS artist_prefs(
    artist TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    value INTEGER NOT NULL,
    at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS seed_use(
    video_id TEXT PRIMARY KEY,
    at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS queue(
    pos INTEGER PRIMARY KEY,
    video_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS kv(
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cache(
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    expires REAL NOT NULL
);
"""

BACKUPS_KEPT = 10
SQL_CHUNK = 500  # ids per query, safely under SQLite's limit of bound parameters


class Store:
    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(SCHEMA)
        for column in ("year INTEGER", "year_kind TEXT"):
            try:
                self.db.execute(f"ALTER TABLE tracks ADD COLUMN {column}")
            except sqlite3.OperationalError:
                pass  # the column is already there
        self.db.execute("DELETE FROM cache WHERE expires<?", (time.time(),))

    def _all(self, sql, *args):
        with self.lock:
            return [dict(row) for row in self.db.execute(sql, args).fetchall()]

    def _one(self, sql, *args):
        rows = self._all(sql, *args)
        return rows[0] if rows else None

    def _tx(self, fn):
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                result = fn(self.db)
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
            self.db.execute("COMMIT")
            return result

    # Tracks
    def upsert_tracks(self, tracks):
        self._tx(lambda db: self._upsert(db, tracks))

    @staticmethod
    def _upsert(db, tracks):
        db.executemany(
            """INSERT INTO tracks(video_id, title, artist, duration, thumb)
               VALUES(:video_id, :title, :artist, :duration, :thumb)
               ON CONFLICT(video_id) DO UPDATE SET
                 title=excluded.title,
                 artist=CASE WHEN excluded.artist<>'' THEN excluded.artist ELSE artist END,
                 duration=CASE WHEN excluded.duration>0 THEN excluded.duration ELSE duration END,
                 thumb=CASE WHEN excluded.thumb<>'' THEN excluded.thumb ELSE thumb END""",
            tracks,
        )

    def track(self, video_id):
        return self._one("SELECT * FROM tracks WHERE video_id=?", video_id)

    def set_alternative(self, video_id, alt_video_id):
        with self.lock:
            self.db.execute("UPDATE tracks SET alt_video_id=? WHERE video_id=?", (alt_video_id, video_id))

    def set_year(self, video_id, year, kind):
        with self.lock:
            self.db.execute("UPDATE tracks SET year=?, year_kind=? WHERE video_id=?", (year, kind, video_id))

    def mark_unplayable(self, video_id):
        with self.lock:
            self.db.execute("UPDATE tracks SET unplayable=1, alt_video_id=NULL WHERE video_id=?", (video_id,))

    # Saved lists (playlists, mixes, generated mixes and saved queues)
    def create_source(self, kind, name, ref, tracks, meta=None):
        now = time.time()

        def work(db):
            cur = db.execute(
                "INSERT INTO sources(kind, name, ref, meta, created_at, updated_at) VALUES(?,?,?,?,?,?)",
                (kind, name, ref, json.dumps(meta or {}), now, now),
            )
            self._write_source_tracks(db, cur.lastrowid, tracks)
            return cur.lastrowid

        return self._tx(work)

    def replace_source_tracks(self, source_id, tracks):
        def work(db):
            db.execute("UPDATE sources SET updated_at=? WHERE id=?", (time.time(), source_id))
            self._write_source_tracks(db, source_id, tracks)

        self._tx(work)

    def _write_source_tracks(self, db, source_id, tracks):
        self._upsert(db, tracks)
        db.execute("DELETE FROM source_tracks WHERE source_id=?", (source_id,))
        db.executemany(
            "INSERT INTO source_tracks(source_id, pos, video_id) VALUES(?,?,?)",
            [(source_id, position, track["video_id"]) for position, track in enumerate(tracks)],
        )

    def sources(self):
        rows = self._all(
            """SELECT s.*, COUNT(st.video_id) AS count FROM sources s
               LEFT JOIN source_tracks st ON st.source_id=s.id
               GROUP BY s.id ORDER BY s.created_at DESC"""
        )
        for row in rows:
            row["meta"] = json.loads(row["meta"])
            # Playlists follow the original unless told otherwise; mixes are kept as they were saved
            row["auto_update"] = row["meta"].get("auto_update", row["kind"] == "playlist")
        return rows

    def source(self, source_id):
        row = self._one("SELECT * FROM sources WHERE id=?", source_id)
        if row:
            row["meta"] = json.loads(row["meta"])
        return row

    def set_source_meta(self, source_id, meta):
        with self.lock:
            self.db.execute("UPDATE sources SET meta=? WHERE id=?", (json.dumps(meta), source_id))

    def source_by_ref(self, ref):
        return self._one("SELECT id FROM sources WHERE ref=?", ref)

    def source_tracks(self, source_id):
        return self._all(
            """SELECT t.* FROM source_tracks st JOIN tracks t ON t.video_id=st.video_id
               WHERE st.source_id=? ORDER BY st.pos""",
            source_id,
        )

    def tracks_of_sources(self, source_ids):
        tracks = []
        for source_id in source_ids:
            tracks.extend(self.source_tracks(source_id))
        return tracks

    def rename_source(self, source_id, name):
        with self.lock:
            self.db.execute("UPDATE sources SET name=? WHERE id=?", (name, source_id))

    def delete_source(self, source_id):
        with self.lock:
            self.db.execute("DELETE FROM sources WHERE id=?", (source_id,))

    def library_ids(self):
        """Every song in the user's own lists (not in the mixes YouMixer generated)."""
        rows = self._all(
            """SELECT DISTINCT st.video_id FROM source_tracks st
               JOIN sources s ON s.id=st.source_id WHERE s.kind<>'generated'"""
        )
        return {row["video_id"] for row in rows}

    # Queue and player state
    def set_queue(self, video_ids):
        def work(db):
            db.execute("DELETE FROM queue")
            db.executemany("INSERT INTO queue(pos, video_id) VALUES(?,?)", list(enumerate(video_ids)))

        self._tx(work)

    def queue(self):
        return self._all(
            "SELECT t.* FROM queue q JOIN tracks t ON t.video_id=q.video_id ORDER BY q.pos"
        )

    def get(self, key, default=None):
        row = self._one("SELECT value FROM kv WHERE key=?", key)
        return json.loads(row["value"]) if row else default

    def put(self, key, value):
        with self.lock:
            self.db.execute(
                "INSERT INTO kv(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value)),
            )

    # Activity: what was played, finished, skipped or failed
    def log_event(self, video_id, type_, position=0, duration=0, detail=None):
        with self.lock:
            self.db.execute(
                "INSERT INTO events(video_id, type, position, duration, detail, at) VALUES(?,?,?,?,?,?)",
                (video_id, type_, position, duration, detail, time.time()),
            )

    def events(self):
        return self._all("SELECT * FROM events ORDER BY at")

    def history(self, limit=200):
        return self._all(
            """SELECT e.id, e.type, e.at, e.detail, t.video_id, t.title, t.artist, t.thumb
               FROM events e JOIN tracks t ON t.video_id=e.video_id
               WHERE e.type IN ('finish','skip','error') ORDER BY e.at DESC LIMIT ?""",
            limit,
        )

    def delete_event(self, event_id):
        with self.lock:
            self.db.execute("DELETE FROM events WHERE id=?", (event_id,))

    def forget_tracks(self, video_ids):
        """Forgets what was learned from these songs: plays, skips and reactions."""
        rows = [(video_id,) for video_id in video_ids]

        def work(db):
            db.executemany("DELETE FROM events WHERE video_id=? AND type IN ('finish','skip')", rows)
            db.executemany("DELETE FROM reactions WHERE video_id=?", rows)

        self._tx(work)

    def played_ids(self):
        rows = self._all("SELECT DISTINCT video_id FROM events WHERE type IN ('play','finish','skip')")
        return {row["video_id"] for row in rows}

    def recent_ids(self, since):
        rows = self._all("SELECT DISTINCT video_id FROM events WHERE at>=? AND type='play'", since)
        return {row["video_id"] for row in rows}

    def react(self, video_id, value):
        with self.lock:
            if value:
                self.db.execute(
                    """INSERT INTO reactions(video_id, value, at) VALUES(?,?,?)
                       ON CONFLICT(video_id) DO UPDATE SET value=excluded.value, at=excluded.at""",
                    (video_id, value, time.time()),
                )
            else:
                self.db.execute("DELETE FROM reactions WHERE video_id=?", (video_id,))

    def reactions(self):
        return {row["video_id"]: row["value"] for row in self._all("SELECT video_id, value FROM reactions")}

    def tracks_by_ids(self, video_ids):
        video_ids = list(video_ids)
        tracks = []
        for start in range(0, len(video_ids), SQL_CHUNK):
            chunk = video_ids[start:start + SQL_CHUNK]
            tracks += self._all(f"SELECT * FROM tracks WHERE video_id IN ({','.join('?' * len(chunk))})", *chunk)
        return tracks

    def artist_prefs(self):
        return {row["artist"]: row for row in self._all("SELECT * FROM artist_prefs")}

    def set_artist_pref(self, artist, name, value):
        with self.lock:
            if value:
                self.db.execute(
                    """INSERT INTO artist_prefs(artist, name, value, at) VALUES(?,?,?,?)
                       ON CONFLICT(artist) DO UPDATE SET name=excluded.name, value=excluded.value, at=excluded.at""",
                    (artist, name, value, time.time()),
                )
            else:
                self.db.execute("DELETE FROM artist_prefs WHERE artist=?", (artist,))

    def seed_uses(self):
        return {row["video_id"]: row["at"] for row in self._all("SELECT * FROM seed_use")}

    def mark_seeds(self, video_ids):
        now = time.time()
        with self.lock:
            self.db.executemany(
                """INSERT INTO seed_use(video_id, at) VALUES(?,?)
                   ON CONFLICT(video_id) DO UPDATE SET at=excluded.at""",
                [(video_id, now) for video_id in video_ids],
            )

    # Cache of answers from YouTube and Last.fm; nothing of the user's is lost if it is wiped
    def cache_get(self, key):
        row = self._one("SELECT value FROM cache WHERE key=? AND expires>?", key, time.time())
        return json.loads(row["value"]) if row else None

    def cache_put(self, key, value, ttl):
        with self.lock:
            self.db.execute(
                """INSERT INTO cache(key, value, expires) VALUES(?,?,?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value, expires=excluded.expires""",
                (key, json.dumps(value), time.time() + ttl),
            )

    # Backups
    def backup(self, folder):
        os.makedirs(folder, exist_ok=True)
        target = os.path.join(folder, time.strftime("youmixer-%Y%m%d-%H%M%S.db"))
        with self.lock:
            dest = sqlite3.connect(target)
            with dest:
                self.db.backup(dest)
            dest.close()
        for old in sorted(glob.glob(os.path.join(folder, "youmixer-*.db")))[:-BACKUPS_KEPT]:
            os.remove(old)
        return target

    def export(self):
        return {
            "exported_at": time.time(),
            "sources": [
                {**s, "tracks": self.source_tracks(s["id"])} for s in self.sources()
            ],
            "reactions": self.reactions(),
            "artist_prefs": list(self.artist_prefs().values()),
            "events": self.events(),
            "queue": self.queue(),
        }

    def close(self):
        with self.lock:
            self.db.close()
