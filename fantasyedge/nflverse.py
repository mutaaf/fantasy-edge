"""The single owner of talking to nflverse.

nflverse republishes the NFL's own play-by-play as free CSV. It carries the
numbers ESPN's public feed never states - where the ball was caught as against
where the play ended, which gap a run went through, how far a kick actually
travelled - and those are exactly the numbers a field animation needs. So this
is the truth source behind `truth.py`, which corrects a live estimate with it.

Three constraints shape everything here:

1. **Stdlib only.** nflverse publishes parquet beside the CSV and parquet
   needs pandas, so the `.csv.gz` releases are the only ones read. They are
   the same rows.
2. **A season is one file.** There is no per-week release, so a season is
   fetched whole (19 MB gzipped for a finished one) and then sharded per game
   on disk. A shard is what callers read, so the second question about a game
   costs no parse at all.
3. **Freshness is published, not guessed.** Every release carries a
   `timestamp.json` saying when nflverse last rebuilt it. It is recorded
   beside the cache, so "how current is this" is answered from nflverse's own
   statement rather than from a file's mtime.

THE GAME BRIDGE
---------------
nflverse ids a game `2025_01_MIN_CHI` and ESPN ids it `401772810`. Neither
knows the other, but nflverse's schedules release carries an `espn` column
holding ESPN's id, so the bridge is published rather than inferred. Play ids
are *not* bridged anywhere, which is why `truth.py` has to match plays on what
they say about themselves.

WHAT IS CACHED
--------------
    ~/.fantasy-edge/nflverse/
        meta.json                        per-URL: last-modified, etag, size,
                                         nflverse's own last_updated, columns
        play_by_play_2025.csv.gz         the release, as published
        games.csv                        schedules, for the bridge
        pbp/2025/2025_01_MIN_CHI.json    one game's rows, KEPT columns only

A download lands in `<name>.part` and is renamed only when it completes, so an
interrupted fetch never leaves a half file that later reads as truth. A repeat
costs one HEAD request: unchanged `Last-Modified` means the cached bytes are
the release, and nothing is re-downloaded.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import os
import pathlib
import time
import urllib.request

BASE = "https://github.com/nflverse/nflverse-data/releases/download"
WEEKLY = BASE + "/stats_player/stats_player_week_{season}.csv"
ROSTER = BASE + "/players/players.csv"
PBP = BASE + "/pbp/play_by_play_{season}.csv.gz"
PBP_STAMP = BASE + "/pbp/timestamp.json"
SCHEDULES = BASE + "/schedules/games.csv"

CACHE_DIR = pathlib.Path(os.environ.get("FANTASYEDGE_HOME") or (pathlib.Path.home() / ".fantasy-edge"))
NFLVERSE_DIR = CACHE_DIR / "nflverse"
CACHE_TTL = 24 * 3600
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/140.0"

# A season in progress is rewritten daily; a finished one never changes. Both
# are re-checked with a HEAD, which costs nothing, so the window only decides
# how often that check happens.
LIVE_TTL = 3600

# The columns kept in a shard. Everything a path needs, plus what identifies a
# play and what proves the join. nflverse publishes 372; storing all of them
# would put 50 MB of coverage data behind a question about one kick.
KEPT = (
    # identity
    "game_id", "play_id", "old_game_id", "season", "week", "qtr", "time",
    "quarter_seconds_remaining", "game_seconds_remaining", "down", "ydstogo",
    "yardline_100", "posteam", "defteam", "posteam_type", "drive", "play_type",
    "desc", "game_date",
    # where the ball actually went
    "yards_gained", "air_yards", "yards_after_catch", "pass_length",
    "pass_location", "run_location", "run_gap", "kick_distance", "return_yards",
    "penalty_yards", "return_team",
    # how the play was run and how it ended
    "shotgun", "no_huddle", "qb_dropback", "qb_scramble", "qb_kneel", "qb_spike",
    "pass_attempt", "rush_attempt", "complete_pass", "incomplete_pass",
    "field_goal_result", "extra_point_result", "two_point_conv_result",
    "touchdown", "interception", "fumble_lost", "safety", "sack", "sp",
    "timeout", "penalty", "aborted_play", "special_teams_play",
)


def _req(url: str, method: str = "GET"):
    return urllib.request.Request(url, headers={"User-Agent": UA}, method=method)


def _head(url: str) -> dict:
    with urllib.request.urlopen(_req(url, "HEAD"), timeout=60) as r:
        return {"last_modified": r.headers.get("Last-Modified"),
                "etag": r.headers.get("ETag"),
                "length": r.headers.get("Content-Length")}


def _meta_path() -> pathlib.Path:
    return NFLVERSE_DIR / "meta.json"


def _meta() -> dict:
    try:
        return json.loads(_meta_path().read_text())
    except (OSError, ValueError):
        return {}


def _write_meta(meta: dict) -> None:
    try:
        NFLVERSE_DIR.mkdir(parents=True, exist_ok=True)
        _meta_path().write_text(json.dumps(meta, indent=1, sort_keys=True))
    except OSError:
        pass                                   # a cold cache is not a failure


def stamp() -> str | None:
    """When nflverse last rebuilt the play-by-play, in its own words."""
    try:
        with urllib.request.urlopen(_req(PBP_STAMP), timeout=60) as r:
            return json.loads(r.read().decode()).get("last_updated")
    except (OSError, ValueError):
        return None


def fetch(url: str, name: str, ttl: int = CACHE_TTL) -> pathlib.Path:
    """The release at `url`, on disk at `name`. Returns the cached path.

    Re-downloads only when nflverse says the bytes changed. The download goes
    to `<name>.part` and is renamed on completion, so a cancelled fetch cannot
    leave a truncated file that a later read would trust.
    """
    NFLVERSE_DIR.mkdir(parents=True, exist_ok=True)
    path, part = NFLVERSE_DIR / name, NFLVERSE_DIR / (name + ".part")
    meta = _meta()
    rec = meta.get(url) or {}
    fresh = path.exists() and time.time() - float(rec.get("fetched") or 0) < ttl
    if fresh:
        return path

    head = {}
    if path.exists():
        try:
            head = _head(url)
        except OSError:
            return path                        # offline, with bytes already here
        if head.get("last_modified") and head["last_modified"] == rec.get("last_modified"):
            rec["fetched"] = time.time()
            meta[url] = rec
            _write_meta(meta)
            return path

    with urllib.request.urlopen(_req(url), timeout=300) as r:
        head = {"last_modified": r.headers.get("Last-Modified"),
                "etag": r.headers.get("ETag"),
                "length": r.headers.get("Content-Length")}
        part.write_bytes(r.read())
    part.replace(path)
    meta[url] = {**head, "fetched": time.time(), "bytes": path.stat().st_size,
                 "name": name}
    if "play_by_play" in name:
        meta[url]["nflverse_last_updated"] = stamp()
    _write_meta(meta)
    return path


def _rows(path: pathlib.Path) -> list[dict]:
    raw = path.read_bytes()
    if path.suffix == ".gz":
        raw = gzip.decompress(raw)
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8", "replace"))))


def games() -> list[dict]:
    """Every scheduled game nflverse knows, including the ESPN id."""
    return _rows(fetch(SCHEDULES, "games.csv", ttl=LIVE_TTL))


def bridge() -> dict[str, dict]:
    """ESPN event id -> the game's schedule row. The crosswalk is published."""
    out = {}
    for r in games():
        espn = (r.get("espn") or "").strip()
        if espn:
            out[espn] = r
    return out


def _shard(season: int, game_id: str) -> pathlib.Path:
    return NFLVERSE_DIR / "pbp" / str(season) / f"{game_id}.json"


def season_plays(season: int, refresh: bool = False) -> int:
    """Shard a season's release per game. Returns how many games were written.

    The 19 MB release parses in a second or two; a shard is read in none. This
    is the only place the whole season is held in memory.
    """
    path = fetch(PBP.format(season=season), f"play_by_play_{season}.csv.gz",
                 ttl=0 if refresh else LIVE_TTL)
    rows = _rows(path)
    by_game: dict[str, list[dict]] = {}
    for r in rows:
        by_game.setdefault(r["game_id"], []).append({k: r.get(k) for k in KEPT})
    root = NFLVERSE_DIR / "pbp" / str(season)
    root.mkdir(parents=True, exist_ok=True)
    for game_id, plays in by_game.items():
        part = root / (game_id + ".json.part")
        part.write_text(json.dumps(plays))
        part.replace(root / (game_id + ".json"))
    meta = _meta()
    meta[f"pbp:{season}"] = {"games": len(by_game), "rows": len(rows),
                            "columns": len(rows[0]) if rows else 0,
                            "kept": len(KEPT), "sharded": time.time(),
                            "source": PBP.format(season=season)}
    _write_meta(meta)
    return len(by_game)


def game_plays(game_id: str, season: int | None = None, refresh: bool = False) -> list[dict]:
    """One game's rows, from the shard, sharding the season first if needed."""
    season = season or int(str(game_id)[:4])
    path = _shard(season, game_id)
    if refresh or not path.exists():
        season_plays(season, refresh=refresh)
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return []


def plays_for_espn(event: str, refresh: bool = False) -> tuple[list[dict], dict | None]:
    """(rows, schedule row) for an ESPN event id, or ([], None) if unbridged.

    A game nflverse has not published yet bridges to a schedule row with no
    plays behind it, which is the honest answer for a game still being played.
    """
    row = bridge().get(str(event))
    if not row:
        return [], None
    try:
        season = int(row["season"])
    except (KeyError, TypeError, ValueError):
        return [], row
    return game_plays(row["game_id"], season, refresh=refresh), row


def coverage(season: int) -> dict:
    """What is actually published for a season, and how fresh it is.

    Answers "can a game from last week be corrected yet" with nflverse's own
    timestamp and the last game it covers, rather than an assumed cadence.
    """
    sched = [r for r in games() if str(r.get("season")) == str(season)]
    played = [r for r in sched if (r.get("result") or "").strip() not in ("", "NA")]
    path = fetch(PBP.format(season=season), f"play_by_play_{season}.csv.gz", ttl=LIVE_TTL)
    rows = _rows(path)
    covered = sorted({r["game_id"] for r in rows})
    dates = sorted({r.get("game_date") or "" for r in rows})
    meta = _meta().get(PBP.format(season=season)) or {}
    return {
        "season": season,
        "scheduled": len(sched),
        "played": len(played),
        "in_pbp": len(covered),
        "weeks": sorted({r.get("week") for r in rows}, key=lambda w: int(w or 0)),
        "last_game_date": dates[-1] if dates else None,
        "missing": [r["game_id"] for r in played if r["game_id"] not in set(covered)],
        "release_last_modified": meta.get("last_modified"),
        "nflverse_last_updated": meta.get("nflverse_last_updated") or stamp(),
    }


# ─────────────────────── what advanced.py needs, shared ────────────────────

def csv_rows(url: str) -> list[dict]:
    """A plain CSV release, parsed. Kept here so one module owns the fetch."""
    with urllib.request.urlopen(_req(url), timeout=120) as r:
        return list(csv.DictReader(io.StringIO(r.read().decode("utf-8", "replace"))))


def cached_json(name: str, build):
    """A derived JSON blob, rebuilt at most daily."""
    path = CACHE_DIR / name
    if path.exists() and time.time() - path.stat().st_mtime < CACHE_TTL:
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            pass
    data = build()
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
    except OSError:
        pass
    return data
