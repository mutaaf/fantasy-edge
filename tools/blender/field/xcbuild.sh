#!/bin/sh
# Build the app for one simulator, niced and capped at four jobs (studio rule).
#   tools/blender/field/xcbuild.sh <udid> <log>
set -e
cd "$(dirname "$0")/../../.."
python3 apple/generate_project.py >/dev/null
nice -n 10 xcodebuild -project apple/FantasyEdge.xcodeproj -scheme FantasyEdge \
  -destination "platform=visionOS Simulator,id=$1" -derivedDataPath .work/dd -jobs 4 build > "$2" 2>&1
