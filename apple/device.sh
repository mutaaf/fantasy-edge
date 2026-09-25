#!/bin/bash
# Build Fantasy Edge for a real Apple Vision Pro, install it, and launch it.
#
#   apple/device.sh                 build, install, launch
#   apple/device.sh --stats         same, with -stadiumStats, and stream the log
#   apple/device.sh --list          what is paired
#   apple/device.sh --build-only    build and stop
#
# The simulator path is untouched: it does not sign, and `make build-visionos`
# still does exactly what it did. This is the other half.
#
# Everything that can go wrong here goes wrong the same three ways - nothing
# paired, nothing signed, the developer not trusted on the headset - and each
# one produces a wall of Xcode text that says none of those words. So each is
# caught and answered in English.
set -uo pipefail

cd "$(dirname "$0")/.."
# Parameterised the way apple/sim.sh is, so Saturday runs on the headset
# through the same script rather than a second copy of it. Saturday sets these
# in apps/saturday/apple/device.sh; unset, they mean fantasy-edge.
BUNDLE="${FE_BUNDLE:-com.mutaaf.fantasyedge}"
PROJECT="${FE_PROJECT:-apple/FantasyEdge.xcodeproj}"
SCHEME="${FE_SCHEME:-FantasyEdge}"
APP_NAME="${FE_PRODUCT:-FantasyEdge.app}"
DD="${FE_DD:-.work/dd-device-$SCHEME}"
STATS=0
BUILD_ONLY=0

for arg in "$@"; do
  case "$arg" in
    --stats)      STATS=1 ;;
    --build-only) BUILD_ONLY=1 ;;
    --list)       xcrun devicectl list devices; exit 0 ;;
    -h|--help)    sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31m%s\033[0m\n' "$*" >&2; }

# ---------------------------------------------------------------- the headset
# `devicectl list devices` prints simulators too; a real headset is the row
# whose Reality column says "physical" and whose model is an Apple Vision Pro.
device_line() {
  xcrun devicectl list devices 2>/dev/null \
    | grep -i "Apple Vision Pro" | grep -i "physical" | head -1
}

LINE="$(device_line)"
if [ -z "$LINE" ] && [ "$BUILD_ONLY" -eq 1 ]; then
  # A build needs a signing team, not a headset. Checking the device first
  # would mean nobody could prove the device build compiles until the headset
  # was in the room, which is exactly backwards.
  say "No headset paired; building anyway (--build-only)"
elif [ -z "$LINE" ]; then
  fail "No Apple Vision Pro is paired with this Mac."
  cat <<'EOS'

To pair one, on the headset:
  1. Settings > General > Remote Devices, and leave that screen open.
  2. Settings > Privacy & Security > Developer Mode, turn it on, restart when asked.
On the Mac:
  3. Xcode > Window > Devices and Simulators, pick the headset, enter the code it shows.
Both must be on the same Wi-Fi network.

Then run this again. `apple/device.sh --list` shows what is currently paired.
EOS
  exit 1
fi

DEVICE_ID=""
DEVICE_NAME=""
if [ -n "$LINE" ]; then
  # The identifier is the UDID column: the first field that looks like one.
  DEVICE_ID="$(echo "$LINE" | grep -oE '[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}' | head -1)"
  if [ -z "$DEVICE_ID" ]; then
    DEVICE_ID="$(echo "$LINE" | grep -oE '[0-9A-Fa-f]{8}-[0-9A-Fa-f]{16}' | head -1)"
  fi
  DEVICE_NAME="$(echo "$LINE" | sed 's/  */ /g' | cut -d' ' -f1-2)"
  if [ -z "$DEVICE_ID" ] && [ "$BUILD_ONLY" -eq 0 ]; then
    fail "Found a headset but could not read its identifier from:"
    echo "$LINE" >&2
    exit 1
  fi

  STATE="$(echo "$LINE" | grep -oiE 'available|unavailable|connecting|shutdown' | head -1)"
  if echo "$STATE" | grep -qi unavailable && [ "$BUILD_ONLY" -eq 0 ]; then
    fail "The headset is paired but not reachable right now (state: $STATE)."
    echo "Put it on, unlock it, and make sure it is on the same Wi-Fi as this Mac." >&2
    exit 1
  fi
  say "Device: $DEVICE_NAME  ($DEVICE_ID)"
fi

# ----------------------------------------------------------------- the build
python3 apple/generate_project.py || exit 1

say "Building for visionOS device"
# -allowProvisioningUpdates lets Xcode register the App ID and make a profile
# on first run. Without it the first build of a bundle id nobody has ever
# built fails with a provisioning error and no explanation of what to do.
#
# -allowProvisioningDeviceRegistration is the other half, and it bites the
# first time a headset is paired: the profile is made from the devices the
# team knew about, so a device paired afterwards is not in it. The build
# still succeeds and signs; the INSTALL fails, with "this provisioning
# profile cannot be installed on this device" and nothing about the real
# cause. This flag registers the device and re-makes the profile.
BUILD_LOG=".work/device-build.log"
mkdir -p .work
# Status from xcodebuild itself, not from a pipeline. An earlier version piped
# through tee and grep and read $PIPESTATUS after a trailing `|| true`, which
# always said success - so a failed build printed its errors and then
# announced the app it had not built.
# Build AT the headset when we have one, not at a generic device. Xcode only
# registers a device it is actually building for, so with the generic
# destination a newly paired headset is never added to the profile and the
# install fails however many times you pass the registration flag.
DEST="generic/platform=visionOS"
[ -n "${DEVICE_ID:-}" ] && DEST="id=$DEVICE_ID"
xcodebuild -project "$PROJECT" -scheme "$SCHEME" \
  -destination "$DEST" \
  -derivedDataPath "$DD" -allowProvisioningUpdates -allowProvisioningDeviceRegistration build > "$BUILD_LOG" 2>&1
STATUS=$?
grep -E "error:|warning:|BUILD (SUCCEEDED|FAILED)|Signing Identity" "$BUILD_LOG" | sort -u | head -20

if [ "$STATUS" -ne 0 ]; then
  fail "Build failed."
  if grep -qi "no profiles for\|requires a provisioning profile\|no signing certificate" "$BUILD_LOG"; then
    cat <<EOS

This is a signing problem, not a code problem. Most likely one of:
  * Xcode is not signed in to the developer account.
    Xcode > Settings > Accounts, add the Apple ID that holds the membership.
  * The team is wrong. This build used: $(grep -m1 'signing team' "$BUILD_LOG" 2>/dev/null || echo 'see above')
    Override it with:  FE_TEAM=XXXXXXXXXX make device
  * The headset is not registered to the team. Building from Xcode once
    (Product > Run with the headset selected) registers it.
EOS
  fi
  echo "Full log: $BUILD_LOG" >&2
  exit 1
fi

APP="$DD/Build/Products/Debug-xros/$APP_NAME"
[ -d "$APP" ] || APP="$DD/Build/Products/Release-xros/$APP_NAME"
if [ ! -d "$APP" ]; then
  fail "Build succeeded but no app bundle at $DD/Build/Products/*-xros/$APP_NAME"
  exit 1
fi
say "Built $APP"
[ "$BUILD_ONLY" -eq 1 ] && exit 0

# --------------------------------------------------------- install and launch
say "Installing"
INSTALL_LOG=".work/device-install.log"
if ! xcrun devicectl device install app --device "$DEVICE_ID" "$APP" > "$INSTALL_LOG" 2>&1; then
  fail "Install failed."
  tail -20 "$INSTALL_LOG" >&2
  if grep -qi "trust\|untrusted\|developer" "$INSTALL_LOG"; then
    cat <<'EOS'

If it mentions trust: on the headset, open
  Settings > General > VPN & Device Management
and trust the developer certificate, then run this again.
EOS
  fi
  exit 1
fi

say "Launching"
ARGS=()
[ "$STATS" -eq 1 ] && ARGS=(-stadiumStats)
if ! xcrun devicectl device process launch --device "$DEVICE_ID" \
      ${ARGS:+--} "${ARGS[@]:-}" "$BUNDLE" 2>&1 | tail -5; then
  fail "Launch failed. If the headset says the developer is untrusted:"
  echo "  Settings > General > VPN & Device Management > trust the certificate." >&2
  exit 1
fi

cat <<EOS

Running on $DEVICE_NAME.
  Put the headset on: Fantasy Edge is open.

EOS

if [ "$STATS" -eq 1 ]; then
  cat <<'EOS'
Streaming the stadium's own numbers. Open the stadium in the headset, sit in a
seat, and leave it running for ten seconds or so - the first report needs 300
frames. Ctrl-C to stop.

EOS
  xcrun devicectl device process view-log --device "$DEVICE_ID" 2>/dev/null \
    | grep --line-buffered -E "\[stadium-device\]|\[stadium-stats\]|\[stadium-timing\]" \
    || cat <<'EOS'

Could not stream the device log from here. Instead:
  Console.app > pick the headset on the left > filter on "stadium"
and read the [stadium-device] lines.
EOS
fi
