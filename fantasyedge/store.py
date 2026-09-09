"""Storage: SQLite, one file, no server.

SQLite because the whole dataset is a few megabytes and the analytics are
naturally relational. Postgres would be operational overhead with no
payoff at this size.

Every write is idempotent. Re-pulling a season overwrites it cleanly, so
`pull` is safe to run on a cron without accumulating duplicates.
"""

from __future__ import annotations

import pathlib
import sqlite3
from contextlib import contextmanager

from .models import SeasonBundle

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS league (
  provider TEXT, league_id TEXT, season INTEGER,
  name TEXT, team_count INTEGER, scoring TEXT,
  PRIMARY KEY (provider, league_id, season)
);

CREATE TABLE IF NOT EXISTS manager (
  provider TEXT, league_id TEXT, season INTEGER,
  team_id TEXT, name TEXT, owner TEXT,
  PRIMARY KEY (provider, league_id, season, team_id)
);

CREATE TABLE IF NOT EXISTS player (
  provider TEXT, player_id TEXT, name TEXT, pos TEXT, nfl_team TEXT,
  PRIMARY KEY (provider, player_id)
);

CREATE TABLE IF NOT EXISTS draft_pick (
  provider TEXT, league_id TEXT, season INTEGER,
  overall INTEGER, round INTEGER, team_id TEXT, player_id TEXT, cost REAL,
  PRIMARY KEY (provider, league_id, season, overall)
);

CREATE TABLE IF NOT EXISTS roster_slot (
  provider TEXT, league_id TEXT, season INTEGER,
  week INTEGER, team_id TEXT, player_id TEXT, slot TEXT,
  points REAL, projected REAL, started INTEGER,
  PRIMARY KEY (provider, league_id, season, week, team_id, player_id)
);

CREATE TABLE IF NOT EXISTS matchup (
  provider TEXT, league_id TEXT, season INTEGER,
  week INTEGER, team_id TEXT, opponent_id TEXT, points REAL, opp_points REAL,
  PRIMARY KEY (provider, league_id, season, week, team_id)
);

CREATE TABLE IF NOT EXISTS txn (
  provider TEXT, league_id TEXT, season INTEGER,
  week INTEGER, team_id TEXT, player_id TEXT, kind TEXT, source TEXT
);

CREATE TABLE IF NOT EXISTS standing (
  provider TEXT, league_id TEXT, season INTEGER,
  team_id TEXT, rank INTEGER, wins INTEGER, losses INTEGER, ties INTEGER,
  points_for REAL, points_against REAL,
  PRIMARY KEY (provider, league_id, season, team_id)
);

CREATE TABLE IF NOT EXISTS adp (
  season INTEGER, provider TEXT, player_id TEXT, source TEXT, rank REAL,
  PRIMARY KEY (season, provider, player_id, source)
);

CREATE TABLE IF NOT EXISTS projection (
  season INTEGER, week INTEGER, source TEXT, provider TEXT, player_id TEXT,
  points REAL,
  PRIMARY KEY (season, week, source, provider, player_id)
);

CREATE INDEX IF NOT EXISTS ix_proj_src ON projection(source, season, week);
CREATE INDEX IF NOT EXISTS ix_roster_week ON roster_slot(provider, league_id, season, week);
CREATE INDEX IF NOT EXISTS ix_draft_team  ON draft_pick(provider, league_id, season, team_id);
CREATE INDEX IF NOT EXISTS ix_txn_team    ON txn(provider, league_id, season, team_id);
"""


class Store:
    def __init__(self, path: str | pathlib.Path = "data/fantasy.db"):
        self.path = pathlib.Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self.conn.execute(
            "INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version',?)",
            (str(SCHEMA_VERSION),),
        )
        self.conn.commit()

    @contextmanager
    def tx(self):
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def close(self) -> None:
        self.conn.close()

    # ---------- writes ----------

    def save(self, b: SeasonBundle) -> dict:
        """Replace one league-season atomically. Safe to re-run.

        Returns per-table counts of rows offered versus rows landed. A gap
        means primary-key collisions swallowed data, which is a real signal:
        it usually indicates a provider emitting the same player twice in one
        team-week. Silently losing rows here would poison every analysis
        downstream, so the caller gets told.
        """
        k = (b.provider, b.league_id, b.season)
        with self.tx() as c:
            for table in ("league", "manager", "draft_pick", "roster_slot",
                          "matchup", "txn", "standing"):
                c.execute(
                    f"DELETE FROM {table} WHERE provider=? AND league_id=? AND season=?", k
                )

            c.execute(
                "INSERT INTO league VALUES (?,?,?,?,?,?)",
                (*k, b.league_name, b.team_count, b.scoring),
            )
            c.executemany(
                "INSERT INTO manager VALUES (?,?,?,?,?,?)",
                [(*k, m.team_id, m.name, m.owner) for m in b.managers],
            )
            c.executemany(
                "INSERT OR REPLACE INTO player VALUES (?,?,?,?,?)",
                [(b.provider, p.player_id, p.name, p.pos, p.nfl_team) for p in b.players],
            )
            c.executemany(
                "INSERT INTO draft_pick VALUES (?,?,?,?,?,?,?,?)",
                [(*k, d.overall, d.round, d.team_id, d.player_id, d.cost) for d in b.draft],
            )
            c.executemany(
                "INSERT OR REPLACE INTO roster_slot VALUES (?,?,?,?,?,?,?,?,?,?)",
                [(*k, r.week, r.team_id, r.player_id, r.slot, r.points,
                  r.projected, int(r.started)) for r in b.rosters],
            )
            c.executemany(
                "INSERT OR REPLACE INTO matchup VALUES (?,?,?,?,?,?,?,?)",
                [(*k, m.week, m.team_id, m.opponent_id, m.points, m.opp_points)
                 for m in b.matchups],
            )
            c.executemany(
                "INSERT INTO txn VALUES (?,?,?,?,?,?,?,?)",
                [(*k, t.week, t.team_id, t.player_id, t.kind, t.source)
                 for t in b.transactions],
            )
            c.executemany(
                "INSERT INTO standing VALUES (?,?,?,?,?,?,?,?,?,?)",
                [(*k, s.team_id, s.rank, s.wins, s.losses, s.ties,
                  s.points_for, s.points_against) for s in b.standings],
            )
            c.executemany(
                "INSERT OR REPLACE INTO adp VALUES (?,?,?,?,?)",
                [(b.season, b.provider, a.player_id, a.source, a.rank) for a in b.adp],
            )

        offered = {"draft_pick": len(b.draft), "roster_slot": len(b.rosters),
                   "matchup": len(b.matchups), "standing": len(b.standings)}
        landed = {
            t: self.q(
                f"SELECT COUNT(*) c FROM {t} WHERE provider=? AND league_id=? AND season=?", k
            )[0]["c"]
            for t in offered
        }
        for t, n in offered.items():
            if n and landed[t] < n:
                print(f"  warn: {t} {n} offered, {landed[t]} stored "
                      f"({n - landed[t]} lost to duplicate keys)")
        return {"offered": offered, "landed": landed}

    # ---------- reads ----------

    def q(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        return self.conn.execute(sql, params).fetchall()

    def seasons(self) -> list[sqlite3.Row]:
        return self.q(
            "SELECT provider, league_id, season, name, team_count "
            "FROM league ORDER BY season DESC"
        )

    def is_empty(self) -> bool:
        return not self.q("SELECT 1 FROM league LIMIT 1")
