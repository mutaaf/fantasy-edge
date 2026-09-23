"""One college game from its ESPN summary, in gamecast shape.

# INTEGRATE: shared gamecast shaping from fantasy-edge scene/replay branch.
# fantasy-edge's `API.gamecast` is the one owner of "a summary in the shape a
# field draws". This adapter mirrors its field names exactly (drives[].plays[]
# with from/to as yards to the end zone, winProbability[{play, home}],
# scoringPlays[]) so the swap is a deletion. What stays college-only after
# integration: rank, overtime count, completion from status, box score
# labels and leaders, which the NFL shape does not carry.
"""
from __future__ import annotations

import re

from . import league, text as words
from .parse import _int, status_of, team_record

TURNOVER_RESULTS = {"Fumble", "Interception", "Downs", "Turnover on Downs", "Blocked Punt", "Blocked FG"}


def _play(pl: dict, abbr_of: dict[str, str] | None = None) -> dict:
    st, en = pl.get("start") or {}, pl.get("end") or {}
    return {
        "id": str(pl.get("id") or ""),
        # Yards from the HOME goal line - ESPN's own `yardLine` - which is what
        # the shared scene draws from. Unlike `yardsToEndzone` below it is
        # fixed to the field: it does not flip with possession, and it is not
        # the placeholder a timeout carries or the punter's own line a punt
        # does. `from`/`to` stay for the 2D field bar, which is drawn from the
        # offence's point of view.
        "fromYard": st.get("yardLine"),
        "toYard": en.get("yardLine"),
        # Who snapped it. A drive's team is not enough: a pick-six is in the
        # offence's drive and scored by the defence.
        "team": (abbr_of or {}).get(str((st.get("team") or {}).get("id") or ""), ""),
        "text": words.play(pl.get("text")),
        "type": (pl.get("type") or {}).get("text", ""),
        "clock": (pl.get("clock") or {}).get("displayValue", ""),
        "period": (pl.get("period") or {}).get("number", 0),
        "down": st.get("down"),
        "distance": st.get("distance"),
        "downText": st.get("downDistanceText") or None,
        "from": st.get("yardsToEndzone"),
        "to": en.get("yardsToEndzone"),
        "yards": pl.get("statYardage"),
        "scoring": bool(pl.get("scoringPlay")),
        "turnover": bool(pl.get("isTurnover")),
        "penalty": bool(pl.get("isPenalty")),
        "home": _int(pl.get("homeScore"), 0),
        "away": _int(pl.get("awayScore"), 0),
    }


def game_from_summary(event: str, data: dict, situation: dict | None = None) -> dict:
    head = data.get("header") or {}
    comp = (head.get("competitions") or [{}])[0]
    st = status_of(comp.get("status") or {})
    sides = {}
    for c in comp.get("competitors") or []:
        t = team_record(c)
        t["linescores"] = [_int(l.get("displayValue"), 0) for l in c.get("linescores") or []]
        sides[(c.get("homeAway") or "").lower()] = t

    abbr_of = {str(t.get("id") or ""): t.get("abbr", "") for t in sides.values()}
    raw = data.get("drives") or {}
    current = raw.get("current")
    previous = raw.get("previous") or []
    # ESPN lists the drive in progress in `previous` as well as in `current`.
    # Keyed on id it appears once, in its place, taken from `current`.
    seen = {str(d.get("id")) for d in previous}
    ordered = [current if current and str(d.get("id")) == str(current.get("id")) else d for d in previous]
    if current and str(current.get("id")) not in seen:
        ordered.append(current)
    drives = []
    for d in ordered:
        plays = [_play(p, abbr_of) for p in d.get("plays") or []
                 if (p.get("type") or {}).get("text") not in ("End Period", "End of Half", "End of Game")]
        result = d.get("displayResult") or d.get("result") or ""
        drives.append({
            "id": str(d.get("id") or ""),
            "team": ((d.get("team") or {}).get("abbreviation") or "").upper(),
            "description": d.get("description") or "",
            "result": words.result(result),
            "scored": bool(d.get("isScore")),
            "turnover": result in TURNOVER_RESULTS,
            "current": bool(current) and str(d.get("id")) == str(current.get("id")) and not st["completed"],
            "yards": d.get("yards"),
            "plays": plays,
        })

    wp = [{"play": str(w.get("playId") or ""), "home": w.get("homeWinPercentage")}
          for w in data.get("winprobability") or [] if w.get("homeWinPercentage") is not None]

    box = []
    for t in (data.get("boxscore") or {}).get("teams") or []:
        box.append({"team": ((t.get("team") or {}).get("abbreviation") or "").upper(),
                    "stats": [{"label": s.get("label") or "", "value": (s.get("displayValue") or "").strip()}
                              for s in t.get("statistics") or []]})
    leaders = []
    for p in (data.get("boxscore") or {}).get("players") or []:
        team = ((p.get("team") or {}).get("abbreviation") or "").upper()
        for cat in (p.get("statistics") or [])[:3]:
            if not cat.get("athletes"):
                continue
            a = cat["athletes"][0]
            leaders.append({"team": team, "category": cat.get("name") or "",
                            "name": (a.get("athlete") or {}).get("displayName") or "",
                            "labels": cat.get("labels") or [], "stats": a.get("stats") or []})

    last = next((d["plays"][-1] for d in reversed(drives) if d["plays"]), None)
    info = data.get("gameInfo") or {}
    return {
        "event": str(event),
        # The scene reads the code of football from the game, not from the
        # caller: college hash marks are 3.58 yards wider than the NFL's, and a
        # Saturday drawn as a Sunday puts every play off across the field.
        "league": league.LEAGUE,
        # What the shared scene reads at the top level: it draws a pre-game
        # field empty, a live one with the ball where the situation says, and
        # a finished one with the whole night's arcs laid down.
        "state": st["state"],
        "period": st["period"],
        "clock": st["clock"],
        # ESPN's own situation block, passed through rather than reshaped: the
        # scene wants `yardLine` (fixed to the field) and the down and
        # distance, and a summary's header does not carry them - the board
        # does, which is why the handler hands it in.
        "situation": situation or {},
        "status": st,
        "home": sides.get("home"),
        "away": sides.get("away"),
        "possession": next((str((c.get("team") or {}).get("id")) for c in comp.get("competitors") or []
                            if c.get("possession") and not st["completed"]), None),
        "lastPlay": last,
        "drives": drives,
        "winProbability": wp,
        "winProbabilitySource": "ESPN",
        "scoringPlays": [{
            "text": words.play(sp.get("text")),
            "clock": (sp.get("clock") or {}).get("displayValue", ""),
            "period": (sp.get("period") or {}).get("number", 0),
            "team": ((sp.get("team") or {}).get("abbreviation") or "").upper(),
            "home": _int(sp.get("homeScore"), 0),
            "away": _int(sp.get("awayScore"), 0),
        } for sp in data.get("scoringPlays") or []],
        # Before kickoff ESPN's "box score" is each team's season per-game
        # averages; shown as this game's totals it reads 586 yards for a game
        # that has not started. It moves to seasonAverages until kickoff.
        "boxscore": [] if st["state"] == "pre" else box,
        "seasonAverages": box if st["state"] == "pre" else [],
        "leaders": leaders,
        "venue": ((info.get("venue") or {}).get("fullName")) or "",
        "weather": {"temperature": (info.get("weather") or {}).get("temperature")} if info.get("weather") else None,
    }
