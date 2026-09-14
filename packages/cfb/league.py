"""College football as a league: where its data lives and the rules that differ.

Everything here is about the sport, not about any one client. The NFL
equivalent lives in fantasy-edge; the two meet in a shared rules table.

# INTEGRATE: shared league rules table from fantasy-edge scene/replay branch
# (`fantasyedge/scene.py` keys rules by league; `college-football` is stubbed
# there). When it lands, RULES below becomes that table's college entry and
# this module keeps only the ESPN host details.
"""
from __future__ import annotations

import os

LEAGUE = "college-football"
SPORT = "football"

HOST = os.environ.get("ESPN_API_HOST", "site.web.api.espn.com")
BASE = f"https://{HOST}/apis/site/v2/sports/{SPORT}/{LEAGUE}"

# groups=80 is FBS. Without it ESPN serves a curated subset of the slate, with
# no error - a Saturday of 86 games quietly becomes a couple of dozen.
FBS_GROUP = "80"
SCOREBOARD = BASE + "/scoreboard?groups=" + FBS_GROUP + "&limit=300"
SUMMARY = BASE + "/summary?event={event}"

LOGO = "https://a.espncdn.com/i/teamlogos/ncaa/500/{id}.png"

RULES = {
    "periods": 4,
    "period_seconds": 900,
    # Overtime: each side gets a possession from the opponent's 25; from the
    # third overtime on, each possession is a single two-point attempt.
    "ot_start_yards_to_goal": 25,
    "ot_two_point_only_from": 3,
    # Hash marks sit 60 ft from each sideline (20 yd), far wider apart than
    # the NFL's; a field renderer that shares NFL geometry puts every
    # college ball in the wrong lane.
    "hash_from_sideline_yd": 20.0,
    "field_width_yd": 53.33,
    "red_zone_yards_to_goal": 20,
}


def scoreboard_url(dates: str | None = None) -> str:
    return SCOREBOARD + (f"&dates={dates}" if dates else "")


def summary_url(event: str) -> str:
    return SUMMARY.format(event=event)
