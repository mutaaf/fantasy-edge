PY ?= python3
# Saturday lives at apps/saturday in the monorepo; `cfb` and the other shared
# packages live at its root. Run these from this directory, or use the root
# Makefile's saturday-* targets.
MONO := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))../..)
export PYTHONPATH := $(MONO)/packages:$(CURDIR):$(CURDIR)/tests

.PHONY: test fixtures doctor serve replay live live-test record-weekend record-dry-run record-plan \
	project build-visionos build-ios build-ipad mockups

test:
	$(PY) -m unittest discover -s tests -t tests

fixtures:
	$(PY) tools/make_fixtures.py

doctor:
	$(PY) -m api doctor

serve:
	$(PY) -m api serve --source fixtures --host 0.0.0.0

replay:
	$(PY) -m api serve --source capture:data/capture/2026-09-12@20260913T003400Z --host 0.0.0.0

# --- the live test (docs/LIVE_TEST.md) ---

SLATE ?= 2026-09-19
HOST ?= 0.0.0.0

live:            ## API against live ESPN, reachable from a phone or headset on the LAN
	$(PY) -m api serve --source espn --host $(HOST)

live-test: doctor live   ## doctor first, then the live API

record-plan:     ## the window the recorder computes from the real schedule
	$(PY) tools/record_slate.py --slate $(SLATE) --plan

record-weekend:  ## wait for the window, record the weekend, keep the Mac awake
	tools/record_weekend.sh $(SLATE)

record-dry-run:  ## prove the recording works now: 3 minutes against today's board
	tools/record_weekend.sh $(SLATE) --dry-run 3 --interval 30 \
	  --out data/capture/$(SLATE)-pregame --watch 401856688

project:
	$(PY) apps/saturday/apple/generate_project.py

build-visionos: project
	xcodebuild -project apps/saturday/apple/Saturday.xcodeproj -scheme Saturday \
	  -destination 'platform=visionOS Simulator,name=Apple Vision Pro,OS=26.5' -derivedDataPath apps/saturday/apple/build build

build-ios: project
	xcodebuild -project apps/saturday/apple/Saturday.xcodeproj -scheme Saturday \
	  -destination 'platform=iOS Simulator,name=iPhone 17 Pro,OS=26.5' -derivedDataPath apps/saturday/apple/build build

mockups:
	$(PY) design/build.py && $(PY) design/immersive.py

build-ipad: project
	xcodebuild -project apps/saturday/apple/Saturday.xcodeproj -scheme Saturday \
	  -destination 'platform=iOS Simulator,name=iPad Pro 13-inch (M5),OS=26.5' -derivedDataPath apps/saturday/apple/build build
