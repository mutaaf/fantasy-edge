#!/bin/bash
# Refresh the public demo from real data, but only publish if it is safe to.
#
# This runs unattended on a schedule, which is the whole reason for the gate
# below. Every step that could put somebody else's name on a public URL has to
# fail closed: a leak that nobody is watching is worse than a stale demo.
set -euo pipefail

cd "$(dirname "$0")/.."
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"

log() { printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }

# `--check` proves the scheduled job can actually run, without running it.
#
# Worth having because the failure this was written for was invisible from a
# shell. The job sat in launchd for a day exiting 126 - "Operation not
# permitted" - while the same script ran fine by hand: the repository was
# under ~/Desktop, which is one of the three folders macOS withholds from a
# background agent, so launchd could not execute the file at all. Nothing
# published, no error anybody saw, and a shell test could not have caught it
# because a shell has the grant the agent does not.
#
# So this exits before the first thing with a consequence, and reports what
# the run would depend on. `launchctl kickstart` it after any change to where
# this lives or what runs it.
if [ "${1:-}" = "--check" ]; then
  log "check: running as $(id -un) from $(pwd)"
  for f in Makefile data/fantasy.db "$HOME/.fantasy-edge/leagues.json"; do
    [ -r "$f" ] && log "  can read $f" || { log "  CANNOT READ $f"; exit 1; }
  done
  command -v python3 >/dev/null || { log "  no python3 on PATH"; exit 1; }
  log "  python3 at $(command -v python3)"
  git rev-parse --short HEAD >/dev/null 2>&1 \
    && log "  git ok at $(git rev-parse --short HEAD)" \
    || { log "  not a git checkout"; exit 1; }
  log "check: this job can run"
  exit 0
fi

# Credentials live outside the repository and are read, never written.
[ -f "$HOME/.fantasy-edge/espn.env" ] && { set -a; . "$HOME/.fantasy-edge/espn.env"; set +a; }

log "pulling the current season"
for L in $(python3 -c "
import json,pathlib
p = pathlib.Path.home()/'.fantasy-edge'/'leagues.json'
print(' '.join(e['league_id'] for e in json.loads(p.read_text())))"); do
  python3 -m fantasyedge pull --provider espn --league "$L" --seasons 2026 --json >/dev/null 2>&1 \
    || log "  warn: league $L did not pull; keeping what is stored"
done

log "running the suite"
make test >/dev/null || { log "ABORT: tests failed, nothing published"; exit 1; }

log "rebuilding the pages"
make docs >/dev/null

# The gate. Every manager and league name in the database, checked against the
# built page - except the reader's own teams, which are kept on purpose.
log "checking for leaks"
python3 - <<'PY' || { echo "ABORT: a real name reached the built page"; exit 1; }
import json, pathlib, sqlite3, sys, urllib.request

c = sqlite3.connect("data/fantasy.db"); c.row_factory = sqlite3.Row
html = pathlib.Path("docs/demo.html").read_text()

try:
    mos = json.loads(urllib.request.urlopen(
        "http://127.0.0.1:8770/api/mosaic", timeout=30).read())
    mine = {(L.get("you") or {}).get("name", "").strip() for L in mos["leagues"]}
except Exception:
    prefs = json.loads((pathlib.Path.home()/".fantasy-edge"/"prefs.json").read_text())
    picks = prefs.get("teams") or {}
    mine = {r["name"].strip() for r in c.execute(
        "SELECT league_id, team_id, name FROM manager WHERE season=2026")
        if picks.get(f"espn-{r['league_id']}") == str(r["team_id"])}
mine.discard("")

names = {str(v).strip() for r in c.execute("SELECT name, owner FROM manager")
         for v in (r["name"], r["owner"]) if v}
names |= {str(r["name"]).strip() for r in c.execute("SELECT name FROM league") if r["name"]}

leaked = [n for n in names
          if len(n) >= 4 and not n.startswith("{") and n not in mine and n in html]
if leaked:
    print("LEAKED:", leaked[:10], file=sys.stderr)
    sys.exit(1)
print(f"  clean: {len(names)} real names checked, {len(mine)} of yours kept on purpose")
PY

if git diff --quiet -- docs; then
  log "no change to publish"
  exit 0
fi

log "publishing"
git add docs
git -c user.name="$(git config user.name)" -c user.email="$(git config user.email)" \
    commit -q -m "Refresh the public demo

Rebuilt from the current season by tools/publish_demo.sh. Only the reader's own
teams carry their real names; every other manager is a stand-in, and the build
is refused if any of them reaches the page."
git push -q origin main
log "published"
