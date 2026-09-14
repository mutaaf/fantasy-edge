"""SQLite schema for college football history from CollegeFootballData.

Schema only for now: the CFBD client and its season-by-season pulls land
when a CFBD_API_KEY is configured (`doctor` says so). Every table keys on
(source, id) because ESPN and CFBD mint their own ids and they collide as
strings; joining the two goes through `team_alias`, never through equality
of ids.
"""
from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS team (
  source TEXT NOT NULL, id TEXT NOT NULL,
  school TEXT NOT NULL, mascot TEXT, abbr TEXT, conference TEXT, division TEXT,
  color TEXT, alt_color TEXT, logo TEXT, venue_id TEXT,
  PRIMARY KEY (source, id)
);

CREATE TABLE IF NOT EXISTS team_alias (
  source TEXT NOT NULL, id TEXT NOT NULL,
  other_source TEXT NOT NULL, other_id TEXT NOT NULL,
  PRIMARY KEY (source, id, other_source)
);

CREATE TABLE IF NOT EXISTS game (
  source TEXT NOT NULL, id TEXT NOT NULL,
  season INTEGER NOT NULL, week INTEGER, season_type TEXT, start TEXT,
  neutral INTEGER, conference_game INTEGER, venue_id TEXT, attendance INTEGER,
  home_id TEXT NOT NULL, home_points INTEGER, away_id TEXT NOT NULL, away_points INTEGER,
  completed INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (source, id)
);
CREATE INDEX IF NOT EXISTS game_season ON game (source, season, week);

CREATE TABLE IF NOT EXISTS line (
  source TEXT NOT NULL, game_id TEXT NOT NULL, provider TEXT NOT NULL,
  spread REAL, over_under REAL, home_moneyline INTEGER, away_moneyline INTEGER,
  PRIMARY KEY (source, game_id, provider)
);

CREATE TABLE IF NOT EXISTS coach (
  source TEXT NOT NULL, id TEXT NOT NULL, season INTEGER NOT NULL,
  first_name TEXT, last_name TEXT, team_id TEXT NOT NULL,
  wins INTEGER, losses INTEGER, ties INTEGER,
  PRIMARY KEY (source, id, season, team_id)
);

CREATE TABLE IF NOT EXISTS recruit (
  source TEXT NOT NULL, id TEXT NOT NULL, year INTEGER NOT NULL,
  name TEXT NOT NULL, position TEXT, stars INTEGER, rating REAL, ranking INTEGER,
  hometown TEXT, state TEXT, lat REAL, lon REAL, committed_to TEXT,
  PRIMARY KEY (source, id)
);

CREATE TABLE IF NOT EXISTS portal_move (
  source TEXT NOT NULL, id TEXT NOT NULL, season INTEGER NOT NULL,
  name TEXT NOT NULL, position TEXT, origin_id TEXT, destination_id TEXT,
  transfer_date TEXT, stars INTEGER, rating REAL, eligibility TEXT,
  PRIMARY KEY (source, id)
);

-- Every CFBD call is counted, so a pull can refuse to spend a month's
-- budget (1,000 on the free tier) in one run.
CREATE TABLE IF NOT EXISTS call_budget (
  month TEXT PRIMARY KEY, calls INTEGER NOT NULL DEFAULT 0, limit_calls INTEGER NOT NULL
);
"""


def connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.execute("INSERT OR REPLACE INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
    con.commit()
    return con
