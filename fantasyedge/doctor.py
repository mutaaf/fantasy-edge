"""Self-diagnosis.

Written for an agent, not a human. Every check reports a machine-readable
status and, critically, the exact next command to run. An agent should never
have to infer what is wrong from a stack trace; it runs `doctor --json`,
reads `next_command`, and executes it.

Exit codes are part of the contract:
    0  ready
    2  config incomplete
    3  credentials missing or invalid
    4  no data loaded yet
"""

from __future__ import annotations

import os
import pathlib
import sys
from dataclasses import dataclass, asdict

OK, WARN, FAIL = "ok", "warn", "fail"

EXIT_READY, EXIT_ERROR, EXIT_CONFIG, EXIT_AUTH, EXIT_NODATA = 0, 1, 2, 3, 4

CRED_ENV = {
    "espn": ["ESPN_S2", "ESPN_SWID", "ESPN_LEAGUE_ID"],
    "yahoo": ["YAHOO_CLIENT_ID", "YAHOO_CLIENT_SECRET"],
    "manual": [],
}


@dataclass
class Check:
    name: str
    status: str
    detail: str
    fix: str = ""


@dataclass
class Diagnosis:
    ok: bool
    exit_code: int
    checks: list
    next_action: str
    next_command: str

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "exit_code": self.exit_code,
            "checks": [asdict(c) for c in self.checks],
            "next_action": self.next_action,
            "next_command": self.next_command,
        }


def diagnose(db_path: str, config: dict, config_path: pathlib.Path) -> Diagnosis:
    checks: list[Check] = []

    # 1. runtime
    v = sys.version_info
    checks.append(Check(
        "python",
        OK if v >= (3, 11) else FAIL,
        f"{v.major}.{v.minor}.{v.micro}",
        "" if v >= (3, 11) else "Python 3.11+ required for tomllib.",
    ))

    # 2. config
    league_cfg = config.get("league", {}) or {}
    provider = league_cfg.get("provider") or ""
    league_id = str(league_cfg.get("league_id") or "")

    if not config_path.exists():
        checks.append(Check("config", FAIL, f"{config_path} not found",
                            "python3 -m fantasyedge setup --provider espn --league <id>"))
    elif not provider:
        checks.append(Check("config", FAIL, "no provider set",
                            "python3 -m fantasyedge setup --provider espn --league <id>"))
    elif not league_id and provider != "manual":
        checks.append(Check("config", WARN, f"provider={provider}, league_id empty",
                            f"python3 -m fantasyedge discover --provider {provider}"))
    else:
        checks.append(Check("config", OK, f"provider={provider} league={league_id or 'n/a'}"))

    # 3. credentials
    missing = [k for k in CRED_ENV.get(provider, []) if not os.environ.get(k)]
    if provider == "yahoo":
        token = pathlib.Path.home() / ".fantasy-edge" / "yahoo.json"
        if token.exists():
            checks.append(Check("credentials", OK, "yahoo refresh token present"))
        elif missing:
            checks.append(Check("credentials", FAIL, f"missing env: {', '.join(missing)}",
                                "export YAHOO_CLIENT_ID=... YAHOO_CLIENT_SECRET=..."))
        else:
            checks.append(Check("credentials", FAIL, "client id set but not authorized yet",
                                "python3 -m fantasyedge auth --provider yahoo --url"))
    elif provider == "espn":
        if missing:
            checks.append(Check("credentials", FAIL, f"missing env: {', '.join(missing)}",
                                "export ESPN_S2=... ESPN_SWID='{...}' ESPN_LEAGUE_ID=..."))
        else:
            checks.append(Check("credentials", OK, "espn cookies present"))
    else:
        checks.append(Check("credentials", OK, "manual provider needs none"))

    # 4. data
    db = pathlib.Path(db_path)
    if not db.exists():
        checks.append(Check("data", WARN, "no database yet",
                            "python3 -m fantasyedge pull"))
    else:
        from .store import Store
        store = Store(db)
        rows = store.seasons()
        store.close()
        if not rows:
            checks.append(Check("data", WARN, "database empty",
                                "python3 -m fantasyedge pull"))
        else:
            yrs = sorted({r["season"] for r in rows})
            checks.append(Check("data", OK,
                                f"{len(rows)} league-seasons loaded ({min(yrs)}-{max(yrs)})"))

    # 5. optional ADP
    if db.exists():
        from .store import Store
        store = Store(db)
        n = store.q("SELECT COUNT(*) c FROM adp")[0]["c"]
        store.close()
        checks.append(Check(
            "adp", OK if n else WARN,
            f"{n} ADP rows",
            "" if n else "Optional. Without it the reach analysis is skipped: "
                         "python3 -m fantasyedge adp-load --season 2026 --csv adp.csv",
        ))

    # verdict: first failing check owns the next action
    for c in checks:
        if c.status == FAIL:
            code = EXIT_AUTH if c.name == "credentials" else EXIT_CONFIG
            return Diagnosis(False, code, checks, f"{c.name}: {c.detail}", c.fix)
    for c in checks:
        if c.status == WARN and c.name == "data":
            return Diagnosis(False, EXIT_NODATA, checks, c.detail, c.fix)
    for c in checks:
        if c.status == WARN and c.fix:
            return Diagnosis(True, EXIT_READY, checks, c.detail, c.fix)

    return Diagnosis(True, EXIT_READY, checks, "ready",
                     "python3 -m fantasyedge report --out report.html")


def render_text(d: Diagnosis) -> str:
    mark = {OK: "ok  ", WARN: "warn", FAIL: "FAIL"}
    lines = ["", "fantasy-edge doctor", ""]
    for c in d.checks:
        lines.append(f"  [{mark[c.status]}] {c.name:12} {c.detail}")
        if c.fix and c.status != OK:
            lines.append(f"           -> {c.fix}")
    lines += ["", f"  next: {d.next_action}"]
    if d.next_command:
        lines.append(f"  run:  {d.next_command}")
    return "\n".join(lines)
