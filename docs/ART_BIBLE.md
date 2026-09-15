# The stadium art bible

The stadium and the tabletop are drawn by ten actors. Each is owned by one
specialist at a time. This page is the bar each actor is held to, the budget
it spends, the shots it is judged in, and the rules that let ten people work
on one stadium without touching each other's code.

The director (the Immersive Quality Lead) owns this page, the composer
(`StadiumRenderer.swift`), the protocol (`Actors/StadiumActor.swift`),
`SceneSpec.swift`, `SceneLook.swift`'s top-level `Look`, and every merge.

## The look

**A night game, seen the way a premium broadcast wishes it could show it.**

- **Night, not black.** A deep blue sky with stars, and a warm light dome over
  the rim where the stadium's own light hangs in the air. Nothing reads as a
  void.
- **The stadium-lights identity.** The rim light banks are the one ornament
  the whole product carries, from the app icon to the Saturday Wall. Here they
  are real. They burn, they bloom, their haze falls toward the field, and they
  are what strobes when something happens.
- **The field is the brightest thing in the bowl.** Floodlit grass with a
  mowing stripe, worn paint, and a sheen at grazing angles. The stands sit a
  stop darker, the sky two.
- **Colour is the clubs'.** Crowds, end zones and benches wear the chips from
  the scene, never invented colours. Broadcast graphics - the lines, the
  trails, the horizon - are light, not paint.
- **Nothing is invented that the feed does not know.** No players: the feed
  has no tracking. The ball, the lines and the drive are drawn exactly where
  the scene puts them.
- **Comfort first.** The world moves; the wearer never does. Panels sit
  within ±30° and no lower than 33° below the eye. Motion has a reduce-motion
  equivalent, always.

References are descriptions, never copies. Take the quality bar from current
Apple immersive sports and modern console football presentation. Never copy
anyone's stadium, branding, crowd art or broadcast package.

## Rules between actors

1. **Stay in your folders.** An actor's specialist writes only to:
   - `apple/FantasyEdge/Sources/Stadium/Actors/<Actor>/`
   - `assets/actors/<actor>/`
   - `tools/blender/<actor>/`
   - their own `visual.<actor>` block in `design/tokens.json`
   - their own struct in `SceneLook.swift` (the `<Actor>Look` struct and the
     structs nested under it)

   Spec geometry (`scene.py`) changes go through the director.
2. **Actors never call each other.** What one needs from another passes
   through `StadiumShared`, the blackboard. It holds bank positions, the press
   box, the stands behind each end, the wearer's eyes, strobe and surge
   requests, and mute. A new blackboard field is a director change.
3. **Every renderer-facing number lives in `visual.<actor>`.** None may exist
   only in Swift. `tests/test_replay_scene.py` fails if `SceneLook.swift`
   reads a key the tokens do not carry. The web and Android ports read the
   same numbers.
4. **Assets are portable.**
   - **Textures:** PNG or KTX2.
   - **Light probes:** HDR or EXR.
   - **Audio:** WAV.
   - **Models:** authored in Blender and exported twice, as `.usdz` for the
     headset and a `.glb` beside it for Three.js and Filament. A test fails
     on a model without its twin.
   - **Licences:** CC0 or original only, each recorded in `assets/LICENSES.md`.
   - **Trademarks:** none. Club names and colours come from the scene at
     runtime.
5. **Gates, before any merge request:**
   - `make test` passes.
   - `apple/verify_scene.swift` passes.
   - `apple/contrast_check.py` passes.
   - `xcodebuild` succeeds with no new warnings.
   - Every shot for your actor is re-shot, with before and after paths in
     `docs/IMMERSIVE_QUALITY.md`.

## The model pipeline

```
tools/blender/<actor>/build.py      a Blender script: builds or opens the .blend,
                                     exports <name>.usdz and <name>.glb
        │  blender --background --python tools/blender/<actor>/build.py
        ▼
assets/actors/<actor>/<name>.usdz    headset
assets/actors/<actor>/<name>.glb     web (Three.js) and Android (Filament)
assets/actors/<actor>/*.png|ktx2     textures the models reference
        │  named in design/tokens.json → visual.<actor>.models.<id> = "actors/<actor>/<name>.usdz"
        ▼
StadiumAssets.prepare                loads every declared .usdz once, asynchronously
        │
        ▼
c.assets.model("<actor>.<id>")       a fresh clone for the actor to place and scale
```

- **The app bundle.** `apple/generate_project.py` bundles `assets/` unchanged
  as a folder reference. No Reality Composer Pro package and no
  `realitytool` step: USDZ loads directly with `Entity(contentsOf:)`.
- **Shader Graph.** Materials authored as `.usda` Shader Graph can be loaded
  with `ShaderGraphMaterial(named:from:in:)`. If you add one, add its portable
  fallback parameters to your `visual` section, so the ports have something to
  draw.
- **Units.** Author in metres, at real size. Actors draw in yards under a
  root scaled to metres, so scale a loaded model by `1 / 0.9144` in the
  stadium, and by the tabletop's `metersPerYard` in reverse.
- **Procedural assets.** `tools/make_assets.py` writes into
  `assets/generated/<actor>/`, never into `assets/actors/`. A specialist
  replaces a generated asset by pointing their `visual.<actor>.assets` entry
  at their own file.

## Budget

The whole stadium targets **90 fps on Vision Pro in full immersion**. A share
is a ceiling, not an allowance to fill. Measure with `-stadiumStats`, which
logs per-actor draw parts and triangles. `tools/lookdev.py` writes the
numbers to `stats.txt`.

| Actor | Triangles | Draw parts | Texture MB | Other |
|---|---:|---:|---:|---|
| Field | 3k | 12 | 40 | 1.1k measured at integration-3 |
| Sideline | 22k | 15 | 20 | 20.6k measured |
| Bowl | 60k | 20 | 50 | ~57k measured |
| Crowd | 150k | 45 | 60 | 52,039 seats; LOD2 pose-mesh ring near club seats capped in `visual.crowd.rings`; fans animate by group, never per fan on the CPU |
| Lighting | 10k | 20 | 20 | ≤ 4 spot lights, ≤ 1 shadow caster |
| Sky | 5k | 3 | 30 | |
| Broadcast | 30k | 25 | 20 | |
| Moments | 2k | 10 | 10 | ≤ 4,000 live particles |
| Audio | – | – | 40 (audio) | ≤ 16 voices |
| Experience | 5k | 10 | 10 | attachments excluded |
| **Stadium total** | **287k** | **160** | **300** | |
| **Tabletop total** | **80k** | **110** | shared | |

**Rebalanced at integration-3:** Crowd rises from 120k to 150k triangles, because Bowl now seats 52,039 fans, not 32k, and fans 5–12 yd from a club seat need real meshes, not magnified cards. The extra 30k is measured slack from Field (20k → 3k), Bowl (70k → 60k) and Sideline (25k → 22k). The total stays at 287k. Any actor that needs its slack back goes through the director.

**Measured at the actor split, iteration 4 of the look pass:**
- **Stadium:** 113 draw parts, 205k triangles, 32k fans, about 67 MB of
  textures.
- **Tabletop:** 92 parts, 50k triangles.

The simulator cannot measure frame time honestly. Frame budget is verified
on device.

## Actors

Each entry lists what the actor owns, its bar, its reference, and the shots
that judge it.

### Field — `Actors/Field/`, `visual.field`

- **Owns:** turf, mowing stripe, surround, painted lines and hashes, yard
  numbers, end-zone paint and lettering.
- **Bar:**
  - From the club seat it reads as floodlit natural grass, not a green plane.
  - The stripe changes with viewing angle as well as colour.
  - Paint is worn where it should be, with blades through it.
  - Numbers have the right font weight and scale.
  - No tiling is visible from any seat.
  - Up close at field level, the grass has blades, not a blurred photo.
- **Reference:** a professionally kept natural-grass field under LED
  floodlights at night: saturated but not neon, a darker line at the stripe
  edges, crisp white paint.
- **Shots:** `field-level`, `bowl-wide`, `redzone-trails`.

### Sideline — `Actors/Sideline/`, `field.props`, `visual.sideline`

- **Owns:** goal posts, pads, pylons, benches, the LED boards on the wall.
- **Bar:**
  - The goal posts have a gooseneck, correct proportions, painted metal and a
    soft shadow on the grass.
  - Benches read as benches, with team-area detail.
  - The boards glow like LED, with a subtle pixel grid up close and no
    aliasing at distance.
  - Nothing is branded.
- **Reference:** an NFL and college sideline at night: the yellow slingshot
  posts, orange pylons, benches under the lights, ribbon-style boards along the
  wall.
- **Shots:** `sideline-props`, `field-level`.

### Bowl — `Actors/Bowl/`, `bowl`, `visual.bowl`

- **Owns:** stepped tiers, seats, aisles and stairs, rails, the wall cap,
  concourse, fascia, press box, tunnels, the back wall.
- **Bar:**
  - The bowl reads as seating architecture at every distance: seat backs and
    rows visible, aisles with steps, handrails, vomitories.
  - The upper deck overhangs with an underside.
  - The press box has depth and interior light.
  - The concrete has weathering.
  - Nothing reads as a flat grey wall from any seat.
- **Reference:** a modern open-air football bowl: two decks with a club
  level, precast concrete, a single seat colour, a glazed press box on one
  sideline.
- **Shots:** `bowl-wide`, `crowd-closeup`, `sideline-props`.

### Crowd — `Actors/Crowd/`, `bowl.crowd`, `bowl.sectionTint`, `visual.crowd`

- **Owns:** every fan, their clothing in the clubs' colours, their idle
  motion, the wave, and the section surge on a score.
- **Bar:**
  - **At distance:** a living, mottled mass in club colours, with light and
    shade.
  - **At 3–10 m** (`crowd-closeup`): individuals, not sprites. Silhouettes
    have shoulders, heads, variety of build and posture, and some hats and
    scarves. Nobody is duplicated side by side.
  - **Motion:** idle motion is visible but calm. A touchdown makes the
    scoring section rise in a way you feel.
  - **Faces:** the rows in front show backs of heads, never faces turned to
    the wearer.
  - **Comfort:** no fan stands in the wearer's seat.
- **Reference:** a sold-out night game from the lower bowl: team colour
  dominant, flecks of white and dark, arms up on a big play.
- **Shots:** `crowd-closeup`, `bowl-wide`, `td-moment`.

### Lighting — `Actors/Lighting/`, `bowl.rimLights`, `visual.lighting`

- **Owns:** the image-based light probe, rim light banks (structure, lamp
  faces, bloom, haze), floodlights and shadows, and the strobe.
- **Bar:**
  - The banks read as stadium LED arrays that burn, with bloom that sits
    behind the lamp.
  - The haze is visible against the sky but never fogs the field.
  - The field is lit from the banks' direction, with soft multiple shadows
    under the goal posts.
  - The stands pick up spill.
  - The strobe is punchy and brief.
- **Reference:** LED stadium lighting at night: cool-white, intense
  point-sources with a slight star glare, visible beams in humid air.
- **Shots:** `lights-haze`, `bowl-wide`, `td-moment`.

### Sky — `Actors/Sky/`, `visual.sky`

- **Owns:** the star dome, the atmosphere, and the light dome above the rim.
- **Bar:**
  - Stars are points, never discs, and thin toward the horizon.
  - A warm sodium dome rises from the rim and fades up into deep blue.
  - The horizon has a faint city glow.
  - There is no banding and no visible seam.
- **Reference:** a clear night over a city stadium.
- **Shots:** `sky-dome`, `lights-haze`, `bowl-wide`.

### Broadcast — `Actors/Broadcast/`, scene drives, ball, lasers and win probability, `visual.broadcast`

- **Owns:** the ball and its flight, the drive trails, the scrimmage and
  line-to-gain lines, the beacon, the chains, the ribbon board, and the
  win-probability horizon.
- **Bar:**
  - Trails are thin, luminous and fading, like a broadcast ball-flight
    graphic. The current play is bright; earlier plays are ghosted.
  - The first-down line looks painted on the grass by light, with no
    z-fighting.
  - The ball is findable at 50 yards without being a cartoon.
  - The horizon tells you who is winning at a glance and is labelled.
  - The ribbon board is crisp and readable from the far side.
- **Reference:** the best modern broadcast football graphics packages, in
  spirit, not in copy.
- **Shots:** `redzone-trails`, `td-moment`, `tabletop`.

### Moments — `Actors/Moments/`, scene moments, `visual.moments`

- **Owns:** the choreography of a touchdown, field goal, safety and turnover:
  fireworks, the strobe and surge requests, and their timing.
- **Bar:**
  - A touchdown is an event: fireworks off the rim at the scoring end, the
    banks strobing, the section rising, all inside `motion.momentSeconds`.
  - A field goal is smaller.
  - A turnover is sound only.
  - Reduce motion keeps the tint and the sound and drops everything that
    moves.
- **Shots:** `td-moment`.

### Audio — `Actors/Audio/`, `visual.audio`

- **Owns:** the crowd bed, roar, groan, PA chime, their placement in the
  bowl, and mute.
- **Bar:**
  - The bed breathes, never loops audibly, and sits under commentary level.
  - The roar comes from the scoring side's seats.
  - Everything respects mute instantly.
  - CC0 or original only.
- **Shots:** `td-moment`. Audio can't be screenshotted; record a note of what
  you heard in `docs/IMMERSIVE_QUALITY.md`.

### Experience — `Actors/Experience/`, `presentation`, `visual.experience`

- **Owns:** seat placement and the seat change, the tabletop baseplate and
  cutaway, the immersion ramp, the in-stadium controls, `StadiumShots`, and
  `StadiumViews`.
- **Bar:**
  - A seat change fades, turns the world and never moves the wearer.
  - The tabletop is a jewel-like model on a lit plinth that you look into.
  - Controls are glanceable, within reach and within the comfort limits.
  - Entering and leaving the stadium restores exactly what you had open.
- **Shots:** `tabletop`, `field-level`.

## Shots

```
python3 tools/lookdev.py --device <your simulator udid> --out .work/shots/<actor>-<iteration> [--only <names>]
```

| Shot | Seat and view | Replay position | Judges |
|---|---|---|---|
| `tabletop` | the table model in the room | red-zone snap | Experience, Broadcast, Crowd at LOD |
| `bowl-wide` | upper deck, midfield, slightly down | a normal snap | Bowl, Crowd, Lighting, Sky |
| `field-level` | home sideline, field level | red-zone snap | Field, Sideline, Experience |
| `crowd-closeup` | club seat, turned 62° toward the side stands | a normal snap | Crowd, Bowl |
| `lights-haze` | club seat, looking up at the far rim | a normal snap | Lighting, Sky |
| `sky-dome` | club seat, looking high | a normal snap | Sky |
| `td-moment` | club seat, turned toward the scoring end | the Bears pick-six at 1x | Moments, Crowd, Lighting, Broadcast, Audio |
| `redzone-trails` | club seat, turned toward the red zone | red-zone snap | Broadcast, Field |
| `sideline-props` | behind the home end zone | a normal snap | Sideline, Field |

The app understands the same names on its own (`-shot crowd-closeup`). The
harness also positions the replay. A test keeps the harness, the app and
this table in step.

## Critique rubric

Score every shot for your actor, 1–5 on each line, in
`docs/IMMERSIVE_QUALITY.md`. A merge needs no line below 3 on your shots, and
no line on anyone else's shots lower than it was before your change.

1. **Read.** Does it read as the real thing at a glance, from this seat?
2. **Light.** Is it lit by the stadium? Is there value structure, and is the
   field the brightest thing?
3. **Material.** Does each surface look like what it is: grass, paint,
   concrete, metal, fabric, light?
4. **Scale.** Does it feel the right size from here? Are there cues (seats,
   rails, people) that give it away?
5. **Life.** Does anything move that should, and does nothing move that
   shouldn't?
6. **Clarity.** Is the game (ball, lines, drive, score) instantly legible
   over everything else?
7. **Comfort.** Within the placement limits? No flicker, strobe too long, or
   world motion the wearer didn't ask for?
8. **Cost.** Within your budget line, measured with `-stadiumStats`?

Write one sentence of "worst thing left" per shot. The next iteration starts
there.
