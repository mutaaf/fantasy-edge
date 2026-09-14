# Fantasy Edge Stadium for Android

Tabletop and Stadium for Android phones and tablets. The app is a thin renderer of the scene the API serves from `fantasyedge/scene.py`. It holds no football logic: where a pass peaks, which lane a play takes, which drive is shown and when a section lights up all arrive decided in the JSON. The app turns those primitives into meshes and draws them.

- **Rendering:** Kotlin, Jetpack Compose, and [Filament](https://github.com/google/filament).
- **Materials:** compiled on the device at first launch with filamat and cached, so there is no offline material compiler in the build.

## Run it

```bash
# 1. An API with the repo's recorded games, parked on the Bears' pick-six
python3 clients/android/scripts/serve_replay.py --port 8794 --event 401772810 --at 1929 --speed 60

# 2. Build, test, install (JDK 17, Android SDK 36)
cd clients/android
./gradlew assembleDebug testDebugUnitTest
adb install -r app/build/outputs/apk/debug/app-debug.apk

# 3. Open a mode directly (the emulator reaches the Mac at 10.0.2.2)
adb shell am start -n com.mutaaf.fantasyedge.stadium/.ui.MainActivity --es mode STADIUM
```

On a real phone, set the API address in the app's settings. Cleartext is allowed only to `10.0.2.2`, `localhost` and `127.0.0.1` (`res/xml/network_security_config.xml`). The replay remote is a loopback-only POST, so driving a replay from a phone on the LAN needs `FANTASYEDGE_ALLOW_REMOTE_REPLAY=1` on the API.

## What it does

| | |
|---|---|
| **Tabletop** | The lower bowl, floodlit, orbiting. Drag to orbit, pinch to zoom, double-tap to reset. |
| **Stadium** | The seat from `presentation.stadium.seat`. Drag, or turn the phone (game rotation vector), to look around. |
| **Plays** | Each new arc is flown by the ball for the scene's `duration`, then laid down. A backlog is squeezed, and reduce motion (animator scale 0) lands the ball instead of flying it. |
| **Moments** | `activeMoment` shows a banner. `bowl.sectionTint` relights the scoring side's club-coloured crowd in its chip colour and dims the other side to `dim`. |
| **Replay** | Play, pause, seek and speed go through `POST /api/replay`. The game list comes from `GET /api/replay`. |
| **Layout** | On tablets (wide *and* tall), the drive log is a side panel. On phones it is a bottom sheet, and a landscape phone gets a compact one-row overlay. Touch targets are at least 48 dp. |

## Contract

- **Versions:** `SceneDecoder` accepts any `1.x` scene and ignores fields it doesn't know. It refuses `2.x` with a sentence the screen shows, rather than drawing a new contract with old rules.
- **Math:** `scene/SceneMath.kt` is a line-for-line port of `apple/.../Stadium/SceneMath.swift`: arc points, dashes, bowl superellipse, tier height, horizon, play queue. The tests hold it to the scene's own numbers.
- **Tokens:** `design/tokens.json` is copied into the APK's assets by the `copyDesignTokens` Gradle task, never duplicated. The Compose chrome reads colours from it; the 3D uses the scene's embedded `palette`.

## Tests

`./gradlew testDebugUnitTest` runs JVM tests with no network and no device. They cover:
- spec parsing across every recorded scene
- version gating
- arc apex, lane and endpoints
- dashes, bowl and tier geometry
- crowd, rim-light, field, arc, laser, beacon and horizon primitive counts
- index validity
- the play queue
- every colour token the scenes use existing in `design/tokens.json`

The fixtures in `app/src/test/resources` are recorded by `scripts/record_fixtures.py`, which replays the repo's whole-game fixtures through the real API. Its output is deterministic, so never edit the fixtures by hand; re-run the script.

## Where the spec is silent

`geometry/StadiumGeometry.Look` holds every presentation number the scene doesn't carry. Each matches the visionOS renderer so the platforms agree, and each belongs in `scene.py` or `tokens.json`:
- crowd count
- arc and halo radius, and score emphasis
- rim height above the tier and lamp size (the spec's `rimLights.offset` and `height` are not what the headset uses)
- ball and beacon radius
- ball lift
- horizon thickness
- sky radius
- yard-number inset
- crowd colour mix and visitor-section bounds (the spec's `awaySection.fromX` is unused by both renderers)
