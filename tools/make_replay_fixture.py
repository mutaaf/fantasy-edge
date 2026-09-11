"""Regenerate the replay test fixtures from a real ESPN game.

    python3 tools/make_replay_fixture.py [--event 401872656] [--drives 8]

Writes `tests/fixtures/replay_scoreboard.json` and
`tests/fixtures/replay_summary.json`: the first few drives of one finished
game, with the bulk ESPN ships alongside them - logos, odds, videos, news,
standings, per-play `$ref` links - thrown away.

It is deterministic because a finished game is immutable: event 401872656 will
report the same 179 plays in the same order for as long as ESPN serves it. The
trim keeps ESPN's own shapes rather than a hand-written approximation, which is
the whole point - `frame()` is tested against the payload it will actually be
handed, including the awkward parts (a play whose `yardsToEndzone` is measured
against the other team's end zone, a win-probability point whose `playId` is a
drive id, an "Official Timeout" record with no yardage).

Never edit the fixtures by hand. Hand-edited fixtures have already cost this
repository one silent 74% data loss.
"""

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fantasyedge import replay as rp                       # noqa: E402
from fantasyedge.live import _get_json, scoreboard_url, summary_url, with_key  # noqa: E402

FIX = pathlib.Path(__file__).resolve().parents[1] / "tests" / "fixtures"
CAPTURE = pathlib.Path(__file__).resolve().parents[1] / "data" / "replay" / "source"

# Whole sections of the summary no part of the live tier or the gamecast reads.
SUMMARY_DROP = ("article", "videos", "news", "pickcenter", "odds", "standings",
                "againstTheSpread", "broadcasts", "leaders", "format",
                "gameInfo", "meta", "injuries")
COMP_DROP = ("headlines", "broadcasts", "geoBroadcasts", "highlights", "notes",
             "odds", "leaders", "venue", "tickets", "format")


def slim_team(team: dict) -> dict:
    """A club, minus the eight logo variants ESPN ships with every mention."""
    return {k: v for k, v in team.items()
            if k in ("id", "uid", "abbreviation", "displayName", "shortDisplayName",
                     "name", "location", "color", "alternateColor")}


def slim_play(play: dict) -> dict:
    """A play, minus the core-API links. `teamParticipants` is kept, without
    its `$ref`s, because possession is read off `start.team`/`end.team` and a
    reader that drops the participants entirely would not notice if it broke."""
    out = {k: v for k, v in play.items() if k != "teamParticipants"}
    out["teamParticipants"] = [
        {"id": tp.get("id"), "order": tp.get("order"), "type": tp.get("type")}
        for tp in (play.get("teamParticipants") or [])]
    return out


def trim_summary(summary: dict, drives: int) -> dict:
    out = {k: v for k, v in summary.items() if k not in SUMMARY_DROP}

    kept = (summary.get("drives") or {}).get("previous", [])[:drives]
    out["drives"] = {"previous": [
        {**{k: v for k, v in d.items() if k != "team"},
         "team": slim_team(d.get("team") or {}),
         "plays": [slim_play(p) for p in (d.get("plays") or [])]}
        for d in kept]}

    ids = {str(p.get("id")) for d in kept for p in (d.get("plays") or [])}
    # Positional, not membership: the leading win-probability point names the
    # opening drive rather than a play, and dropping it would hide the one case
    # `frame()` has to handle specially.
    wp = summary.get("winprobability") or []
    keep = 0
    for i, w in enumerate(wp):
        if str(w.get("playId")) in ids:
            keep = i + 1
    out["winprobability"] = [{"homeWinPercentage": w.get("homeWinPercentage"),
                              "tiePercentage": w.get("tiePercentage"),
                              "playId": w.get("playId")} for w in wp[:keep]]
    out["scoringPlays"] = [{**{k: v for k, v in sp.items() if k != "team"},
                            "team": slim_team(sp.get("team") or {})}
                           for sp in (summary.get("scoringPlays") or [])
                           if str(sp.get("id")) in ids]

    head = dict(summary.get("header") or {})
    head.pop("links", None)
    comp = dict((head.get("competitions") or [{}])[0])
    for key in COMP_DROP:
        comp.pop(key, None)
    comp["competitors"] = [
        {**{k: v for k, v in c.items()
            if k in ("id", "uid", "order", "homeAway", "winner", "score",
                     "linescores", "possession")},
         "team": slim_team(c.get("team") or {})}
        for c in (comp.get("competitors") or [])]
    head["competitions"] = [comp]
    out["header"] = head

    # The box score is kept deliberately, and kept whole for two athletes: the
    # tests assert that a replay does NOT touch it, and an empty one would let
    # that assertion pass for the wrong reason.
    box = summary.get("boxscore") or {}
    players = []
    for team in (box.get("players") or []):
        cats = []
        for cat in (team.get("statistics") or [])[:3]:
            cats.append({**cat, "athletes": (cat.get("athletes") or [])[:2]})
        players.append({"team": slim_team(team.get("team") or {}), "statistics": cats})
    out["boxscore"] = {"players": players, "teams": box.get("teams") or []}
    return out


def trim_scoreboard(board: dict, event: str) -> dict:
    ev = rp._event(board, event)
    if not ev:
        raise SystemExit(f"event {event} is not on this scoreboard")
    ev = dict(ev)
    ev.pop("links", None)
    comp = dict((ev.get("competitions") or [{}])[0])
    for key in COMP_DROP:
        comp.pop(key, None)
    comp["competitors"] = [
        {**{k: v for k, v in c.items()
            if k in ("id", "uid", "type", "order", "homeAway", "winner", "score",
                     "linescores")},
         "team": slim_team(c.get("team") or {})}
        for c in (comp.get("competitors") or [])]
    ev["competitions"] = [comp]
    return {"leagues": [], "season": board.get("season"), "week": board.get("week"),
            "events": [ev]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--event", default="401872656")
    ap.add_argument("--drives", type=int, default=8)
    ap.add_argument("--offline", action="store_true",
                    help="require a local capture rather than fetching")
    args = ap.parse_args()

    game = CAPTURE / f"{args.event}.json"
    board_file = CAPTURE / "scoreboard.json"
    if game.exists() and board_file.exists():
        summary = json.loads(game.read_text())
        board = json.loads(board_file.read_text())
    elif args.offline:
        raise SystemExit(f"no capture in {CAPTURE}; drop --offline to fetch it")
    else:
        summary = _get_json(with_key(summary_url(args.event)))
        board = _get_json(with_key(scoreboard_url()))

    sm = trim_summary(summary, args.drives)
    sb = trim_scoreboard(board, args.event)
    FIX.mkdir(parents=True, exist_ok=True)
    (FIX / "replay_summary.json").write_text(json.dumps(sm, indent=1, sort_keys=True))
    (FIX / "replay_scoreboard.json").write_text(json.dumps(sb, indent=1, sort_keys=True))
    plays = rp._all_plays(sm)
    print(f"event {args.event}: {len(sm['drives']['previous'])} drives, "
          f"{len(plays)} plays, 0-{rp.total_seconds(sm)}s, "
          f"{len(sm['winprobability'])} win-prob points, "
          f"{len(sm['scoringPlays'])} scoring plays")


if __name__ == "__main__":
    main()
