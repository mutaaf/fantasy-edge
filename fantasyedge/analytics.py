"""Analytics.

Each analysis is a pure function: store in, `Result` out. No printing, no
formatting, no file writing. That keeps them trivially testable and lets
the CLI and the HTML report share exactly the same numbers.

Every result carries a `caveat` where the method has a real limitation.
An analysis that hides its own weaknesses is worse than no analysis.
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

from .store import Store

SCOPE = "provider=? AND league_id=?"


@dataclass
class Result:
    key: str
    title: str
    headline: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    caveat: str = ""
    note: str = ""

    @property
    def empty(self) -> bool:
        return not self.rows


def _owner_map(store: Store, provider: str, league: str) -> dict[tuple[int, str], str]:
    """Team ids are stable within a season but team names are not.

    Owner is the durable identity, so grouping still keys on it. But an owner
    id is an opaque GUID on ESPN, and printing that helps nobody, so every
    season of one owner is labelled with the newest team name they used.
    """
    rows = store.q(
        f"SELECT season, team_id, name, owner FROM manager WHERE {SCOPE}",
        (provider, league),
    )
    latest: dict[str, tuple[int, str]] = {}
    for r in rows:
        key = r["owner"] or r["name"] or r["team_id"]
        seen = latest.get(key)
        if r["name"] and (seen is None or r["season"] >= seen[0]):
            latest[key] = (r["season"], r["name"])
    return {
        (r["season"], r["team_id"]):
            latest.get(r["owner"] or r["name"] or r["team_id"],
                       (0, r["owner"] or r["name"] or r["team_id"]))[1]
        for r in rows
    }


# ─────────────────────────── 1. draft ROI by round ───────────────────────────

def draft_roi_by_round(store: Store, provider: str, league: str) -> Result:
    """Points a pick returned, versus what that round returned league-wide.

    A round you are consistently negative in is a systematic leak, not bad
    luck. Rounds 3 through 6 are where most managers quietly bleed.
    """
    rows = store.q(
        f"""
        SELECT d.season, d.round, d.team_id,
               COALESCE(SUM(r.points), 0) AS pts
        FROM draft_pick d
        LEFT JOIN roster_slot r
          ON  r.provider=d.provider AND r.league_id=d.league_id
          AND r.season=d.season AND r.player_id=d.player_id
        WHERE d.provider=? AND d.league_id=?
        GROUP BY d.season, d.round, d.team_id, d.overall
        """,
        (provider, league),
    )
    if not rows:
        return Result("draft_roi", "Draft ROI by round",
                      caveat="Needs both draft results and weekly roster points.")

    if not any(r["pts"] for r in rows):
        # Draft results loaded but no weekly scoring. Returning a table of
        # zeros would look like a finding; saying so is the honest output.
        return Result(
            "draft_roi", "Draft ROI by round",
            caveat="Draft picks are loaded but no weekly player points are. "
                   "This analysis needs roster_slot rows, which the manual "
                   "paste provider cannot supply. Use the ESPN or Yahoo "
                   "provider for it.",
        )

    owners = _owner_map(store, provider, league)
    by_round: dict[int, list[float]] = {}
    for r in rows:
        by_round.setdefault(r["round"], []).append(r["pts"])
    baseline = {rd: statistics.median(v) for rd, v in by_round.items() if v}

    per: dict[tuple[str, int], list[float]] = {}
    for r in rows:
        owner = owners.get((r["season"], r["team_id"]), r["team_id"])
        per.setdefault((owner, r["round"]), []).append(r["pts"] - baseline[r["round"]])

    out = []
    for (owner, rd), deltas in sorted(per.items()):
        out.append([owner, rd, len(deltas), round(statistics.mean(deltas), 1)])
    out.sort(key=lambda x: (x[0], x[1]))

    worst = min(out, key=lambda x: x[3]) if out else None
    headline = (
        f"{worst[0]} loses the most value in round {worst[1]}: "
        f"{worst[3]:+.1f} points versus the league median for that round."
        if worst else ""
    )
    return Result(
        "draft_roi", "Draft ROI by round", headline,
        ["Owner", "Round", "Picks", "Pts vs round median"], out,
        caveat="Points are credited to the drafting team for the whole season "
               "even if the player was later traded or dropped. Round-level "
               "medians are thin in leagues with few seasons of history.",
    )


# ──────────────────── 2. positional allocation versus finish ─────────────────

def allocation_vs_finish(store: Store, provider: str, league: str,
                         early_picks: int = 5) -> Result:
    """Position mix of the first N picks, joined to final standing.

    The single highest-signal question in the dataset: does going RB-heavy
    early actually win in this league, or is that just folklore?
    """
    picks = store.q(
        f"""
        SELECT d.season, d.team_id, p.pos
        FROM draft_pick d
        JOIN player p ON p.provider=d.provider AND p.player_id=d.player_id
        WHERE d.provider=? AND d.league_id=? AND d.round<=?
        """,
        (provider, league, early_picks),
    )
    finish = {
        (r["season"], r["team_id"]): r["rank"]
        for r in store.q(f"SELECT season, team_id, rank FROM standing WHERE {SCOPE}",
                         (provider, league))
    }
    if not picks or not finish:
        return Result("allocation", "Positional allocation versus finish",
                      caveat="Needs draft results, player positions, and final standings.")

    mix: dict[tuple[int, str], dict[str, int]] = {}
    for r in picks:
        mix.setdefault((r["season"], r["team_id"]), {}).setdefault(r["pos"] or "?", 0)
        mix[(r["season"], r["team_id"])][r["pos"] or "?"] += 1

    buckets: dict[str, list[int]] = {}
    rows = []
    for key, counts in sorted(mix.items()):
        rank = finish.get(key)
        if not rank:
            continue
        shape = "/".join(f"{n}{p}" for p, n in sorted(counts.items(), key=lambda x: -x[1]))
        rb = counts.get("RB", 0)
        label = "RB heavy" if rb >= 3 else "RB light" if rb <= 1 else "balanced"
        buckets.setdefault(label, []).append(rank)
        rows.append([key[0], key[1], shape, label, rank])

    summary = sorted(
        ([k, len(v), round(statistics.mean(v), 2)] for k, v in buckets.items()),
        key=lambda x: x[2],
    )
    best = summary[0] if summary else None
    headline = (
        f"{best[0]} starts finish {best[2]} on average across {best[1]} team-seasons, "
        f"the best of the three shapes in this league."
        if best else ""
    )
    return Result(
        "allocation", "Positional allocation versus finish", headline,
        ["Shape", "Team-seasons", "Mean finish"], summary,
        caveat="Correlational and small-sample. Three seasons of a 10-team "
               "league is 30 data points split across three buckets, which is "
               "suggestive at best. Do not treat this as causal.",
        note=f"Based on the first {early_picks} rounds of each draft.",
    )


# ───────────────────────────── 3. reach tendency ─────────────────────────────

def reach_tendency(store: Store, provider: str, league: str) -> Result:
    """Pick number minus market ADP, by round, per owner.

    Positive means you reached. Most managers reach 4 to 8 spots in the
    middle rounds and have no idea. It is the cheapest leak to fix.
    """
    rows = store.q(
        f"""
        SELECT d.season, d.round, d.team_id, d.overall, a.rank
        FROM draft_pick d
        JOIN adp a ON a.season=d.season AND a.provider=d.provider
                  AND a.player_id=d.player_id
        WHERE d.provider=? AND d.league_id=?
        """,
        (provider, league),
    )
    if not rows:
        return Result("reach", "Reach tendency",
                      caveat="Needs ADP loaded. Run `adp-load` with a CSV of "
                             "player_id,rank for each season, or skip this one.")

    owners = _owner_map(store, provider, league)
    per: dict[str, list[float]] = {}
    for r in rows:
        owner = owners.get((r["season"], r["team_id"]), r["team_id"])
        # rank minus overall, so a player taken before the market had him
        # reads positive. The reverse reads as a bargain.
        per.setdefault(owner, []).append(r["rank"] - r["overall"])

    out = sorted(
        ([o, len(v), round(statistics.mean(v), 1), round(statistics.pstdev(v), 1)]
         for o, v in per.items()),
        key=lambda x: -x[2],
    )
    headline = (
        f"{out[0][0]} reaches most, {out[0][2]:+.1f} picks ahead of market on average."
        if out else ""
    )
    return Result(
        "reach", "Reach tendency versus market ADP", headline,
        ["Owner", "Picks matched", "Mean reach", "Std dev"], out,
        caveat="Only counts picks where the player matched an ADP row. "
               "Late-round and undrafted players usually have no ADP, so this "
               "measures early and middle rounds far better than late ones.",
    )


# ──────────────────────── 4. points left on the bench ────────────────────────

def bench_leak(store: Store, provider: str, league: str) -> Result:
    """Optimal lineup versus what was actually started.

    Pure process, no luck. Typically a 10 to 15 percent leak, and it is the
    one number here you can improve without knowing anything about football.
    """
    rows = store.q(
        f"""
        SELECT season, week, team_id, slot, points, started
        FROM roster_slot WHERE {SCOPE} AND week > 0
        """,
        (provider, league),
    )
    if not rows:
        return Result("bench", "Points left on the bench",
                      caveat="Needs weekly roster rows with a started flag and actual points.")

    owners = _owner_map(store, provider, league)
    weeks: dict[tuple[int, int, str], list] = {}
    for r in rows:
        weeks.setdefault((r["season"], r["week"], r["team_id"]), []).append(r)

    per: dict[str, list[tuple[float, float]]] = {}
    for (season, _wk, team), roster in weeks.items():
        started = [r for r in roster if r["started"]]
        if not started:
            continue
        actual = sum(r["points"] or 0 for r in started)
        # Optimal within the same number of slots. A true optimizer would
        # respect slot eligibility; this bounds the leak from below.
        pool = sorted((r["points"] or 0 for r in roster), reverse=True)
        optimal = sum(pool[: len(started)])
        per.setdefault(owners.get((season, team), team), []).append((actual, optimal))

    out = []
    for owner, pairs in per.items():
        act = sum(a for a, _ in pairs)
        opt = sum(o for _, o in pairs)
        if opt <= 0:
            continue
        out.append([owner, len(pairs), round(act, 1), round(opt, 1),
                    round(100 * (opt - act) / opt, 1)])
    out.sort(key=lambda x: -x[4])

    if not out:
        # Distinguish "no data" from "data present but unusable", because the
        # two have completely different fixes.
        starters = sum(1 for r in rows if r["started"])
        why = ("Roster rows exist but none are flagged as started, so there is no "
               "lineup to compare against. That usually means the provider did not "
               "expose lineup slots for these seasons."
               if starters == 0 else "No weeks had both a lineup and scored points.")
        return Result("bench", "Points left on the bench", caveat=why)

    headline = (
        f"{out[0][0]} left {out[0][4]}% of available points on the bench across "
        f"{out[0][1]} team-weeks."
        if out else ""
    )
    return Result(
        "bench", "Points left on the bench", headline,
        ["Owner", "Team-weeks", "Started", "Optimal", "Leak %"], out,
        caveat="Optimal is computed as the top N scorers on the roster, ignoring "
               "slot eligibility. That overstates the achievable optimum slightly, "
               "so treat the leak percentage as an upper bound rather than a target.",
    )


# ───────────────────────────── 5. waiver ROI ─────────────────────────────────

def waiver_roi(store: Store, provider: str, league: str) -> Result:
    """Points from in-season acquisitions versus drafted players.

    Directly tests whether the "hold bench spots for churn" rule pays in
    this specific league, rather than in general.
    """
    drafted = {
        (r["season"], r["player_id"])
        for r in store.q(f"SELECT season, player_id FROM draft_pick WHERE {SCOPE}",
                         (provider, league))
    }
    rows = store.q(
        f"""
        SELECT season, team_id, player_id, SUM(points) AS pts,
               SUM(CASE WHEN started=1 THEN points ELSE 0 END) AS started_pts
        FROM roster_slot WHERE {SCOPE} AND week > 0
        GROUP BY season, team_id, player_id
        """,
        (provider, league),
    )
    if not rows:
        return Result("waiver", "Waiver ROI",
                      caveat="Needs weekly roster rows and draft results.")

    if not any(r["started_pts"] for r in rows):
        return Result("waiver", "Waiver and free-agent ROI",
                      caveat="Roster rows carry no scored points, so added and "
                             "drafted contributions cannot be separated.")

    owners = _owner_map(store, provider, league)
    per: dict[str, dict[str, float]] = {}
    for r in rows:
        owner = owners.get((r["season"], r["team_id"]), r["team_id"])
        bucket = "drafted" if (r["season"], r["player_id"]) in drafted else "added"
        d = per.setdefault(owner, {"drafted": 0.0, "added": 0.0, "n_added": 0})
        d[bucket] += r["started_pts"] or 0
        if bucket == "added":
            d["n_added"] += 1

    out = []
    for owner, d in per.items():
        total = d["drafted"] + d["added"]
        if total <= 0:
            continue
        out.append([owner, int(d["n_added"]), round(d["drafted"], 1),
                    round(d["added"], 1), round(100 * d["added"] / total, 1)])
    out.sort(key=lambda x: -x[4])

    headline = (
        f"{out[0][0]} got {out[0][4]}% of started points from players they did not draft."
        if out else ""
    )
    return Result(
        "waiver", "Waiver and free-agent ROI", headline,
        ["Owner", "Players added", "Drafted pts started", "Added pts started", "Added share %"],
        out,
        caveat="A player drafted by someone else and picked up later counts as "
               "added, which is correct for this question but means the number "
               "includes shrewd waiver claims and lucky handcuffs alike.",
    )


# ────────────────────────── 6. luck decomposition ────────────────────────────

def luck(store: Store, provider: str, league: str) -> Result:
    """All-play record versus actual record.

    All-play asks what your record would be if you played every team every
    week. The gap between that and your real record is schedule luck.
    """
    rows = store.q(
        f"SELECT season, week, team_id, points FROM matchup WHERE {SCOPE} AND week>0",
        (provider, league),
    )
    actual = store.q(
        f"SELECT season, team_id, points, opp_points FROM matchup WHERE {SCOPE} AND week>0",
        (provider, league),
    )
    if not rows:
        return Result("luck", "Luck decomposition",
                      caveat="Needs weekly matchup scores.")

    owners = _owner_map(store, provider, league)
    by_week: dict[tuple[int, int], list] = {}
    for r in rows:
        by_week.setdefault((r["season"], r["week"]), []).append((r["team_id"], r["points"]))

    allplay: dict[str, list[int]] = {}
    for (season, _wk), scores in by_week.items():
        for tid, pts in scores:
            owner = owners.get((season, tid), tid)
            w = sum(1 for o, p in scores if o != tid and pts > p)
            l = sum(1 for o, p in scores if o != tid and pts < p)
            rec = allplay.setdefault(owner, [0, 0])
            rec[0] += w
            rec[1] += l

    real: dict[str, list[int]] = {}
    for r in actual:
        owner = owners.get((r["season"], r["team_id"]), r["team_id"])
        rec = real.setdefault(owner, [0, 0])
        if r["points"] > r["opp_points"]:
            rec[0] += 1
        elif r["points"] < r["opp_points"]:
            rec[1] += 1

    out = []
    for owner, (aw, al) in allplay.items():
        rw, rl = real.get(owner, [0, 0])
        ap = aw / (aw + al) if (aw + al) else 0
        rp = rw / (rw + rl) if (rw + rl) else 0
        out.append([owner, f"{rw}-{rl}", round(rp, 3), round(ap, 3),
                    round((rp - ap) * 100, 1)])
    out.sort(key=lambda x: -x[4])

    headline = (
        f"{out[0][0]} ran {out[0][4]:+.1f} points of win rate above their all-play "
        f"record. {out[-1][0]} ran {out[-1][4]:+.1f}."
        if len(out) > 1 else ""
    )
    return Result(
        "luck", "Schedule luck", headline,
        ["Owner", "Real record", "Real win %", "All-play win %", "Luck (pts of win %)"],
        out,
        caveat="All-play is the standard luck proxy but it is not perfect. It "
               "treats every week equally and ignores that a manager may play "
               "differently when facing a strong opponent.",
    )


# ───────────────────── 7. regular season versus playoff weeks ────────────────

def phase_split(store: Store, provider: str, league: str,
                playoff_start: int = 15) -> Result:
    """Scoring in weeks 1-14 versus 15-17, per owner.

    Validates whether the playoff-schedule weighting in the draft model
    deserves the weight it is given, using this league's own history.
    """
    rows = store.q(
        f"SELECT season, week, team_id, points FROM matchup WHERE {SCOPE} AND week>0",
        (provider, league),
    )
    if not rows:
        return Result("phase", "Regular season versus championship weeks",
                      caveat="Needs weekly matchup scores.")

    owners = _owner_map(store, provider, league)
    per: dict[str, dict[str, list[float]]] = {}
    for r in rows:
        owner = owners.get((r["season"], r["team_id"]), r["team_id"])
        phase = "post" if r["week"] >= playoff_start else "reg"
        per.setdefault(owner, {"reg": [], "post": []})[phase].append(r["points"])

    out = []
    for owner, d in per.items():
        if not d["reg"] or not d["post"]:
            continue
        reg, post = statistics.mean(d["reg"]), statistics.mean(d["post"])
        out.append([owner, len(d["reg"]), round(reg, 1), len(d["post"]),
                    round(post, 1), round(post - reg, 1)])
    out.sort(key=lambda x: -x[5])

    headline = (
        f"{out[0][0]} scores {out[0][5]:+.1f} points per week more in weeks "
        f"{playoff_start}+ than in the regular season."
        if out else ""
    )
    return Result(
        "phase", "Regular season versus championship weeks", headline,
        ["Owner", "Reg weeks", "Reg avg", "Post weeks", "Post avg", "Delta"], out,
        caveat="Championship-week samples are tiny, often three games a season. "
               "Two or three seasons of history is not enough to separate skill "
               "from noise here. Read it as a prompt to investigate, not a finding.",
        note=f"Playoff weeks defined as {playoff_start} and later.",
    )


# ─────────────────────────── 8. manager profiles ─────────────────────────────

def manager_profile(store: Store, provider: str, league: str) -> Result:
    """Draft tendencies per owner: when they take QB, TE, K and DEF.

    The most directly exploitable output. If one manager always takes a
    quarterback in round 4, you can let the good ones slide past you.
    """
    rows = store.q(
        f"""
        SELECT d.season, d.team_id, d.round, p.pos
        FROM draft_pick d
        JOIN player p ON p.provider=d.provider AND p.player_id=d.player_id
        WHERE d.provider=? AND d.league_id=?
        """,
        (provider, league),
    )
    if not rows:
        return Result("profile", "Manager draft tendencies",
                      caveat="Needs draft results joined to player positions.")

    owners = _owner_map(store, provider, league)
    first: dict[str, dict[str, list[int]]] = {}
    seen: set = set()
    for r in sorted(rows, key=lambda x: x["round"]):
        owner = owners.get((r["season"], r["team_id"]), r["team_id"])
        pos = r["pos"] or "?"
        key = (owner, r["season"], pos)
        if key in seen:
            continue
        seen.add(key)
        first.setdefault(owner, {}).setdefault(pos, []).append(r["round"])

    out = []
    for owner, by_pos in sorted(first.items()):
        row = [owner]
        for pos in ("QB", "RB", "WR", "TE", "K", "DEF"):
            v = by_pos.get(pos)
            row.append(round(statistics.mean(v), 1) if v else None)
        out.append(row)

    qbs = [(r[0], r[1]) for r in out if r[1] is not None]
    headline = ""
    if len(qbs) > 1:
        early = min(qbs, key=lambda x: x[1])
        late = max(qbs, key=lambda x: x[1])
        headline = (
            f"{early[0]} takes a QB by round {early[1]} on average; "
            f"{late[0]} waits until {late[1]}."
        )
    return Result(
        "profile", "Manager draft tendencies", headline,
        ["Owner", "First QB", "First RB", "First WR", "First TE", "First K", "First DEF"],
        out,
        caveat="Averages over few seasons. One weird draft moves an owner's "
               "number a full round, so check the season count before acting on it.",
    )


# ──────────────────────── 9. storylines and sentiment ────────────────────────

# Quadrant labels. Mean reach says how far ahead of the market a manager
# drafted; the spread says whether they did it consistently or in bursts.
_READS = {
    (False, False): ("Patient",   "stayed near the market and rarely lurched"),
    (False, True):  ("Streaky",   "mostly patient, with a few big swings"),
    (True,  False): ("Assertive", "consistently ahead of the market, not wildly"),
    (True,  True):  ("Gunslinger", "ahead of the market and swinging hard"),
}


def draft_storylines(store: Store, provider: str, league: str) -> Result:
    """A read on each manager's most recent draft, plus what actually happened.

    Everything here is derived, never asserted: the label comes from where a
    manager sits against the league median on two axes, and the sentence
    quotes their own most extreme pick back at them.
    """
    rows = store.q(
        f"""
        SELECT d.season, d.overall, d.round, d.team_id,
               p.name AS name, p.pos AS pos, a.rank AS rank
        FROM draft_pick d
        LEFT JOIN player p
               ON p.provider=d.provider AND p.player_id=d.player_id
        LEFT JOIN adp a
               ON a.season=d.season AND a.provider=d.provider
              AND a.player_id=d.player_id
        WHERE d.provider=? AND d.league_id=?
        ORDER BY d.season, d.overall
        """,
        (provider, league),
    )
    caveat = (
        "One draft, fourteen picks a manager. The label describes how somebody "
        "drafted against consensus on this one night, not how good they are - a "
        "contrarian who is right reads exactly like a reach here. Needs ADP "
        "loaded for the season, or there is nothing to compare a pick against. "
        "Kickers and defences are excluded outright: their ADP is a placeholder, "
        "so including them would make every manager look wild."
    )
    if not rows:
        return Result("storylines", "Draft storylines", caveat=caveat)

    season = max(r["season"] for r in rows)
    # K and DEF carry a placeholder ADP, so they post enormous fake reaches and
    # would win every storyline. Skill positions only.
    skill = {"QB", "RB", "WR", "TE"}
    picks = [r for r in rows
             if r["season"] == season and r["rank"] is not None and r["pos"] in skill]
    if not picks:
        return Result("storylines", "Draft storylines", caveat=caveat)

    owners = _owner_map(store, provider, league)
    name_of = lambda tid: owners.get((season, tid), tid)

    per: dict[str, list[dict]] = {}
    for r in picks:
        per.setdefault(r["team_id"], []).append({
            "overall": r["overall"], "round": r["round"],
            "player": r["name"] or "an unnamed player",
            "pos": r["pos"] or "?", "reach": r["rank"] - r["overall"],
        })

    means = {t: statistics.mean(p["reach"] for p in ps) for t, ps in per.items()}
    sds = {t: statistics.pstdev([p["reach"] for p in ps]) if len(ps) > 1 else 0.0
           for t, ps in per.items()}
    mid_mean = statistics.median(means.values())
    mid_sd = statistics.median(sds.values())

    out = []
    for tid, ps in per.items():
        label, gloss = _READS[(means[tid] > mid_mean, sds[tid] > mid_sd)]
        best = min(ps, key=lambda p: p["reach"])
        worst = max(ps, key=lambda p: p["reach"])
        counts = Counter(p["pos"] for p in ps)
        skew = counts.most_common(1)[0]

        if abs(worst["reach"]) >= abs(best["reach"]):
            story = (f"Took {worst['player']} in round {worst['round']}, "
                     f"{worst['reach']:.0f} picks before the market had him")
        else:
            story = (f"Let {best['player']} fall to round {best['round']} and took him "
                     f"{abs(best['reach']):.0f} picks after his ADP")
        story += f". Left the room with {skew[1]} {skew[0]}s - {gloss}."
        out.append([name_of(tid), label, round(means[tid], 1), story])

    out.sort(key=lambda x: x[2])

    # The loudest single moment in the room, and the longest positional run.
    top = max(picks, key=lambda p: abs(p["rank"] - p["overall"]))
    diff = top["rank"] - top["overall"]
    verb = "reached" if diff > 0 else "got a bargain on"
    headline = (f"{name_of(top['team_id'])} {verb} {top['name'] or 'a player'} by "
                f"{abs(diff):.0f} picks, the widest gap from ADP in the draft.")

    run_pos, run_len, best_run, best_pos, best_at = None, 0, 0, None, 0
    for p in sorted(picks, key=lambda p: p["overall"]):
        if p["pos"] == run_pos:
            run_len += 1
        else:
            run_pos, run_len = p["pos"], 1
        if run_len > best_run and run_pos:
            best_run, best_pos, best_at = run_len, run_pos, p["overall"] - run_len + 1
    note = (f"Longest positional run: {best_run} straight {best_pos}s from pick "
            f"{best_at}." if best_run >= 3 else "")

    return Result(
        "storylines", f"Draft storylines, {season}", headline,
        ["Manager", "Read", "Mean reach", "What happened"], out,
        caveat=caveat, note=note,
    )


def manager_dossier(store: Store, provider: str, league: str,
                    also: tuple[str, ...] = ()) -> dict:
    """Everything known about each manager, keyed by owner.

    `also` takes extra league ids whose history belongs to the same people -
    a league recreated for a new season gets a fresh id on ESPN, and without
    this the managers look like they have never played before.

    Not a `Result`: this feeds prose rather than a table, so it stays out of
    ANALYSES. It reads the same rows the analyses do, which is what keeps a
    written verdict and a printed number from disagreeing.
    """
    ids = [str(league), *[str(x) for x in also]]
    marks = ",".join("?" * len(ids))
    scope = f"provider=? AND league_id IN ({marks})"
    args = (provider, *ids)

    # Owner is the identity; the newest team name they used is the label.
    owner_of, label_of, newest = {}, {}, {}
    for r in store.q(f"SELECT league_id, season, team_id, name, owner FROM manager "
                     f"WHERE {scope}", args):
        key = r["owner"] or r["name"] or r["team_id"]
        owner_of[(r["league_id"], r["season"], r["team_id"])] = key
        if r["name"] and (key not in newest or r["season"] >= newest[key]):
            newest[key], label_of[key] = r["season"], r["name"]
    who = lambda lg, sn, tid: label_of.get(
        owner_of.get((lg, sn, tid), tid), str(tid))

    latest = max((r["season"] for r in store.q(
        f"SELECT DISTINCT season FROM league WHERE {scope}", args)), default=0)
    dossier: dict[str, dict] = {}

    def slot(label):
        return dossier.setdefault(label, {
            "name": label, "seasons": 0, "w": 0, "l": 0, "t": 0, "pf": 0.0,
            "ap_w": 0, "ap_n": 0, "early": 0.0, "late": 0.0,
            "roster": [], "first": {}, "_reach": [], "_picks": [],
        })

    for r in store.q(f"SELECT league_id, season, team_id, points_for "
                     f"FROM standing WHERE {scope}", args):
        d = slot(who(r["league_id"], r["season"], r["team_id"]))
        d["seasons"] += 1
        d["pf"] += r["points_for"] or 0.0

    weekly: dict = {}
    for r in store.q(f"SELECT league_id, season, week, team_id, points "
                     f"FROM matchup WHERE {scope}", args):
        weekly.setdefault((r["league_id"], r["season"], r["week"]), {})[r["team_id"]] = r["points"]
    for (lg, sn, _wk), rows in weekly.items():
        # A scheduled-but-unplayed week is all zeros. Counting it hands every
        # manager a pile of all-play losses and drags the whole league to .500.
        if not any((p or 0) > 0 for p in rows.values()):
            continue
        for tid, pts in rows.items():
            d = slot(who(lg, sn, tid))
            d["ap_w"] += sum(1 for o, p in rows.items() if o != tid and pts > p)
            d["ap_n"] += len(rows) - 1
    for r in store.q(f"SELECT league_id, season, week, team_id, points, opp_points "
                     f"FROM matchup WHERE {scope}", args):
        if (r["points"] or 0) <= 0 and (r["opp_points"] or 0) <= 0:
            continue
        d = slot(who(r["league_id"], r["season"], r["team_id"]))
        if r["points"] > r["opp_points"]: d["w"] += 1
        elif r["points"] < r["opp_points"]: d["l"] += 1
        else: d["t"] += 1

    for lid in ids:
        for owner, rnd, _n, val in draft_roi_by_round(store, provider, lid).rows:
            slot(owner)["early" if rnd <= 5 else "late"] += val

    for r in store.q(
        f"""SELECT d.league_id, d.season, d.overall, d.round, d.team_id,
                   p.name AS nm, p.pos AS pos, a.rank AS adp
            FROM draft_pick d
            LEFT JOIN player p ON p.provider=d.provider AND p.player_id=d.player_id
            LEFT JOIN adp a ON a.season=d.season AND a.provider=d.provider
                           AND a.player_id=d.player_id
            WHERE d.{scope.replace('provider=?','provider=?')} ORDER BY d.overall"""
        .replace("d.provider=? AND league_id", "d.provider=? AND d.league_id"), args):
        d = slot(who(r["league_id"], r["season"], r["team_id"]))
        pick = {"season": r["season"], "overall": r["overall"], "round": r["round"],
                "nm": r["nm"] or "?", "pos": r["pos"] or "?"}
        if r["adp"] is not None and r["pos"] not in ("K", "DEF"):
            pick["reach"] = round(r["adp"] - r["overall"], 1)
            d["_reach"].append(pick["reach"])
        if r["season"] == latest and str(r["league_id"]) == str(league):
            d["roster"].append(pick)
        d["_picks"].append(pick)
        cur = d["first"].get(pick["pos"])
        if cur is None or pick["round"] < cur:
            d["first"][pick["pos"]] = pick["round"]

    for d in dossier.values():
        g = max(d["w"] + d["l"] + d["t"], 1)
        d["record"] = f"{d['w']}-{d['l']}" + (f"-{d['t']}" if d["t"] else "")
        d["win"] = round(d["w"] / g, 3)
        d["allplay"] = round(d["ap_w"] / max(d["ap_n"], 1), 3)
        d["luck"] = round((d["win"] - d["allplay"]) * 100, 1)
        d["early"] = round(d["early"]); d["late"] = round(d["late"])
        d["meanReach"] = round(statistics.mean(d["_reach"]), 1) if d["_reach"] else None
        withadp = [p for p in d["_picks"] if "reach" in p]
        d["bestValue"] = min(withadp, key=lambda p: p["reach"]) if withadp else None
        d["worstReach"] = max(withadp, key=lambda p: p["reach"]) if withadp else None
        d["roster"].sort(key=lambda p: p["overall"])
        d["active"] = bool(d["roster"])
        for k in ("ap_w", "ap_n", "_reach", "_picks"):
            d.pop(k, None)
    return dossier


ANALYSES: dict[str, Callable[..., Result]] = {
    "draft_roi": draft_roi_by_round,
    "allocation": allocation_vs_finish,
    "reach": reach_tendency,
    "bench": bench_leak,
    "waiver": waiver_roi,
    "luck": luck,
    "phase": phase_split,
    "profile": manager_profile,
    "storylines": draft_storylines,
}


def run_all(store: Store, provider: str, league: str) -> list[Result]:
    return [fn(store, provider, league) for fn in ANALYSES.values()]
