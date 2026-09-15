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

from . import text as words
from .parse import _int, status_of, team_record

TURNOVER_RESULTS = {"Fumble", "Interception", "Downs", "Turnover on Downs", "Blocked Punt", "Blocked FG"}


def _play(pl: dict) -> dict:
    st, en = pl.get("start") or {}, pl.get("end") or {}
    return {
        "id": str(pl.get("id") or ""),
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


def game_from_summary(event: str, data: dict) -> dict:
    head = data.get("header") or {}
    comp = (head.get("competitions") or [{}])[0]
    st = status_of(comp.get("status") or {})
    sides = {}
    for c in comp.get("competitors") or []:
        t = team_record(c)
        t["linescores"] = [_int(l.get("displayValue"), 0) for l in c.get("linescores") or []]
        sides[(c.get("homeAway") or "").lower()] = t

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
        plays = [_play(p) for p in d.get("plays") or []
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
        "boxscore": box,
        "leaders": leaders,
        "venue": ((info.get("venue") or {}).get("fullName")) or "",
        "weather": {"temperature": (info.get("weather") or {}).get("temperature")} if info.get("weather") else None,
    }
