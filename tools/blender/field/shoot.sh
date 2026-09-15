#!/bin/sh
# Shoot the field and sideline look-dev shots under the studio's simulator
# slots: wait for a free slot, shoot, shut the simulator down, free the slot.
#   tools/blender/field/shoot.sh <udid> <out dir> [shots...]
cd "$(dirname "$0")/../../.."
UDID="$1"; OUT="$2"; shift 2
SHOTS="${*:-field-level sideline-props redzone-trails tabletop}"
SLOT=""
while [ -z "$SLOT" ]; do
  for n in 1 2; do
    if mkdir "/tmp/fe-sim-slot-$n" 2>/dev/null; then
      SLOT="/tmp/fe-sim-slot-$n"; echo "field specialist $(date +%s)" > "$SLOT/owner"; break
    fi
  done
  [ -z "$SLOT" ] && sleep 20
done
python3 tools/lookdev.py --device "$UDID" --out "$OUT" --port 8804 --only $SHOTS
xcrun simctl shutdown "$UDID" 2>/dev/null
lsof -ti tcp:8804 | xargs kill 2>/dev/null
rm -rf "$SLOT"
echo "done" > "$OUT/.done"
