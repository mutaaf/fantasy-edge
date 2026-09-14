PY ?= python3
export PYTHONPATH := packages:apps/saturday:tests

.PHONY: test fixtures doctor serve replay project build-visionos build-ios mockups

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

project:
	$(PY) apps/saturday/apple/generate_project.py

build-visionos: project
	xcodebuild -project apps/saturday/apple/Saturday.xcodeproj -scheme Saturday \
	  -destination 'platform=visionOS Simulator,name=Apple Vision Pro,OS=26.5' -derivedDataPath apps/saturday/apple/build build

build-ios: project
	xcodebuild -project apps/saturday/apple/Saturday.xcodeproj -scheme Saturday \
	  -destination 'platform=iOS Simulator,name=iPhone 16 Pro' -derivedDataPath apps/saturday/apple/build build

mockups:
	$(PY) design/build.py && $(PY) design/immersive.py
