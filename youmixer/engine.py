"""Shuffling and recommendation logic. It touches neither the network nor the disk: only data."""
import collections
import json
import math
import random
import re
import time
from urllib.parse import parse_qs, urlparse

VIDEO_ID = re.compile(r"^[\w-]{11}$")
NOISE = re.compile(
    r"[\(\[【].*?[\)\]】]|official\s+(music\s+)?(video|audio|mv)|music\s+video|lyrics?|\bm/?v\b|\bhd\b|\b4k\b",
    re.I,
)
EARLY_SKIP_SECONDS = 30
EARLY_SKIP_RATIO = 0.25
HALF_LIFE_DAYS = 90
PINNED_SCORE = 5
SYSTEM_RANDOM = random.SystemRandom()
YOUTUBE_HOSTS = ("youtube.com", "youtu.be")


def parse_url(text):
    """Turns a YouTube link or id into what has to be imported: a playlist, a mix or a single video."""
    text = (text or "").strip()
    if not text:
        return None
    if VIDEO_ID.match(text):
        return {"kind": "video", "video": text}
    if re.match(r"^(PL|OLAK5uy_|UU|FL)[\w-]+$", text):
        return {"kind": "playlist", "list": text}
    if text.startswith("RDCLAK") and re.match(r"^[\w-]+$", text):  # YouTube Music's curated playlists
        return {"kind": "playlist", "list": text}
    if text.startswith("RD") and re.match(r"^[\w-]+$", text):
        return {"kind": "mix", "list": text, "video": _video_in_mix(text)}
    url = urlparse(text if "://" in text else "https://" + text)
    host = url.netloc.lower()
    if not any(host == known or host.endswith("." + known) for known in YOUTUBE_HOSTS):
        return None
    query = parse_qs(url.query)
    video = query.get("v", [None])[0]
    if host.endswith("youtu.be"):
        video = url.path.strip("/").split("/")[0] or None
    elif url.path.startswith(("/shorts/", "/live/")):
        video = url.path.split("/")[2]
    playlist = query.get("list", [None])[0]
    if playlist and playlist.startswith("RD") and not playlist.startswith("RDCLAK"):
        return {"kind": "mix", "list": playlist, "video": video or _video_in_mix(playlist)}
    if playlist:
        return {"kind": "playlist", "list": playlist}
    if video:
        return {"kind": "video", "video": video}
    return None


def _video_in_mix(playlist):
    """A mix's id usually carries the id of the video it was made from."""
    for prefix in ("RDAMVM", "RDMM", "RD"):
        rest = playlist[len(prefix):]
        if playlist.startswith(prefix) and VIDEO_ID.match(rest):
            return rest
    return None


DESCRIPTION = re.compile(r'"shortDescription":"((?:[^"\\]|\\.)*)"')
YEAR_SOURCES = (
    ("copyright", re.compile(r"\u2117\s*((?:19|20)\d{2})")),
    ("released", re.compile(r"Released on:\s*((?:19|20)\d{2})")),
)
UPLOAD = re.compile(r'"(?:uploadDate|publishDate)":"((?:19|20)\d{2})')


def release_year(html):
    """Year of a song from its YouTube page: copyright (℗) or release if the description has them; else the upload year."""
    match = DESCRIPTION.search(html)
    if match:
        try:
            description = json.loads('"' + match.group(1) + '"')
        except ValueError:
            description = ""
        for kind, pattern in YEAR_SOURCES:
            found = pattern.search(description)
            if found:
                return int(found.group(1)), kind
    found = UPLOAD.search(html)
    return (int(found.group(1)), "upload") if found else (None, None)


def normalize(text):
    """Lower case without punctuation or noise such as "(Official Video)", to compare titles and artists."""
    text = NOISE.sub(" ", text or "").lower()
    return re.sub(r"[^\w]+", " ", text).strip()


def track_key(track):
    return normalize(track["title"]), normalize(track.get("artist", ""))


def dedupe(tracks):
    """Drops repeats: the same video, or the same song uploaded twice."""
    seen_ids, seen_keys, unique = set(), set(), []
    for track in tracks:
        key = track_key(track)
        if track["video_id"] in seen_ids or key in seen_keys:
            continue
        seen_ids.add(track["video_id"])
        seen_keys.add(key)
        unique.append(track)
    return unique


def space_artists(tracks, gap=2):
    """Pulls apart songs by the same artist that ended up close together, leaving the rest as it is."""
    result = list(tracks)
    artists = [normalize(track.get("artist", "")) for track in result]

    def fits(pos, artist, ignore):
        """The artist doesn't show up within `gap` songs of `pos` (not counting `ignore`)."""
        around = range(max(0, pos - gap), min(len(result), pos + gap + 1))
        return not artist or all(artists[k] != artist for k in around if k not in ignore)

    for i in range(1, len(result)):
        if not artists[i] or artists[i] not in artists[max(0, i - gap):i]:
            continue
        # Look ahead first; near the end there may be nothing left to swap with, so look back too
        for j in [*range(i + 1, len(result)), *range(i - 1, -1, -1)]:
            if artists[j] != artists[i] and fits(i, artists[j], {i, j}) and fits(j, artists[i], {i, j}):
                result[i], result[j] = result[j], result[i]
                artists[i], artists[j] = artists[j], artists[i]
                break
    return result


def true_shuffle(tracks, avoid=(), rng=SYSTEM_RANDOM):
    """Uniform shuffle: every order is equally likely. `avoid` (what just played) is kept away from the start."""
    tracks = list(tracks)
    rng.shuffle(tracks)
    avoid = set(avoid)
    if avoid:
        first = [track for track in tracks if track["video_id"] not in avoid]
        last = [track for track in tracks if track["video_id"] in avoid]
        cut = len(first) // 2
        tail = first[cut:] + last
        rng.shuffle(tail)
        tracks = first[:cut] + tail
    return space_artists(tracks)


def artist_affinity(events, reactions, tracks_by_id, now=None, prefs=None):
    """Score per artist from reactions and from what gets played through or skipped.
    Old listening weighs less and less (half-life of HALF_LIFE_DAYS).

    `prefs` ({artist: 1 or -1}) is what the user chose by hand, and it overrides what was learned."""
    now = now or time.time()
    scores = collections.Counter()

    def add(video_id, weight):
        track = tracks_by_id.get(video_id)
        artist = normalize(track.get("artist", "")) if track else ""
        if artist:
            scores[artist] += weight

    for event in events:
        decay = 0.5 ** ((now - event["at"]) / 86400 / HALF_LIFE_DAYS)
        if event["type"] == "finish":
            add(event["video_id"], 1 * decay)
        elif event["type"] == "skip" and is_early_skip(event):
            add(event["video_id"], -1.5 * decay)
    for video_id, value in reactions.items():
        add(video_id, 3 if value > 0 else -4)
    for artist, value in (prefs or {}).items():
        scores[artist] = max(scores[artist], PINNED_SCORE) if value > 0 else -PINNED_SCORE
    return scores


def is_early_skip(event):
    """Skipped soon enough to mean "not this one"; skipping near the end doesn't count against a song."""
    position, duration = event["position"], event["duration"]
    return position < EARLY_SKIP_SECONDS or (duration > 0 and position / duration < EARLY_SKIP_RATIO)


def pick_seeds(pool, reactions, finished, seed_uses, count, now=None, rng=SYSTEM_RANDOM):
    """Picks different seeds every time: favours what the user likes and what hasn't been used for a while."""
    now = now or time.time()
    remaining = list({track["video_id"]: track for track in pool}.values())
    chosen, artists = [], set()
    while remaining and len(chosen) < count:
        weights = []
        for track in remaining:
            video_id = track["video_id"]
            weight = 1.0
            if reactions.get(video_id, 0) > 0:
                weight += 3
            if video_id in finished:
                weight += 1
            if video_id in seed_uses:
                weight *= min(1.0, (now - seed_uses[video_id]) / (30 * 86400)) + 0.02
            if normalize(track.get("artist", "")) in artists:
                weight *= 0.3
            weights.append(weight)
        track = rng.choices(remaining, weights)[0]
        remaining.remove(track)
        chosen.append(track)
        artists.add(normalize(track.get("artist", "")))
    return chosen


def score_candidate(overlap, on_topic, related, affinity, similarity):
    """How well a candidate fits: radios it showed up in, whether it matches the topic or a
    known artist, how much the user likes its artist and how similar Last.fm says it is."""
    return (
        math.log2(1 + overlap)
        + (1.2 if on_topic else 0)
        + (0.8 if related else 0)
        + 0.4 * max(-3, min(3, affinity))
        + similarity
    )


def pick_weighted(scored, count, artist_limit, rng=SYSTEM_RANDOM):
    """Takes from among the best with some chance, so it doesn't come out the same every time."""
    ordered = sorted(scored, key=lambda s: s[0], reverse=True)[: max(count * 3, count + 10)]
    per_artist = collections.Counter()
    chosen, overflow = [], []
    while ordered and len(chosen) < count:
        floor = min(s for s, _ in ordered)
        weights = [(s - floor + 0.5) ** 2 for s, _ in ordered]
        item = rng.choices(ordered, weights)[0]
        ordered.remove(item)
        artist = normalize(item[1].get("artist", ""))
        if artist and per_artist[artist] >= artist_limit:
            overflow.append(item[1])
            continue
        per_artist[artist] += 1
        chosen.append(item[1])
    return chosen + overflow[: count - len(chosen)]


def compose(candidates, known, size, explore, rng=SYSTEM_RANDOM):
    """Joins new and familiar songs in the share asked for; if one kind runs short, the other fills in."""
    new_target = round(size * explore / 100)
    new = candidates[:new_target]
    old = known[: size - len(new)]
    new = candidates[: size - len(old)]
    return true_shuffle(dedupe(new + old), rng=rng)
