#!/bin/bash
# The local visionOS rig: one named simulator, one build, one command to look.
#
#   apple/sim.sh doctor           what the machine has, and whether it can build
#   apple/sim.sh build            build to .work/dd (the one derived-data path)
#   apple/sim.sh run              build, install, launch, and open the Simulator
#   apple/sim.sh shots [args...]  build then shoot the look-dev set
#   apple/sim.sh clean            shut everything down and free the caches
#
# Why a script rather than four Makefile lines: every agent that shot the
# stadium re-derived the destination, the device id, the bundle id and the
# derived-data path from comments, and several got one wrong - a stale bundle
# installed from another agent's build, a name-shaped destination that listed
# every simulator and built nothing, a visionOS 1.2 clone that refused the app.
# Those are the defaults here.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BUNDLE="com.mutaaf.fantasyedge"
PROJECT="apple/FantasyEdge.xcodeproj"
SCHEME="FantasyEdge"
DD="${FE_DD:-$ROOT/.work/dd}"
APP="$DD/Build/Products/Debug-xrsimulator/FantasyEdge.app"
# Named rather than cloned per run: a clone per agent is what filled this Mac
# with 115 devices and 41 GB of simulator data. FE_SIM overrides for a second
# rig; keep the name, not the id, so a runtime upgrade does not strand it.
SIM="${FE_SIM:-Stadium 26.5}"

die() { echo "error: $*" >&2; exit 1; }

sim_id() {
  xcrun simctl list devices available -j \
    | python3 -c "
import json,sys
want = sys.argv[1]
for runtime, devices in json.load(sys.stdin)['devices'].items():
    if 'xrOS' not in runtime and 'visionOS' not in runtime:
        continue
    for d in devices:
        if d['name'] == want and d.get('isAvailable'):
            print(d['udid']); raise SystemExit
raise SystemExit('no available visionOS simulator named %r' % want)
" "$SIM"
}

# The load the launcher dies at. visionOS renders a whole headset; the stadium
# is 148k triangles of it. Two of these at once starve the simulator's own home
# screen, which is killed if it cannot draw a frame in ten seconds - every
# RealityLauncher crash on this Mac has been that, never our app.
wait_for_quiet() {
  local limit="${FE_LOAD:-30}" waited=0
  while true; do
    local load
    load=$(python3 -c "import os; print(int(os.getloadavg()[0]))")
    [ "$load" -le "$limit" ] && break
    [ "$waited" -eq 0 ] && echo "  load $load, waiting for it to fall under $limit"
    sleep 15; waited=$((waited + 15))
    [ "$waited" -ge 900 ] && die "load still $load after 15 minutes; something else is using this Mac"
  done
}

cmd_doctor() {
  local ok=0
  echo "Xcode"
  # Capture before trimming: piping into `head` closes the pipe, xcodebuild
  # dies of SIGPIPE, and the check reported MISSING beside the version it had
  # just printed.
  local version
  if version=$(xcodebuild -version 2>/dev/null); then
    echo "  $(echo "$version" | sed -n 1p)"
  else
    echo "  MISSING"; ok=1
  fi
  if xcodebuild -showsdks >/dev/null 2>&1; then
    echo "  licence accepted"
  else
    echo "  LICENCE NOT ACCEPTED - run: sudo xcodebuild -license accept"; ok=1
  fi
  echo "visionOS runtimes"
  xcrun simctl list runtimes 2>/dev/null | grep -iE "visionos|xros" | sed 's/^/  /' || echo "  none"
  echo "simulator"
  if id=$(sim_id 2>/dev/null); then echo "  $SIM ($id)"; else echo "  NOT FOUND: $SIM"; ok=1; fi
  echo "devices on this Mac: $(xcrun simctl list devices 2>/dev/null | grep -cE '^\s+\S.*\(')"
  echo "headset"
  if xcrun devicectl list devices 2>/dev/null | grep -q "physical.*Vision"; then
    xcrun devicectl list devices 2>/dev/null | grep "Vision" | grep physical | sed 's/^/  /'
  else
    echo "  none paired - see docs/DEVICE.md (frame rate can only be measured there)"
  fi
  echo "disk"
  df -h /System/Volumes/Data | tail -1 | awk '{print "  " $4 " free of " $2}'
  echo "load"
  echo "  $(uptime | sed 's/.*averages: //')"
  return $ok
}

cmd_build() {
  wait_for_quiet
  echo "building to $DD"
  # A destination by NAME lists every simulator and builds nothing. The generic
  # destination is the one that builds; the id is for installing.
  xcodebuild -project "$PROJECT" -scheme "$SCHEME" \
    -destination "generic/platform=visionOS Simulator" -derivedDataPath "$DD" build \
    | grep -E "error:|warning:|BUILD" | grep -v appintentsmetadataprocessor | sort -u || true
  [ -d "$APP" ] || die "no app at $APP"
  echo "built $APP"
}

cmd_run() {
  cmd_build
  local id; id=$(sim_id)
  xcrun simctl boot "$id" 2>/dev/null || true
  open -a Simulator
  xcrun simctl install "$id" "$APP"
  xcrun simctl launch "$id" "$BUNDLE" "$@"
  echo "launched on $SIM"
}

cmd_shots() {
  cmd_build
  local id; id=$(sim_id)
  python3 tools/lookdev.py --device "$id" --app "$APP" "$@"
}

cmd_clean() {
  xcrun simctl shutdown all 2>/dev/null || true
  xcrun simctl delete unavailable 2>/dev/null || true
  rm -rf "$DD"
  echo "shut down, stale devices deleted, $DD removed"
  echo "Xcode's own cache is ~/Library/Developer/Xcode/DerivedData - remove it by hand if you want it gone"
}

case "${1:-doctor}" in
  doctor) cmd_doctor ;;
  build)  cmd_build ;;
  run)    shift; cmd_run "$@" ;;
  shots)  shift; cmd_shots "$@" ;;
  clean)  cmd_clean ;;
  *)      die "unknown command ${1}; try doctor, build, run, shots, clean" ;;
esac
