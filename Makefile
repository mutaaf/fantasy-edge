.PHONY: test test-all saturday-test saturday-doctor saturday-replay \
	doctor demo publish-demo report docs api board clean verify-scene \
	sim sim-doctor sim-shots sim-clean \
	device device-build device-stats device-list

# FANTASYEDGE_CORRECT_PLAYS=0 keeps the promise the suite is built on: no
# network. Correcting a finished game's plays reads nflverse (truth.py), and a
# test must never depend on a release being reachable. The correction itself is
# tested against fixtures cut by tools/make_replay_fixture.py --nflverse.
test:
	FANTASYEDGE_CORRECT_PLAYS=0 python3 -m unittest discover -s tests

# --- apps/saturday (college football; see apps/saturday/CLAUDE.md) ---

saturday-test:
	$(MAKE) -C apps/saturday test

saturday-doctor:
	$(MAKE) -C apps/saturday doctor

saturday-replay:
	$(MAKE) -C apps/saturday replay

# Both products. The stadium is shared, so a change to packages/ has to keep
# fantasy-edge and Saturday green together.
test-all: test saturday-test

doctor:
	python3 -m fantasyedge doctor

# End-to-end run with no credentials, against the bundled fixture.
demo:
	python3 -m fantasyedge --db data/demo.db pull --provider manual \
		--draft tests/fixtures/draft.txt --standings tests/fixtures/standings.txt \
		--league demo --season 2025
	python3 -m fantasyedge --db data/demo.db analyze

report:
	python3 -m fantasyedge report --out report.html

# The read API plus the mosaic. --host 0.0.0.0 lets a TV or headset reach it.
api:
	python3 -m fantasyedge api --host 0.0.0.0

board:
	python3 -m fantasyedge api

# Static build for GitHub Pages. --anon scrubs league and manager names.
docs:
	python3 tools/build_docs.py --anon

fixtures:
	python3 tests/fixtures/make_fixtures.py

# Decode every replayed scene with the Swift client's own types and check the
# maths (seats, facing, trails) against scene.py. Needs Xcode's swiftc.
STADIUM = packages/swift/StadiumKit/Sources/StadiumKit
verify-scene:
	mkdir -p .work/scenes
	python3 tools/scene_samples.py .work/scenes
	swiftc -O -o .work/verify-scene $(STADIUM)/SceneSpec.swift $(STADIUM)/SceneLook.swift \
		$(STADIUM)/Actors/*/*Look.swift $(STADIUM)/Actors/Field/FieldArtSpec.swift \
		$(STADIUM)/SceneMath.swift $(STADIUM)/StadiumVenue.swift \
		$(STADIUM)/Actors/Broadcast/BroadcastFlight.swift apple/verify_scene.swift
	.work/verify-scene .work/scenes/*.json

# The composer's two rules, swept exhaustively. Both were run by copying the
# swiftc line out of the file's own header, which every agent re-derived and
# some got wrong; they are gates, so they have targets.
verify-moment:
	swiftc -parse-as-library -o .work/verify-moment $(STADIUM)/MomentGate.swift \
		$(STADIUM)/LaidPlay.swift $(STADIUM)/SceneSpec.swift $(STADIUM)/SceneLook.swift \
		$(STADIUM)/Actors/*/*Look.swift $(STADIUM)/Actors/Field/FieldArtSpec.swift \
		apple/verify_moment.swift
	.work/verify-moment

verify-crowd:
	swiftc -parse-as-library -o .work/verify-crowd \
		$(STADIUM)/Actors/Crowd/CrowdChoreography.swift apple/verify_crowd.swift
	.work/verify-crowd

# The local visionOS rig. apple/sim.sh holds the defaults every agent used to
# re-derive from comments: the generic destination that actually builds, the
# device by name, one derived-data path, and a wait for the machine to be quiet
# enough that the simulator's own home screen is not killed mid-frame.
sim:
	apple/sim.sh run

sim-doctor:
	apple/sim.sh doctor

sim-shots:
	apple/sim.sh shots --out .work/shots/local

sim-clean:
	apple/sim.sh clean
# On a real Apple Vision Pro. The simulator cannot measure frame time, so the
# 90 fps the art bible asks for has never been checked anywhere else.
# docs/DEVICE.md is the guide; `device-build` needs no headset.
device:
	apple/device.sh

device-build:
	apple/device.sh --build-only

# The same, with -stadiumStats, streaming the [stadium-device] lines: real fps,
# the frames that missed 11.1 ms, and peak memory.
device-stats:
	apple/device.sh --stats

device-list:
	apple/device.sh --list

clean:
	rm -rf data/*.db report.html
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

# Refresh the PUBLIC demo from live data and push it. Named `publish-demo`
# rather than `demo` because `demo` is already the credential-free fixture run,
# and make silently keeps the first definition of a duplicated target - so this
# would have looked wired up and done nothing.
#
# Refuses to publish if the suite fails, or if any manager who is not you
# reaches the built page. Unattended publishing has to fail closed.
publish-demo:
	tools/publish_demo.sh
