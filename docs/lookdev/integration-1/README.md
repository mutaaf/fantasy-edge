# Integration 1

- **Build:** `immersive/quality` @ 50cb09b, which merges `actor/lighting-sky` @ 3bccb72 onto 3e7b6e2.
- **Shots:** `python3 tools/lookdev.py --device <sim> --out .work/shots/integration-1 --settle 14`, with `s-*.png` at 1400 px.
- **Stats:** per-actor draw counts are in `stats.txt`.

## Art director review

**What changed.** Every seat now frames correctly. The seat-floor fix puts the eyes above the tread, and the head-turn shots keep the world level. The lit banks, the beams and the navy sky make the bowl read as a night game for the first time.

**Cross-actor issues to route:**

1. **Moments / harness: `td-moment` shows no banner or fireworks.** It was shot 14 s after a 6 s moment. `lookdev.py` now caps the touchdown settle at 7 s; re-shoot in integration-2. The scoring arc is also not visible from this seat (Broadcast).
2. **Broadcast (Wave 2): the WIN PROBABILITY horizon and its CHI / MIN / WIN PROBABILITY labels float in the sky.**
   - In `lights-haze`, `bowl-wide` and `sky-dome` they read as debris, not as a graphic.
   - In `td-moment` the horizon is a jagged scribble across the top of the frame.
   - It needs a panel or a ribbon behind it, anchored to the far stands, and it must not cross the sky.
3. **Crowd: near fans are pixelated cut-outs.**
   - They have blocky edges and flat colour (`crowd-closeup` and `td-moment` foreground, `sideline-props` bottom edge).
   - At distance the mass reads, but banding from the two-colour mottle is visible across the upper deck in `bowl-wide`.
4. **Bowl: the foreground ledge in front of the seat.**
   - It is a flat grey tread with no seat rows in `crowd-closeup` and `td-moment`.
   - It is a black slab under the goal post in `sideline-props`.
   - The press box is a flat beige band with no glazing depth (`field-level`, `bowl-wide`).
5. **Lighting: beams over the stands.**
   - They wash the far upper deck to grey fog (`bowl-wide`, `td-moment` centre) and flatten club colour.
   - Lower the beam opacity where beams cross the stands, or stop them at the rim.
   - The banks hang on bare stilts above the rim; see agreement below.

**Do seats, crowd and rim lights agree?** Not yet, and only partly checkable: `actor/bowl`'s seating and mounts are not merged.
- On this build the banks stand at `upper.outer + beyondOuter` on thin poles with no headframe, above a back wall they don't touch.
- Bowl's `mounts.rim` (16 headframes on a parapet at offset 70.6, top 47.6) should replace the poles, and Lighting should hang its lamps on those mounts.
- The crowd still fills rows from `SceneMath.row`, not `bowl.seating`. Crowd must switch to `SceneMath.seat` when Bowl lands, or fans will float off the modelled seats.
- Check again at integration-2, after the Bowl and Crowd merges.

**Budget.**
- Stadium: about 112 draw parts and 210k triangles.
- Over budget: Field at 26 parts (budget 12), Crowd at 129k triangles (budget 120k).
- Lighting: 11 parts and 9.3k triangles, within budget.
