# Running on a real Apple Vision Pro

Everything in this project has been judged from simulator screenshots. That is
honest for some things and worthless for others, and the line between them
matters:

| | The simulator can tell you | Only a headset can tell you |
|---|---|---|
| Triangles, draw parts, texture memory | yes, exactly | — |
| Where the seconds before the first frame go | ratios and load order | the real seconds |
| **Frame rate** | **no** | yes |
| **Memory the system will kill you for** | no | yes |
| Whether something reads at true scale | no | yes |

The art bible asks for 90 fps in full immersion. Nobody has ever measured it,
because nothing before this could. That is what this page is for.

---

## Once: pair the headset

**On the headset**

1. **Settings > Privacy & Security > Developer Mode** — turn it on. It will ask
   to restart; let it.
2. **Settings > General > Remote Devices** — open it and leave it open. The Mac
   appears here when it is looking.

**On the Mac**

3. **Xcode > Window > Devices and Simulators** (⇧⌘2). The headset appears in the
   left column. Click **Pair**, and type the six digits the headset shows.

Both must be on the same Wi-Fi network. There is no cable option: a Vision Pro
pairs wirelessly, so a weak network makes installs slow rather than failing
outright.

Check it worked:

```bash
make device-list
```

The headset is the row that says `physical` in the last column. Simulators say
`simulated`; every other row can be ignored.

---

## Every time: build, install, run

```bash
make device
```

That regenerates the Xcode project, builds for the headset, signs it, installs
it and launches it. Put the headset on and Fantasy Edge is open.

```bash
make device-build     # build only; works with no headset in the room
make device-stats     # the same, plus -stadiumStats, streaming the numbers
make device-list      # what is paired
```

### The first run will stop you once

The first time a developer-signed app runs on a headset it is not trusted yet.
The install or launch fails and the headset says something about an untrusted
developer. Fix it once and it stays fixed:

**Settings > General > VPN & Device Management** on the headset → your developer
certificate → **Trust**.

Then `make device` again.

---

## Signing, and what to do when it breaks

The project signs automatically. Which team it signs for is worked out from
this Mac rather than written into the source:

1. `FE_TEAM` in the environment, if set;
2. `apple/signing.json` (`{"team": "XXXXXXXXXX"}`), if present;
3. otherwise, the team holding a provisioning profile that names visionOS.

`python3 apple/generate_project.py` prints which it chose and why. On this Mac
that is **Z73865R687 (Mutaaf Aziz)**, the only team here with a visionOS
profile. To force a different one:

```bash
FE_TEAM=XXXXXXXXXX make device
```

**The simulator never signs.** `CODE_SIGNING_ALLOWED` is off for the simulator
SDK and on for the device SDK, so every existing simulator build and every
look-dev shot is exactly what it was.

Three failures account for nearly everything, and `make device` names each one
when it sees it:

- **"No profiles for com.mutaaf.fantasyedge"** — Xcode is not signed in.
  **Xcode > Settings > Accounts**, add the Apple ID that holds the membership.
- **"No signing certificate"** — the team is wrong, or its certificate is not on
  this Mac. Try `FE_TEAM=...`, or let Xcode create one from the Accounts pane.
- **The headset is not registered to the team** — build once from Xcode itself
  (Product > Run with the headset selected) and it registers the device.

---

## Reading the numbers

`make device-stats` launches with `-stadiumStats` and streams three kinds of
line. If streaming does not work from the terminal, open **Console.app**, pick
the headset in the left column, and filter on `stadium`.

Open the stadium and sit in a seat for ten seconds or so. The first frame-rate
report needs 300 frames, and the first 60 after a build are thrown away so the
build itself is not counted against the stadium.

```
[stadium-device] stadium running on device, budget 90.0 fps (11.11 ms), footprint at start 412 MB
[stadium-device] stadium device: 89.4 fps mean (11.19 ms), p95 12.90 ms, worst 24.10 ms,
                 18 of 300 frames over 11.1 ms, peak footprint 1204 MB
```

- **`device` or `simulator`** — every line says which machine produced it. A
  simulator line is not evidence about anything; the app says so itself when it
  starts there.
- **Mean fps** is the least interesting number. **p95 and the count over
  budget** are what a wearer feels: one frame in a hundred over 11.1 ms is a
  visible hitch in a headset, where the same figure on a monitor passes
  unnoticed.
- **Peak footprint** is what the system kills an app for. Watch it through a
  touchdown, when particles, cards and the crowd's surge are all live at once.

Alongside these, already there and unchanged:

```
[stadium-stats]  stadium: models 87, draw parts 100, triangles 227250, texture memory ~67 MB
[stadium-timing] stadium first tick after open: 6.214 s
[stadium] crowd dress composed in 2.41 s
```

The counts are true anywhere. The timings, on a headset, are the real ones.

---

## What to look for that a screenshot cannot show

Carry these in with you; they are the open questions the project has recorded
and could not answer:

- **Frame rate through a touchdown** — fireworks, the strobe, the crowd's surge
  and a trail in flight all at once. This is the budget's worst moment.
- **Does the crowd's dressing hitch the first open?** It takes about 2.4 s on a
  quiet Mac and is staged in by ring; whether that is visible as a pop is a
  device question.
- **The press box at true scale** — its dock draws at ×0.47 inside the glass,
  which has never been judged by an eye.
- **The recentre pinch** — whether the dock lands where you expect, and whether
  the up-to-7.5° bucketing is noticeable.
- **Do the beams pop on a seat change?** They are re-aimed per seat.
- **The clouds** — they carry no mipmaps; the question is whether they shimmer.

---

## Known first-run pitfalls

- **Nothing happens when you launch.** The app opens a window; the stadium is a
  separate immersive space you enter from it. Look for the window first.
- **The install hangs.** Wireless install over a slow network. Move both onto
  the same band, or plug the Mac into ethernet.
- **`devicectl` says the device is unavailable.** The headset is asleep or has
  locked. Put it on, unlock it, try again.
- **The app was killed on launch.** The simulator's own launcher was killed once
  during development for missing a 10-second scene-update deadline while the Mac
  was at load average 61 with several builds running. On a headset the same
  watchdog applies to us. If it happens on device with an idle Mac, that is a
  real defect in our startup, not a busy machine — say so, because the two look
  identical from the outside.
