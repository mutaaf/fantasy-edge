# Running the stadium locally

One simulator, one build, one command.

```bash
make sim-doctor     # what this Mac has, and whether it can build
make sim            # build, install, launch, open the Simulator
make sim-shots      # build, then shoot the look-dev set
make sim-clean      # shut down, drop stale devices, remove .work/dd
```

`apple/sim.sh` is the whole rig; the make targets are shortcuts. It holds the
defaults that were previously copied out of comments by hand, and got wrong:

| Thing | Value | Why it is not obvious |
|---|---|---|
| Build destination | `generic/platform=visionOS Simulator` | A destination **by name** lists every simulator and builds nothing. This one builds; the device id is for installing. |
| Simulator | `Stadium 26.5`, by name | A clone per run is what put 115 devices and 41 GB of simulator data on this Mac. Naming survives a runtime upgrade; an id does not. |
| Derived data | `.work/dd` | Sharing one path across agents installed one agent's stale bundle from another's build. `FE_DD` overrides. |
| Bundle id | `com.mutaaf.fantasyedge` | A wrong id fails as a launch error that reads like a crash. |
| Load gate | waits under 30 | See below. `FE_LOAD` overrides. |

## The simulator's home screen gets killed, and it is not our app

Every `RealityLauncher` crash on this Mac is the same: *scene-update watchdog
transgression, exhausted real (wall clock) time allowance of 10.00 seconds*,
with the CPU pinned at 99%. `RealityLauncher` is the **simulator's own home
screen**. FantasyEdge has never appeared in a crash report.

visionOS renders a whole headset, and the stadium is a heavy scene: ~148k
triangles, ~100 draw parts, 44,000 fans. One simulator is comfortable. Several
at once — which is what parallel agents do — starve the launcher until it
misses a frame deadline and the system kills it. Load has been seen at 938.

So `sim.sh` waits for the one-minute load average to fall under 30 before it
builds or shoots. If you see the crash anyway, check what else is running
before suspecting the app.

**The one real caveat:** the app blocks its main thread for about four seconds
building the crowd on first open. That is one-off and after the immersive space
is already up, but it is the same class of thing the watchdog kills, and it is
the startup defect worth measuring on a real headset.

## What is installed, and what was removed

Kept: visionOS **26.5** (what the shots are taken on) and **27.0**.

Removed on 2026-09-23: visionOS **1.2** and **2.1** runtimes (30 GB), 40
unavailable devices, six stale agent clones, Xcode's DerivedData and the
worktrees' `.work/dd-*` (21 GB+). 56 GB freed. An agent had already lost a run
to a visionOS 1.2 clone refusing the app with *"Requires a Newer Version of
visionOS"*.

Re-install a runtime from Xcode → Settings → Components if one is ever needed.

## On a real Vision Pro

The simulator cannot measure frame time, and never could — a simulator build
now says so in its own log rather than letting anyone quote its numbers. For
frame rate, the press box at true scale, and whether the whip-around between
games is comfortable, see `docs/DEVICE.md` and `make device`.
