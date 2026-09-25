#!/bin/bash
# Saturday on a real Apple Vision Pro, through the shared device script.
#
#   apps/saturday/apple/device.sh              build, sign, install, launch
#   apps/saturday/apple/device.sh --stats      the same, streaming frame times
#   apps/saturday/apple/device.sh --build-only works with no headset paired
#   apps/saturday/apple/device.sh --list       what is paired
#
# The script is apple/device.sh: signing team resolution, the install, the
# untrusted-developer step, and the [stadium-device] frame lines the simulator
# cannot produce. Only the four things that differ between the two apps are set
# here, exactly as apps/saturday/apple/sim.sh does for the simulator.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
export FE_BUNDLE="com.mutaaf.saturday"
export FE_PROJECT="apps/saturday/apple/Saturday.xcodeproj"
export FE_SCHEME="Saturday"
export FE_PRODUCT="Saturday.app"
exec "$ROOT/apple/device.sh" "$@"
