"""The list of leagues this install follows, and how to build a board from it.

Two problems this fixes. Leagues used to be re-added by hand every session,
because the only record of them lived in one browser's local storage. And the
board used to be built by calling the provider at startup, so it needed the
network and a live cookie just to draw a page about seasons already sitting in
SQLite.

Now the roster of leagues is a file in `~/.fantasy-edge/`, and everything the
board renders is read back out of the local database. The network is needed
only to pull new data or follow a draft that is actually running.
"""

from __future__ import annotations

import json
import os
import pathlib

CONFIG = pathlib.Path.home() / ".fantasy-edge" / "leagues.json"
DEFAULT_SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "DEF", "K"]


# ───────────────────────────── the roster of leagues ─────────────────────────

def load() -> list[dict]:
    try:
        data = json.loads(CONFIG.read_text())
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def save(entries: list[dict]) -> None:
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(entries, indent=2))


def add(provider: str, league_id: str, label: str = "",
        also: tuple[str, ...] = ()) -> list[dict]:
    entries = [e for e in load()
               if not (e["provider"] == provider and e["league_id"] == str(league_id))]
    entries.append({"provider": provider, "league_id": str(league_id),
                    "label": label, "also": [str(a) for a in also]})
    save(entries)
    return entries


def remove(league_id: str) -> list[dict]:
    entries = [e for e in load() if e["league_id"] != str(league_id)]
    save(entries)
    return entries


# ───────────────────────── building a board from the db ──────────────────────

def _swid() -> str:
    return (os.environ.get("ESPN_SWID") or "").upper().strip("{}")


def config_from_db(store, provider: str, league_id: str, season: int,
                   also: tuple[str, ...] = (), label: str = "") -> dict | None:
    """A league's shape, order and your seat in it, read from stored rows.

    Returns None when nothing for that league has been pulled yet, which is
    the honest answer rather than a page of blanks.
    """
    rows = store.q(
        "SELECT name, team_count FROM league WHERE provider=? AND league_id=? AND season=?",
        (provider, str(league_id), season))
    if not rows:
        return None
    name = rows[0]["name"] or label or f"League {league_id}"
    teams = int(rows[0]["team_count"] or 0)

    mgrs = store.q(
        "SELECT team_id, name, owner FROM manager "
        "WHERE provider=? AND league_id=? AND season=?",
        (provider, str(league_id), season))
    if not mgrs:
        return None
    teams = teams or len(mgrs)

    picks = store.q(
        "SELECT overall, round, team_id FROM draft_pick "
        "WHERE provider=? AND league_id=? AND season=? ORDER BY overall",
        (provider, str(league_id), season))
    slot_of = {p["team_id"]: p["overall"] for p in picks if p["round"] == 1}
    rounds = (len(picks) // teams) if teams and picks else 0

    me = _swid()
    mine = next((m for m in mgrs
                 if (m["owner"] or "").upper().strip("{}") == me), None)

    ordered = sorted(mgrs, key=lambda m: slot_of.get(m["team_id"], 99))
    return {
        "id": f"{provider}-{league_id}", "provider": provider,
        "leagueId": str(league_id), "also": [str(a) for a in also],
        "name": name, "teams": teams, "rounds": rounds or 16,
        "bench": max((rounds or 16) - len(DEFAULT_SLOTS), 0),
        "slots": DEFAULT_SLOTS,
        "season": season,
        "slot": slot_of.get(mine["team_id"]) if mine else 1,
        "myTid": mine["team_id"] if mine else "",
        "myTeam": mine["name"] if mine else "",
        "drafted": bool(picks),
        "scoring": "",
        "order": [m["team_id"] for m in ordered],
        "mgrs": [],          # filled from the dossier, which knows the history
    }


def latest_season(store, provider: str, league_id: str) -> int:
    rows = store.q("SELECT MAX(season) AS s FROM league WHERE provider=? AND league_id=?",
                   (provider, str(league_id)))
    return int(rows[0]["s"]) if rows and rows[0]["s"] else 0


def draft_log(store, provider: str, league_id: str, season: int) -> list[list]:
    rows = store.q(
        """SELECT d.overall, d.round, d.team_id, p.name AS nm, p.pos AS pos,
                  a.rank AS adp, m.name AS team
           FROM draft_pick d
           LEFT JOIN player p ON p.provider=d.provider AND p.player_id=d.player_id
           LEFT JOIN manager m ON m.provider=d.provider AND m.league_id=d.league_id
                              AND m.season=d.season AND m.team_id=d.team_id
           LEFT JOIN adp a ON a.season=d.season AND a.provider=d.provider
                          AND a.player_id=d.player_id
           WHERE d.provider=? AND d.league_id=? AND d.season=?
           ORDER BY d.overall""",
        (provider, str(league_id), season))
    return [[r["overall"], r["round"], r["team"] or r["team_id"], r["nm"] or "?",
             r["pos"] or "?", round(r["adp"], 1) if r["adp"] is not None else None]
            for r in rows]
