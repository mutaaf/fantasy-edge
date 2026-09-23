"""Regenerate the replay test fixtures from a real ESPN game.

    python3 tools/make_replay_fixture.py [--event 401872656] [--drives 7]
    python3 tools/make_replay_fixture.py --event 401872656 --pbp

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
import gzip
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

    # The box score is kept whole, athlete list and all. It used to be cut to
    # two athletes per category; that stopped working the day `frame()` began
    # deriving the box score from the play text, because the derivation
    # resolves a name in a play against the box score's own athlete list and a
    # truncated list resolves nobody. It is also the ground truth the
    # reconciliation test diffs against, so cutting it would be cutting the
    # thing under test.
    box = summary.get("boxscore") or {}
    out["boxscore"] = {
        "players": [{"team": slim_team(team.get("team") or {}),
                     "statistics": team.get("statistics") or []}
                    for team in (box.get("players") or [])],
        "teams": box.get("teams") or [],
    }
    return out


# What the box-score derivation reads off a play, and nothing else. A whole
# game of full play records is 600KB; this is the same 179 plays at a tenth of
# that, which is what makes it reasonable to check in two of them.
PBP_KEEP = ("id", "text", "statYardage", "scoringPlay", "awayScore", "homeScore")


def trim_pbp(summary: dict) -> dict:
    """A whole game, cut to the plays and the final box score.

    The reconciliation fixture. `frame()` needs drives, win probability and a
    scoreboard; this needs neither - it is the parser's acceptance test, and
    the only two things it compares are what the text says and what ESPN
    published.
    """
    drives = []
    for d in rp._drives(summary):
        plays = []
        for p in (d.get("plays") or []):
            keep = {k: p[k] for k in PBP_KEEP if k in p}
            keep["type"] = {"text": (p.get("type") or {}).get("text")}
            keep["period"] = {"number": (p.get("period") or {}).get("number")}
            keep["clock"] = {"displayValue": (p.get("clock") or {}).get("displayValue")}
            keep["start"] = {"team": {"id": str((((p.get("start") or {})
                                                  .get("team")) or {}).get("id") or "")}}
            plays.append(keep)
        drives.append({"team": slim_team(d.get("team") or {}), "plays": plays})
    box = summary.get("boxscore") or {}
    return {
        "header": {"id": (summary.get("header") or {}).get("id"),
                   "competitions": [{"competitors": [
                       {"homeAway": c.get("homeAway"),
                        "team": slim_team(c.get("team") or {})}
                       for c in (((summary.get("header") or {})
                                  .get("competitions") or [{}])[0]
                                 .get("competitors") or [])]}]},
        "drives": {"previous": drives},
        "boxscore": {"players": [{"team": slim_team(t.get("team") or {}),
                                  "statistics": t.get("statistics") or []}
                                 for t in (box.get("players") or [])],
                     "teams": box.get("teams") or []},
    }


# A whole game for the scene and the director: every drive and play, win
# probability and scoring plays, and no box score. The box score is the
# reconciliation fixture's job; here it would be 300KB of stat lines that the
# geometry never reads.
GAME_PLAY_KEEP = ("id", "text", "statYardage", "scoringPlay", "isTurnover", "isPenalty",
                  "awayScore", "homeScore")
GAME_SIDE_KEEP = ("down", "distance", "yardLine", "yardsToEndzone", "downDistanceText",
                  "possessionText")


def trim_game(summary: dict, board: dict, event: str) -> dict:
    drives = []
    for d in rp._drives(summary):
        plays = []
        for p in (d.get("plays") or []):
            keep = {k: p[k] for k in GAME_PLAY_KEEP if k in p}
            keep["type"] = {"text": (p.get("type") or {}).get("text")}
            keep["period"] = {"number": (p.get("period") or {}).get("number")}
            keep["clock"] = {"displayValue": (p.get("clock") or {}).get("displayValue")}
            for side in ("start", "end"):
                raw = p.get(side) or {}
                keep[side] = {k: raw[k] for k in GAME_SIDE_KEEP if k in raw}
                keep[side]["team"] = {"id": str(((raw.get("team") or {}).get("id")) or "")}
            plays.append(keep)
        drives.append({**{k: d[k] for k in ("id", "description", "displayResult", "result",
                                           "isScore", "yards") if k in d},
                       "team": slim_team(d.get("team") or {}), "plays": plays})
    out = trim_summary(summary, 0)
    out.pop("boxscore", None)
    out["drives"] = {"previous": drives}
    out["winprobability"] = [{"homeWinPercentage": w.get("homeWinPercentage"),
                              "playId": w.get("playId")}
                             for w in (summary.get("winprobability") or [])]
    out["scoringPlays"] = [{**{k: v for k, v in sp.items() if k in
                               ("id", "text", "awayScore", "homeScore", "period", "clock",
                                "type", "scoringType")},
                            "team": slim_team(sp.get("team") or {})}
                           for sp in (summary.get("scoringPlays") or [])]
    return {"event": event, "scoreboard": trim_scoreboard(board, event), "summary": out}


def from_capture(root: pathlib.Path, event: str) -> tuple[dict, dict]:
    """A game out of a weekend recorder's capture: `final/<event>.json.gz` and
    the newest `scoreboard/*.json.gz` that carries it.

    The recorder writes gzipped ESPN bytes in a layout of its own, which is
    how a college fixture gets made at all: this repository's own captures are
    NFL, and a fixture must never be assembled by hand.
    """
    summary = json.loads(gzip.decompress((root / "final" / f"{event}.json.gz").read_bytes()))
    for path in sorted((root / "scoreboard").glob("*.json.gz"), reverse=True):
        board = json.loads(gzip.decompress(path.read_bytes()))
        events = [e for e in (board.get("events") or []) if str(e.get("id")) == event]
        if events:
            return {**board, "events": events}, summary
    raise SystemExit(f"event {event} is on no scoreboard under {root}")


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


def trim_week(board: dict) -> dict:
    """A whole week's slate, every game, with only what a picker reads.

    `trim_scoreboard` keeps one event because a replay drives one game. A week
    fixture is the opposite shape - sixteen games and no play-by-play - and it
    is what `week.py` is tested against: the states that decide whether a week
    is finished, and the `linescores` every quarter-resolution reason is read
    from.
    """
    events = []
    for ev in (board.get("events") or []):
        ev = {k: v for k, v in ev.items()
              if k in ("id", "uid", "date", "name", "shortName", "season", "week")}
        src = rp._event(board, str(ev.get("id")))
        comp = dict(((src or {}).get("competitions") or [{}])[0])
        for key in COMP_DROP:
            comp.pop(key, None)
        comp = {k: v for k, v in comp.items()
                if k in ("id", "date", "status", "competitors", "attendance")}
        comp["competitors"] = [
            {**{k: v for k, v in c.items()
                if k in ("id", "homeAway", "winner", "score", "linescores")},
             "team": slim_team(c.get("team") or {})}
            for c in (comp.get("competitors") or [])]
        ev["competitions"] = [comp]
        events.append(ev)
    return {"leagues": [{"season": ((board.get("leagues") or [{}])[0].get("season"))}],
            "season": board.get("season"), "week": board.get("week"),
            "events": events}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--event", default="401872656")
    ap.add_argument("--drives", type=int, default=7)
    ap.add_argument("--pbp", action="store_true",
                    help="write the whole-game reconciliation fixture instead")
    ap.add_argument("--offline", action="store_true",
                    help="require a local capture rather than fetching")
    ap.add_argument("--game", action="store_true",
                    help="write the whole-game scene fixture, tests/fixtures/replay_game_EVENT.json, "
                         "from a capture made with `replay --capture`")
    ap.add_argument("--nflverse", action="store_true",
                    help="write tests/fixtures/nflverse_pbp_EVENT.json: the game's published "
                         "play-by-play rows, which correct a replay's geometry")
    ap.add_argument("--day", metavar="YYYY-MM-DD",
                    help="write tests/fixtures/day_slate.json and day_game_*.json: a "
                         "pulled day trimmed to two games, for the day-replay tests")
    ap.add_argument("--day-root", default="data/replay/day",
                    help="where --day reads the pulled day from")
    ap.add_argument("--day-games", type=int, default=2, help="how many games to keep")
    ap.add_argument("--day-plays", type=int, default=60, help="plays per game to keep")
    ap.add_argument("--week", type=int,
                    help="write a week's slate fixture, tests/fixtures/week_slate_SEASON_TYPE_WEEK.json")
    ap.add_argument("--from-capture", default="",
                    help="build --game from a weekend recorder's capture directory "
                         "(final/<event>.json.gz plus scoreboard/), rather than this "
                         "repository's own data/replay/source")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--seasontype", type=int, default=2)
    args = ap.parse_args()

    if args.nflverse:
        from fantasyedge import nflverse as nv
        rows, sched = nv.plays_for_espn(args.event, refresh=True)
        if not sched:
            raise SystemExit(f"event {args.event} is not in nflverse's schedules")
        if not rows:
            raise SystemExit(f"{sched['game_id']} is not published yet")
        out = FIX / f"nflverse_pbp_{args.event}.json"
        out.write_text(json.dumps({"event": args.event, "gameId": sched["game_id"],
                                   "source": nv.PBP.format(season=int(sched["season"])),
                                   "plays": rows},
                                  indent=1, sort_keys=True))
        print(f"event {args.event}: {sched['game_id']}, {len(rows)} nflverse plays "
              f"-> {out} ({out.stat().st_size // 1024} KB)")
        return

    if args.day:
        from fantasyedge import dayreplay as dy

        board, summaries = dy.load_day(pathlib.Path(args.day_root), args.day)
        keep = [str(ev.get("id")) for ev in (board.get("events") or [])
                if str(ev.get("id")) in summaries][:args.day_games]
        slim_board = {k: v for k, v in board.items() if k != "events"}
        slim_board["events"] = [ev for ev in board["events"] if str(ev.get("id")) in keep]
        out = FIX / "day_slate.json"
        out.write_text(json.dumps(slim_board, indent=1, sort_keys=True))
        print(f"{args.day}: {len(keep)} games -> {out} ({out.stat().st_size // 1024} KB)")
        for event in keep:
            summary = summaries[event]
            drives, left = [], args.day_plays
            for d in ((summary.get("drives") or {}).get("previous") or []):
                if left <= 0:
                    break
                plays = [slim_play(p) for p in (d.get("plays") or [])][:left]
                left -= len(plays)
                drives.append({**{k: v for k, v in d.items()
                                  if k in ("id", "description", "displayResult", "result")},
                               "team": slim_team(d.get("team") or {}), "plays": plays})
            ids = {str(p.get("id")) for d in drives for p in d["plays"]}
            head = dict(summary.get("header") or {})
            head.pop("links", None)
            comp = dict((head.get("competitions") or [{}])[0])
            for key in COMP_DROP:
                comp.pop(key, None)
            comp["competitors"] = [
                {**{k: v for k, v in c.items()
                    if k in ("id", "order", "homeAway", "winner", "score")},
                 "team": slim_team(c.get("team") or {})}
                for c in (comp.get("competitors") or [])]
            head["competitions"] = [comp]
            trimmed = {"header": head, "drives": {"previous": drives},
                       "scoringPlays": [{**{k: v for k, v in sp.items() if k != "team"},
                                         "team": slim_team(sp.get("team") or {})}
                                        for sp in (summary.get("scoringPlays") or [])
                                        if str(sp.get("id")) in ids]}
            path = FIX / f"day_game_{event}.json"
            path.write_text(json.dumps(trimmed, indent=1, sort_keys=True))
            print(f"  {event}: {len(ids)} plays -> {path} "
                  f"({path.stat().st_size // 1024} KB)")
        return

    if args.week:
        from fantasyedge import week as wk

        board = _get_json(with_key(wk.week_url(args.season, args.week, args.seasontype)))
        out = FIX / f"week_slate_{args.season}_{args.seasontype}_{args.week}.json"
        FIX.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(trim_week(board), indent=1, sort_keys=True))
        print(f"{args.season} type {args.seasontype} week {args.week}: "
              f"{len(board.get('events') or [])} games, state "
              f"{wk.week_state(board)} -> {out} ({out.stat().st_size // 1024} KB)")

        return

    if args.game:
        board, summary = (from_capture(pathlib.Path(args.from_capture), args.event)
                          if args.from_capture else rp.load(CAPTURE, args.event))
        out = FIX / f"replay_game_{args.event}.json"
        out.write_text(json.dumps(trim_game(summary, board, args.event), sort_keys=True,
                                  separators=(",", ":")))
        print(f"event {args.event}: {len(rp._all_plays(summary))} plays, "
              f"{rp.total_seconds(summary)}s -> {out} ({out.stat().st_size // 1024} KB)")
        return

    game = CAPTURE / f"{args.event}.json"
    board_file = rp.scoreboard_path(CAPTURE, args.event)
    if not board_file.exists():
        board_file = CAPTURE / "scoreboard.json"
    if not game.exists():
        alt = pathlib.Path(f"/tmp/rp{args.event[-3:]}/source/{args.event}.json")
        if alt.exists():
            game, board_file = alt, alt.parent / "scoreboard.json"
    if game.exists() and board_file.exists():
        summary = json.loads(game.read_text())
        board = json.loads(board_file.read_text())
    elif args.offline:
        raise SystemExit(f"no capture in {CAPTURE}; drop --offline to fetch it")
    else:
        summary = _get_json(with_key(summary_url(args.event)))
        board = _get_json(with_key(scoreboard_url()))

    if args.pbp:
        out = FIX / f"replay_pbp_{args.event}.json"
        out.write_text(json.dumps(trim_pbp(summary), indent=1, sort_keys=True))
        checked = rp.reconcile(summary)
        print(f"event {args.event}: {len(rp._all_plays(summary))} plays, "
              f"reconciles {checked['matched']}/{checked['cells']} cells "
              f"({checked['rate']:.1%}) -> {out}")
        return

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
