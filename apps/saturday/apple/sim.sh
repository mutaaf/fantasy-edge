#!/bin/bash
# Saturday on the shared visionOS rig.
#
#   apps/saturday/apple/sim.sh doctor|build|run|shots|clean
#
# The rig is apple/sim.sh: one named simulator, one derived-data path, one
# load gate, and the destination that actually builds. Only the four things
# that differ between the two apps are set here.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
export FE_BUNDLE="com.mutaaf.saturday"
export FE_PROJECT="apps/saturday/apple/Saturday.xcodeproj"
export FE_SCHEME="Saturday"
export FE_PRODUCT="Saturday.app"
export FE_DD="${SAT_DD:-$ROOT/.work/dd-saturday}"
exec "$ROOT/apple/sim.sh" "$@"
