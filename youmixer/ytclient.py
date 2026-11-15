"""Access to YouTube Music, the YouTube Data API and Last.fm, paced so YouTube doesn't cut us off."""
import difflib
import json
import os
import random
import threading
import time
import urllib.parse
import urllib.request

import requests
import ytmusicapi
from ytmusicapi import YTMusic

from . import engine
from .i18n import t

MIN_INTERVAL = 2.0  # seconds between requests; faster than this and YouTube starts answering empty
RETRY_WAITS = (5, 15, 40, 90)
RADIO_TTL = 7 * 86400
LASTFM_TTL = 30 * 86400
ALTERNATIVE_LIKENESS = 0.7  # how alike two titles must be to count as the same song
ALTERNATIVE_SECONDS = 20  # and how close in length


class YouTubeError(Exception):
    """YouTube couldn't be read. The message is ready to be shown to the user."""


def to_seconds(text):
    seconds = 0
    for part in (text or "").split(":"):
        if part.isdigit():
            seconds = seconds * 60 + int(part)
    return seconds


def to_track(item):
    """ytmusicapi item → our track dict, or None if it can't be played."""
    video_id = item.get("videoId")
    if not video_id or item.get("isAvailable") is False:
        return None
    artists = item.get("artists") or []
    thumbs = item.get("thumbnails") or item.get("thumbnail") or []
    return {
        "video_id": video_id,
        "title": item.get("title") or t("name.untitled"),
        "artist": artists[0].get("name") or "" if artists else "",
        "duration": item.get("duration_seconds") or to_seconds(item.get("duration") or item.get("length")),
        "thumb": thumbs[0].get("url", "") if thumbs else "",
    }


def to_tracks(items):
    return [track for track in map(to_track, items) if track]


class YT:
    def __init__(self, store, data_dir, config):
        self.store = store
        self.config = config
        self.auth_path = os.path.join(data_dir, "browser.json")
        self.lock = threading.Lock()
        self.last_call = 0.0
        self.anonymous = YTMusic()
        self.account = None
        self._load_account()

    # Account (optional)
    def _load_account(self):
        self.account = YTMusic(self.auth_path) if os.path.exists(self.auth_path) else None

    def login(self, raw_headers):
        ytmusicapi.setup(filepath=self.auth_path, headers_raw=raw_headers)
        self._load_account()
        self.call(self.account.get_library_playlists, limit=1)

    def logout(self):
        self.account = None
        if os.path.exists(self.auth_path):
            os.remove(self.auth_path)

    def account_playlists(self):
        return self.call(self.account.get_library_playlists, limit=None)

    def liked_songs(self):
        return to_tracks(self.call(self.account.get_liked_songs, limit=5000)["tracks"])

    # Every request goes through here: one at a time and with a pause
    def call(self, fn, *args, **kwargs):
        last_error = None
        for wait in (0, *RETRY_WAITS):
            if wait:
                time.sleep(wait)
            with self.lock:
                pause = self.last_call + MIN_INTERVAL + random.uniform(0, 1) - time.time()
                if pause > 0:
                    time.sleep(pause)
                try:
                    return fn(*args, **kwargs)
                except (json.JSONDecodeError, requests.RequestException) as error:
                    last_error = error  # throttled (empty answer) or network trouble: worth retrying
                finally:
                    self.last_call = time.time()
        raise YouTubeError(t("err.youtube_down", error=last_error))

    def _read(self, method, *args, **kwargs):
        """Tries with the connected account first and anonymously after, so an expired
        session doesn't break reading public lists."""
        clients = [client for client in (self.account, self.anonymous) if client]
        for position, client in enumerate(clients, 1):
            try:
                return self.call(getattr(client, method), *args, **kwargs)
            except YouTubeError:
                raise  # YouTube is not answering at all; another client won't help
            except Exception:
                if position == len(clients):
                    raise

    # Reading
    def playlist(self, playlist_id):
        try:
            data = self._read("get_playlist", playlist_id, limit=None)
            return data.get("title") or t("name.playlist"), to_tracks(data["tracks"])
        except Exception as error:
            key = self.config.get("youtube_key")
            if not key:
                raise YouTubeError(t("err.playlist_read", error=error)) from error
            try:
                return self._playlist_data_api(playlist_id, key)
            except (OSError, ValueError, KeyError) as api_error:
                raise YouTubeError(t("err.playlist_read", error=api_error)) from api_error

    def _playlist_data_api(self, playlist_id, key):
        """Fallback through the official API. It only reaches public playlists."""
        def get(path, **params):
            url = f"https://www.googleapis.com/youtube/v3/{path}?" + urllib.parse.urlencode({**params, "key": key})
            with urllib.request.urlopen(url, timeout=20) as response:
                return json.load(response)

        info = get("playlists", part="snippet", id=playlist_id)
        title = info["items"][0]["snippet"]["title"] if info.get("items") else t("name.playlist")
        tracks, token = [], None
        while True:
            params = {"part": "snippet", "playlistId": playlist_id, "maxResults": 50}
            if token:
                params["pageToken"] = token
            page = get("playlistItems", **params)
            for item in page.get("items", []):
                snippet = item["snippet"]
                if snippet["title"] in ("Private video", "Deleted video"):
                    continue
                tracks.append({
                    "video_id": snippet["resourceId"]["videoId"],
                    "title": snippet["title"],
                    "artist": (snippet.get("videoOwnerChannelTitle") or "").removesuffix(" - Topic"),
                    "duration": 0,
                    "thumb": snippet.get("thumbnails", {}).get("default", {}).get("url", ""),
                })
            token = page.get("nextPageToken")
            if not token:
                return title, tracks

    def mix(self, playlist_id, video_id):
        try:
            # More than 100 means several pages in a row, and that gets us throttled
            data = self._read("get_watch_playlist", videoId=video_id, playlistId=playlist_id, limit=100)
            return to_tracks(data["tracks"])
        except Exception:
            if not video_id:
                raise
            return self.radio(video_id)

    def radio(self, video_id):
        """Songs YouTube would play after this one. Always anonymous, so the user's history doesn't steer it."""
        key = f"radio:{video_id}"
        cached = self.store.cache_get(key)
        if cached is not None:
            return cached
        tracks = to_tracks(self.call(self.anonymous.get_watch_playlist, videoId=video_id, radio=True, limit=50)["tracks"])
        self.store.cache_put(key, tracks, RADIO_TTL)
        return tracks

    def search(self, query, kind, limit=20):
        return self.call(self.anonymous.search, query, filter=kind, limit=limit)

    def term_pool(self, term):
        """Songs about a topic: direct results plus the best playlists."""
        tracks = to_tracks(self.search(term, "songs"))
        for playlist in self.search(term, "community_playlists")[:2]:
            playlist_id = (playlist.get("browseId") or "").removeprefix("VL")
            if playlist_id:
                try:
                    tracks += self.playlist(playlist_id)[1]
                except YouTubeError:
                    pass
        return tracks

    def find_alternative(self, track):
        """Another upload of the same song that can be embedded, or None."""
        query = f"{track['artist']} {engine.normalize(track['title'])}".strip()
        wanted = engine.normalize(track["title"])
        for kind in ("songs", "videos"):
            for item in to_tracks(self.search(query, kind, limit=5))[:3]:
                if item["video_id"] == track["video_id"]:
                    continue
                likeness = difflib.SequenceMatcher(None, wanted, engine.normalize(item["title"])).ratio()
                same_length = (
                    not track["duration"] or not item["duration"]
                    or abs(track["duration"] - item["duration"]) <= ALTERNATIVE_SECONDS
                )
                if likeness >= ALTERNATIVE_LIKENESS and same_length and self._embeddable(item["video_id"]):
                    return item
        return None

    def _embeddable(self, video_id):
        status = self.call(self.anonymous.get_song, video_id).get("playabilityStatus", {})
        return status.get("status") == "OK" and status.get("playableInEmbed") is not False

    def release_year(self, video_id):
        """(year, kind) read from the video's page; (None, None) if the page says nothing."""
        def fetch():
            response = requests.get(
                f"https://www.youtube.com/watch?v={video_id}",
                headers={"Accept-Language": "en", "User-Agent": "Mozilla/5.0"},
                cookies={"SOCS": "CAI"},  # skips the cookie consent page
                timeout=20,
            )
            if response.status_code == 429 or response.status_code >= 500:
                response.raise_for_status()  # worth retrying
            return response.text if response.ok else ""  # gone or private: there is nothing to read

        return engine.release_year(self.call(fetch))

    # Last.fm (optional)
    def similar_artists(self, artist):
        """{normalized artist name: similarity from 0 to 1}; empty without a Last.fm key."""
        key = self.config.get("lastfm_key")
        if not key or not artist:
            return {}
        cache_key = f"lastfm:{engine.normalize(artist)}"
        cached = self.store.cache_get(cache_key)
        if cached is not None:
            return cached
        url = "https://ws.audioscrobbler.com/2.0/?" + urllib.parse.urlencode({
            "method": "artist.getsimilar", "artist": artist, "api_key": key, "format": "json", "limit": 100,
        })
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                data = json.load(response)
            similar = {
                engine.normalize(a["name"]): float(a.get("match", 0))
                for a in data.get("similarartists", {}).get("artist", [])
            }
        except (OSError, ValueError, KeyError):
            return {}
        self.store.cache_put(cache_key, similar, LASTFM_TTL)
        return similar
