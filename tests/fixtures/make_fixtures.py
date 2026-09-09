"""Regenerate test fixtures deterministically.

    python3 tests/fixtures/make_fixtures.py

Synthesises one ESPN-shaped league-season with properties the tests assert
against: 10 teams, a 15-round snake draft of distinct players, 17 weeks of
boxscores, and a deliberately seeded bench leak on teams 5 through 10 so
`bench_leak` has something real to find.

Names are word-only on purpose. The manual parser refuses digits inside a
player name, which is what stops it mistaking a pick number for a name, so
the fixture must respect that constraint too.
"""

import json
import pathlib
import random

random.seed(11)

REAL = [
    "Jahmyr Gibbs", "Bijan Robinson", "Ja'Marr Chase", "Puka Nacua", "CeeDee Lamb",
    "Josh Allen", "Lamar Jackson", "Trey McBride", "Brock Bowers", "Derrick Henry",
    "Breece Hall", "Nico Collins", "Malik Nabers", "Chase Brown", "Kyren Williams",
    "Zay Flowers", "Tee Higgins", "Josh Jacobs", "Sam LaPorta", "George Kittle",
    "Justin Jefferson", "Saquon Barkley", "Jonathan Taylor", "De'Von Achane", "Drake London",
]
FIRST = ["Alder", "Brock", "Cade", "Dane", "Emmet", "Ford", "Gray", "Hollis", "Ives",
         "Jarrett", "Keon", "Lonnie", "Mercer", "Nolan", "Orrin", "Pike", "Quill",
         "Rhett", "Stellan", "Tobias", "Ulric", "Vance", "Wyatt", "Xavier", "Yardley"]
LAST = ["Ashworth", "Bramble", "Calloway", "Dunmore", "Ellery", "Fenwick", "Garvey",
        "Holloway", "Ipswich", "Jessup", "Kingsley", "Larkin", "Marsden", "Norwood"]

POSID = {"QB": 1, "RB": 2, "WR": 3, "TE": 4, "K": 5, "DEF": 16}
SLOTID = {"QB": 0, "RB": 2, "WR": 4, "TE": 6, "K": 17, "DEF": 16}
TEAMS, ROUNDS, WEEKS = 10, 15, 17
HERE = pathlib.Path(__file__).parent


def build_pool(n=200):
    pool = list(REAL)
    i = 0
    while len(pool) < n:
        name = f"{FIRST[i % len(FIRST)]} {LAST[(i // len(FIRST)) % len(LAST)]}"
        if name not in pool:
            pool.append(name)
        i += 1
    return pool[:n]


def pos_of(i):
    if i % 15 == 0:
        return "QB"
    if i % 15 == 7:
        return "TE"
    if i % 15 == 14:
        return "K"
    return "RB" if i % 3 == 0 else "WR"


def main():
    pool = build_pool()
    teams = [{
        "id": t + 1, "name": f"Team {t + 1}", "location": "", "nickname": "",
        "owners": [f"owner-{t + 1}"], "playoffSeed": 0,
        "record": {"overall": {"wins": 0, "losses": 0, "ties": 0,
                               "pointsFor": 0.0, "pointsAgainst": 0.0}},
    } for t in range(TEAMS)]

    picks, overall = [], 0
    for rnd in range(1, ROUNDS + 1):
        order = range(1, TEAMS + 1) if rnd % 2 else range(TEAMS, 0, -1)
        for tid in order:
            overall += 1
            picks.append({"overallPickNumber": overall, "roundId": rnd,
                          "teamId": tid, "playerId": 1000 + overall - 1})

    skill = {t + 1: 1.0 + (0.10 if t < 2 else -0.10 if t >= 8 else 0.0) for t in range(TEAMS)}

    def score(pid, tid):
        base = max(2.0, 22.0 - (pid - 1000) * 0.11)
        return round(max(0.0, random.gauss(base * skill[tid], 5.0)), 1)

    schedule = []
    for wk in range(1, WEEKS + 1):
        order = list(range(1, TEAMS + 1))
        random.shuffle(order)
        for a, b in zip(order[::2], order[1::2]):
            sides = {}
            for tid in (a, b):
                roster = [p for p in picks if p["teamId"] == tid]
                entries, total = [], 0.0
                for i, p in enumerate(roster):
                    pid = p["playerId"]
                    idx = pid - 1000
                    val = score(pid, tid)
                    pos = pos_of(idx)
                    started = i < 9
                    if tid >= 5 and i in (2, 3) and wk % 3 == 0:
                        started = False        # the seeded leak
                    slot = SLOTID.get(pos, 20) if started else 20
                    if started:
                        total += val
                    entries.append({
                        "playerId": pid, "lineupSlotId": slot,
                        "playerPoolEntry": {"appliedStatTotal": val, "player": {
                            "fullName": pool[idx], "defaultPositionId": POSID[pos],
                            "proTeamId": 1,
                            "stats": [
                                {"scoringPeriodId": wk, "statSourceId": 0, "appliedTotal": val},
                                {"scoringPeriodId": wk, "statSourceId": 1,
                                 "appliedTotal": round(val * 0.9, 1)},
                            ]}}})
                sides[tid] = {"teamId": tid, "totalPoints": round(total, 1),
                              "rosterForCurrentScoringPeriod": {"entries": entries}}
            schedule.append({"matchupPeriodId": wk, "home": sides[a], "away": sides[b]})

    tot = {t: 0.0 for t in range(1, TEAMS + 1)}
    wl = {t: [0, 0] for t in range(1, TEAMS + 1)}
    for m in schedule:
        h, a = m["home"], m["away"]
        tot[h["teamId"]] += h["totalPoints"]
        tot[a["teamId"]] += a["totalPoints"]
        hi, lo = (h, a) if h["totalPoints"] > a["totalPoints"] else (a, h)
        wl[hi["teamId"]][0] += 1
        wl[lo["teamId"]][1] += 1

    rank = sorted(tot, key=lambda t: (-wl[t][0], -tot[t]))
    for i, t in enumerate(rank):
        teams[t - 1]["playoffSeed"] = i + 1
        teams[t - 1]["record"]["overall"].update(
            wins=wl[t][0], losses=wl[t][1], pointsFor=round(tot[t], 1))

    txns = [{"scoringPeriodId": w, "teamId": random.randint(1, TEAMS), "type": "WAIVER",
             "items": [{"type": 178, "playerId": 1000 + random.randint(150, 199)}]}
            for w in range(2, 15)]

    (HERE / "espn_2025.json").write_text(json.dumps({
        "settings": {"name": "The Fixture League",
                     "scoringSettings": {"scoringType": "H2H_POINTS"}},
        "teams": teams, "draftDetail": {"picks": picks},
        "schedule": schedule, "transactions": txns}))

    (HERE / "draft.txt").write_text("\n".join(
        f'{p["overallPickNumber"]}. ({p["roundId"]}.{((p["overallPickNumber"] - 1) % TEAMS) + 1:02d}) '
        f'{pool[p["playerId"] - 1000]} {pos_of(p["playerId"] - 1000)} DAL - Team {p["teamId"]}'
        for p in picks[:60]))

    (HERE / "sleeper_2025.json").write_text(
        json.dumps(sleeper_fixture(), indent=1))

    (HERE / "standings.txt").write_text("\n".join(
        f'{i + 1}. Team {t} ({wl[t][0]}-{wl[t][1]}) {tot[t]:.2f}'
        for i, t in enumerate(rank)))

    print(f"{len(picks)} picks, {len({p['playerId'] for p in picks})} distinct players, "
          f"{len(schedule)} matchups")


def sleeper_fixture():
    """A Sleeper-shaped league-season: different wire format, same league.

    Small on purpose. It exists to prove the adapter's mapping - roster_id to
    team, starters list to the started flag, adds/drops to transactions - not
    to restate the ESPN fixture.
    """
    # four rounds against three starting slots, so every team has a bench
    teams, weeks, rounds = 4, 3, 4
    pool = [{"pid": str(9000 + i), "name": REAL[i], "pos": pos_of(i)}
            for i in range(teams * rounds)]
    slots = ["QB", "RB", "WR"]

    players = {p["pid"]: {"player_id": p["pid"], "full_name": p["name"],
                          "position": p["pos"], "team": "DET",
                          "search_full_name": p["name"].lower().replace(" ", "")
                                                       .replace("'", "")}
               for p in pool}

    league = {
        "league_id": "L1", "season": "2025", "name": "Sleeper Test League",
        "total_rosters": teams, "previous_league_id": None,
        "roster_positions": slots + ["BN"],
        "scoring_settings": {"rec": 1.0},
        "settings": {"playoff_week_start": weeks + 1},
    }
    rosters, users = [], []
    for t in range(1, teams + 1):
        owned = [p["pid"] for p in pool[(t - 1) * rounds:t * rounds]]
        rosters.append({"roster_id": t, "owner_id": f"u{t}", "players": owned,
                        "settings": {"wins": t, "losses": teams - t, "ties": 0,
                                     "rank": teams - t + 1, "fpts": 100 + t,
                                     "fpts_against": 100}})
        users.append({"user_id": f"u{t}", "display_name": f"user{t}",
                      "metadata": {"team_name": f"Team {t}"}})

    # snake draft, so pick order reverses on even rounds
    picks = []
    for rd in range(1, rounds + 1):
        order = range(1, teams + 1) if rd % 2 else range(teams, 0, -1)
        for slot, tid in enumerate(order, start=1):
            picks.append({"round": rd, "pick_no": (rd - 1) * teams + slot,
                          "roster_id": tid, "draft_slot": slot,
                          "player_id": pool[(tid - 1) * rounds + rd - 1]["pid"]})

    matchups, txns = {}, {}
    for wk in range(1, weeks + 1):
        rows = []
        for t in range(1, teams + 1):
            owned = [p["pid"] for p in pool[(t - 1) * rounds:t * rounds]]
            started = owned[:len(slots)]
            rows.append({"roster_id": t, "matchup_id": (t + 1) // 2,
                         "points": 90.0 + t + wk,
                         "starters": started, "players": owned,
                         "players_points": {pid: 10.0 + i for i, pid in enumerate(owned)}})
        matchups[wk] = rows
        txns[wk] = [{"status": "complete", "type": "waiver",
                     "adds": {pool[0]["pid"]: 1}, "drops": {pool[1]["pid"]: 1}}]

    return {"league": league, "rosters": rosters, "users": users,
            "drafts": [{"draft_id": "D1", "status": "complete"}],
            "picks": picks, "matchups": matchups, "transactions": txns,
            "players": players}


if __name__ == "__main__":
    main()
