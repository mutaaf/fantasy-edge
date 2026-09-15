# Moments & Audio

The stadium's beats and its sound. Moments choreographs light, crowd and
particles; Audio places every sound where it comes from. Both play the same
schedule from `visual.moments.timeline`, so a whistle, a roar and a strobe
line up without either actor calling the other.

## What the scene now says (additive; ask the director to bump the minor version at merge)

| Field | What |
|---|---|
| `moments[].detail` | `interception`, `fumble`, `puntReturn`, `kickReturn`, `blocked`, or null. A pick-six is a touchdown with `detail: interception`. |
| `cues[]` | The game's other beats, in play order: `twoMinute`, `quarterEnd`, `halfEnd`, `regulationEnd`, `final`, and `redZone` (a drawn play that crosses the twenty without scoring). Each has `id`, `playId`, `side`, `detail`, `treatment`, `source` (`pa`, `bowl`, `standsHome`, `standsAway`), `period`, `clock`, `sequence`. |
| `activeCue` | The cue playing now: the newest event cue until the game clock moves past it, else a state cue, `thirdDown` for the home crowd while the visitors face third down. |

`moments` is unchanged in meaning: scores and turnovers. Cues are kept apart
on purpose, so no client that reads `moments` as scoring plays breaks.

`final` carries `detail` `homeWon`, `awayWon` or `tie`, and its `treatment`
is `finalHomeWon` and so on: the key into `visual.moments.cues`.

## The touchdown timeline (seconds after the moment arrives)

| Step | TD | FG | Safety | Turnover | Who |
|---|---|---|---|---|---|
| whistle | 0.0 | 0.0 | 0.0 | 0.0 | Audio, from the field |
| surge | 0.1 | 0.25 | 0.15 | 0.12 | Moments -> `shared.surge` (Crowd, Lighting wash); Audio roar/cheer/sting+groan from that side's seats |
| strobe | 0.2 for 2.6 s | 0.35 for 1.0 s | 0.3 for 1.0 s | - | Moments -> `shared.strobeUntil` (Lighting) |
| particles | 0.4 fireworks | 0.5 sparks | - | - | Moments, off the rim over the scoring end; Audio fireworks |
| banner | 0.3 | 0.4 | 0.4 | - | Broadcast/Experience, per the banner contract below |
| chime | 2.7 | 1.5 | 1.6 | - | Audio, from the press box |
| settle | 5.4 | 3.4 | 3.4 | 3.0 | everything has ended; within `motion.momentSeconds` (6.0) |

**Reduce motion.** Same beats, no movement: the section holds its wash and
the banks hold a steady glow for `reduceMotion.glowSeconds` (Lighting already
holds rather than flashes while reduce motion is on). No particles. The roar
swells `reduceMotion.swellDb` quieter instead of bursting.

## Audio graph

```
root (ReverbComponent .outside)
 +- crowdBed x5   spatial, round the lower bowl; nearest to the wearer +nearBoost dB
 +- clapBed       spatial, home stands across midfield
 +- murmurBed     spatial, press box (PA and concourse)
 +- windBed       ambient
 +- one-shots     spatial, created per sound and removed when it ends:
                  whistle (field), roar / cheer / sting (scoring or taking side's section),
                  groan (losing side's section), fireworks (rim), chime / horn (press box),
                  rumble / defenseSwell / finalCheer / exodus (home crowd)
```

- **Levels:** `gains[key] + masterGain` (+ `tabletop.gain` on the table).
- **Sources:** capped at `maxSources` = 12. Eight beds leave room for a whistle, a roar, fireworks and a chime at once. When over, a one-shot is dropped rather than a bed.
- **Tabletop:** 2 bed emitters, 22 dB down, rolloff 3.0, so it stays on the table.
- **Mute:** pauses the beds and blocks one-shots.

**Levels as made** (`assets/actors/audio/manifest.json`):
- **Beds:** -30 dBFS RMS.
- **Effects:** -21 dBFS RMS.
- **Peaks:** every file soft-limited under -1 dBFS; the loudest measured peak is -3.4 (sting).

Audio cannot be heard in verification. These are measured, not listened to.

## Hooks this actor needs from others (not implemented in their files)

1. **Composer (director): deliver cues.** Decode `cues` and `activeCue` in `SceneSpec`, add `StadiumEvent.cue(Cue)`, and dispatch `activeCue` once per `id`, the same as `activeMoment` per `playId`.
   - Hold a cue that arrives while a celebrating moment is active until `momentSeconds` has passed.
   - `MomentsActor.cue(treatment:side:id:_:)` and `AudioActor.cue(treatment:side:id:_:)` are ready for it.
   - Until then only `.redZoneEntered` reaches them. Both actors ignore a `redZone` cue within 8 s of that event, so the crossing never plays twice.
2. **Composer (director): decode `Moment.detail`.** Audio would use it to sting harder on a pick-six and to pick a fumble versus interception reaction.
3. **Crowd: posture hooks on the blackboard:**
   - `shared.stand: (side, until)` for third down and red zone;
   - `shared.sit: (side, until)` for the losing side at the final;
   - `shared.groan: (side, until)` for the side that lost the ball, a slump.

   Today Moments maps stand and rise to `shared.surge`, and sit and groan do nothing visible.
4. **Broadcast / Experience: the banner.** Draw it from `visual.moments.banner`:
   - **Size:** at least 34 degrees wide and 8 degrees tall at the eye, `heightYards` 24 over the scoring end zone, with a subtitle at 1.4 degrees.
   - **Timing:** in at `timeline.<kind>.banner` over `enterSeconds`, held `dwellSeconds`, out over `exitSeconds`.
   - **Kinds:** only `banner.kinds`.

   The integration-2 banner is a small chip; this is the contract that fixes it.
5. **Sideline: net sway on a field goal.** Read `activeMoment.kind == fieldGoal` and sway the kicking net over `timeline.fieldGoal.settle`.
6. **Broadcast: kick trail.** A field goal's arc already exists. Brighten it through `timeline.fieldGoal.particles`, when the sparks fire.

## Critique log

Shots are sequences from `tools/audio/moment_sequence.py` (the pick-six at 1x,
stills at offsets after play; the snap is about 3 s in).

### Baseline: `docs/lookdev/integration-2/s-td-moment.png`
- Banner, gold arc, strobe and the dimmed Vikings section all fire.
- **No fireworks anywhere in frame.** The old shells were `ParticleEmitterComponent.Presets.fireworks` scaled 22x on the nearest front banks, and stopped at 1.8 s, before the preset's rockets had burst.
- The banner is a chip.

### Iteration 1: `docs/actors/moments-audio/it1/`
Token-driven shells replace the preset. The emitters are built from `visual.moments.bursts`, in yards, on the stage.
- **t+4.9:** blue and gold shells open over the scoring end, in sync with the banner (which is up by t+4.2).
- **t+7.0:** the shells fall as fading streaks, which reads well.
- **Critique:** the cores blow out to solid white or gold balls, because the dense additive overlap saturates. The shells are small against the bowl, and read as puffballs rather than a show.

### Iteration 2: `docs/actors/moments-audio/it2/`
Each shell is now born on a small sphere's surface (`radius`), fast (24 yd/s) with drag (`damping` 2.2) so it opens into a ring, with fewer, smaller sparks and `streak` 4.
- **t+5.1:** three staggered shells in Bears blue, gold and white-gold, with radial streaks.
- **t+5.8:** open chrysanthemums fading.
- **t+6.8 / 8.5:** trails gone, the sky clean again before the banner leaves.
- **Critique:** the newest shell still flashes hot for its first frames, which is acceptable as the burst. The fourth shell is off-frame right from this seat, which is fine. The banner is still a chip (Broadcast's), and the strobe still fogs the stands (Lighting's cap).

### Audio: `docs/actors/moments-audio/spectro-fireworks-roar.jpg`
- **First pass:** every crowd sound carried flat energy to 16 kHz, which on a spectrogram reads as rain or hiss, not people. All crowd-class sounds now pass through `air()` (a 5.2 kHz roll-off standing in for distance and bodies), and the crowd body is tilted -4 dB per octave.
- **Fireworks:** held full level after its bangs, because a 45%-wet 3 s reverb kept it up. It is now enveloped to decay by 2.6 s.
- **Confirmed by measurement:** the whistle is a clean ~3 kHz line with its trill, and the horn a buzzing harmonic stack with tremolo.

**Unverified:**
- Anything heard: the simulator shots are muted, and no one listened.
- Reduce motion in the simulator.
- The tabletop miniature burst.
- Cues end to end, which wait on the composer hook.

### The way in and out: `visual.audio.experience`
Audio listens for `ExperienceEvents` and moves one envelope, in dB, over the whole mix. It is applied per frame, and only while it is moving.
- **Stadium build:** the beds start at `arrivalStartDb` (-24) and rise over `arriveSeconds` (2.5), so a launch straight into a seat is as gentle as the gate.
- **`gateOpening`:** the table's miniature swells `gateSwellDb` toward the stadium, starting `swellLead` before the space opens.
- **`arrived`:** the envelope settles to 0, and the wearer's section is re-picked.
- **`seatChanging`:** the mix ducks to `seatDuckDb` (-36) by the dark, holds `seatHoldSeconds`, and returns over `seatReturnSeconds` with the new seat's section boost.
- **`panelsYielded`:** `yieldDb`, 0 by default, so nothing changes.
- **`leaving`:** the mix fades to `silenceDb` over `leaveFadeSeconds`, then the beds pause.
- **Reduce motion:** every ramp becomes `reducedSeconds` (0.25).
- **One-shots:** they start at the envelope's current level, so nothing blares through a seat change.

**Unverified:** anything heard, and every transition live, since the simulator runs muted.

### Cues end to end: `docs/actors/moments-audio/cues/`
These are real scenes from `tools/audio/cue_frames.py`: the replay is parked before the play and played at 1x until the scene's own `activeCue` or `activeMoment` shows, with nothing forced.
- **`redzone.jpg` (401772510, 425 s), `thirddown.jpg` (680 s):** the Eagles crowd is on its feet. The clap reads as a stand in a still frame.
- **`turnover.jpg` (401772949, 2300 s, interception):** the Seahawks section that lost the ball, arms up and hands to heads. The ribbon reads TURNOVER.
- **`final.jpg` (3605 s, `finalHomeWon`):** the winners stand under Eagles-colour confetti over the bowl.
- **`fieldgoal-t2.0.jpg` (`lookdev --moment fieldGoal --times`):** the ribbon reads FIELD GOAL and the celebration fires. **The net sway is not visible:** the nets are behind the far posts at this distance, too small to see move. It needs a framing near the posts (Sideline).

### Crowd hooks: `docs/actors/moments-audio/crowd-hooks/`
`actor/crowd` @ `ac9e77f` is merged. The moment timelines call `stand` (the scorers, or the side that took the ball) and `groan` (the side that gave it up); `shared.surge` stays, for the Lighting wash. Cues call `clap` (third down), `stand` (red zone) and, at the final, `stand(.sections)` for the winners until the end and `sit(.sections)` for the losers. The scene serves those section lists on the final cue (`cues[].crowd`, from `fan_sections`). Durations live in `timeline.*.standSeconds` and `groanSeconds`, and in `cues.*.seconds`.
- Frames: the touchdown is the real pick-six; the others use `-crowdCue`, because the composer does not dispatch cues yet.
- `apple/verify_scene.swift`'s header command now also needs `Actors/Field/FieldArtSpec.swift` (after the Field merge). Director.
