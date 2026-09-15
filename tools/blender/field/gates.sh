#!/bin/sh
# The two geometry and colour gates, niced.
#   tools/blender/field/gates.sh
cd "$(dirname "$0")/../../.."
W=.work/gates
rm -rf "$W" && mkdir -p "$W/scenes"
python3 tools/scene_samples.py "$W/scenes" | tail -1
S=apple/FantasyEdge/Sources/Stadium
nice -n 10 swiftc -o "$W/verify-scene" "$S/SceneSpec.swift" "$S/SceneLook.swift" "$S"/Actors/*/*Look.swift \
  "$S/Actors/Field/FieldArtSpec.swift" "$S/SceneMath.swift" "$S/Actors/Broadcast/BroadcastFlight.swift" \
  apple/verify_scene.swift || exit 1
"$W/verify-scene" "$W"/scenes/*.json | tail -3
python3 apple/contrast_check.py | tail -4
