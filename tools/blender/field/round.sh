#!/bin/sh
# One look-dev round for the field: build, then shoot field-level from each
# seat named (use "field" for the default seat), under the simulator slots.
#   tools/blender/field/round.sh <udid> <out dir> field sideline club
cd "$(dirname "$0")/../../.."
UDID="$1"; OUT="$2"; shift 2
LOG="/private/tmp/fsrev/xcb-round.log"
tools/blender/field/xcbuild.sh "$UDID" "$LOG"
grep -q "BUILD SUCCEEDED" "$LOG" || { grep -m8 "error:" "$LOG"; exit 1; }
rm -rf "$OUT"
for seat in "$@"; do
  if [ "$seat" = "field" ]; then
    SETTLE=20 SEAT= SUFFIX= tools/blender/field/shoot.sh "$UDID" "$OUT" field-level
  else
    SETTLE=20 SEAT="$seat" SUFFIX="-$seat" tools/blender/field/shoot.sh "$UDID" "$OUT" field-level
  fi
done
