// The contract a web renderer is held to, against scenes the real API code
// produced for a real replayed game (Vikings at Bears, 2025: a pick-six).
// Fixtures come from tools/fixtures.py; never edit them by hand.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { parseScene, parseVersion, shownDrive, celebrates, type Scene } from "../src/spec.ts";
import {
  arcPoint, arcDashes, bowlPoint, horizonPoints, primitiveCounts, Rng, stadiumRoot, local, rgba,
} from "../src/geometry.ts";
import { PlayMotion } from "../src/motion.ts";

const raw = (name: string): unknown =>
  JSON.parse(readFileSync(new URL(`./fixtures/${name}.json`, import.meta.url), "utf8"));

function scene(name: string): Scene {
  const p = parseScene(raw(`scene-${name}`));
  if (!p.ok) throw new Error(p.error);
  return p.scene;
}

// ── parsing and version gating ──

test("every recorded scene parses as version 1", () => {
  for (const name of ["kickoff", "midgame", "pick-six", "final"]) {
    const p = parseScene(raw(`scene-${name}`));
    assert.ok(p.ok, name);
    if (p.ok) assert.equal(parseVersion(p.scene.version)?.major, 1);
  }
});

test("a minor version bump and unknown fields are drawn, not refused", () => {
  const s = raw("scene-pick-six") as Record<string, unknown>;
  const p = parseScene({ ...s, version: "1.7", somethingNew: { a: 1 }, teams: { ...(s.teams as object), extra: true } });
  assert.ok(p.ok);
  if (p.ok) assert.equal(p.minor, 7);
});

test("a new major version is refused with a message saying which side to update", () => {
  const s = raw("scene-pick-six") as Record<string, unknown>;
  const p = parseScene({ ...s, version: "2.0" });
  assert.equal(p.ok, false);
  if (!p.ok) {
    assert.match(p.error, /1\.x/);
    assert.match(p.error, /2\.0/);
    assert.match(p.error, /Update the web client/);
  }
});

test("payloads that are not a scene are refused plainly", () => {
  assert.equal(parseScene(null).ok, false);
  assert.equal(parseScene({ kind: "football-scene" }).ok, false);
  const s = raw("scene-pick-six") as Record<string, unknown>;
  const { drives: _drop, ...noDrives } = s;
  const p = parseScene(noDrives);
  assert.equal(p.ok, false);
  if (!p.ok) assert.match(p.error, /drives/);
});

// ── primitive counts: what a port must draw ──

test("the stadium draws the field, both tiers, the crowd, the rim, the drive and the markers", () => {
  const s = scene("pick-six");
  const c = primitiveCounts(s, "stadium");
  assert.equal(c.stripes, 20);
  assert.equal(c.yardLines, 21);
  assert.equal(c.hashes, 198);
  assert.equal(c.numbers, 9);
  assert.equal(c.tiers, 2);
  assert.equal(c.crowd, 6000);
  // Ten lamps around the rim, of which the five on the far side are drawn
  // (checked independently in Python against the same superellipse).
  assert.equal(c.rimLights, 5);
  assert.equal(c.arcs, shownDrive(s)!.arcs.length);
  assert.ok(c.arcs > 0);
  assert.equal(c.lasers, 2);
  assert.equal(c.beacon, 1);
  assert.equal(c.horizonPoints, s.winProbability.series.length);
});

test("the tabletop draws only the lower bowl, with a lighter crowd", () => {
  const c = primitiveCounts(scene("pick-six"), "tabletop");
  assert.equal(c.tiers, 1);
  assert.equal(c.crowd, 1800);
});

test("a final has no ball, beacon or lasers to draw", () => {
  const s = scene("final");
  const c = primitiveCounts(s, "stadium");
  assert.equal(s.status.state, "post");
  assert.equal(c.beacon, 0);
  assert.equal(c.lasers, 0);
});

// ── geometry follows the scene's numbers exactly ──

test("every arc peaks at the apex the scene states, at the snap and end spots, in its lane", () => {
  const s = scene("final");
  let n = 0;
  for (const d of s.drives) {
    for (const a of d.arcs) {
      const mid = arcPoint(a, 0.5), start = arcPoint(a, 0), end = arcPoint(a, 1);
      assert.ok(Math.abs(mid[1] - a.apex) < 1e-9, a.id);
      assert.deepEqual(start, [a.fromX - 50, 0, a.lane]);
      assert.deepEqual(end, [a.toX - 50, 0, a.lane]);
      n++;
    }
  }
  assert.ok(n > 100);
});

test("an incomplete pass is drawn dashed and a run solid", () => {
  const arcs = scene("final").drives.flatMap((d) => d.arcs);
  const incomplete = arcs.find((a) => a.style === "incomplete")!;
  const run = arcs.find((a) => a.style === "run" && Math.abs(a.toX - a.fromX) > 3)!;
  assert.ok(arcDashes(incomplete).length > 1);
  assert.equal(arcDashes(run).length, 1);
});

test("the bowl, horizon and seat land where the headset puts them", () => {
  const s = scene("pick-six");
  const p = bowlPoint(s.bowl.shape, 6, 0);
  assert.ok(Math.abs(p.x - (s.bowl.shape.halfLength + 6)) < 1e-9 && Math.abs(p.z) < 1e-9);
  const h = horizonPoints(s.winProbability), hz = s.winProbability.horizon;
  assert.equal(h[0][0], hz.x0 - 50);
  assert.equal(h[h.length - 1][0], hz.x1 - 50);
  assert.ok(h.every(([, y]) => y >= hz.y0 - 1e-9 && y <= hz.y1 + 1e-9));
  const st = s.presentation.stadium;
  const root = stadiumRoot(st.seat, st.metersPerYard);
  const seat = local(st.seat.x, st.seat.y, st.seat.z).map((v, i) => v * st.metersPerYard + root[i]);
  assert.deepEqual(seat.map((v) => Math.round(v * 1e9) / 1e9), [0, 1.2, 0]);
});

test("the crowd generator is the headset's, bit for bit", () => {
  // Values from the same 64-bit LCG evaluated in Python.
  const r = new Rng(12n);
  assert.equal(r.next(), 0.2182148468113263);
  assert.equal(r.next(), 0.994202951339924);
  assert.equal(r.next(), 0.12175617868359867);
});

test("palette colours with alpha parse", () => {
  assert.deepEqual(rgba("#FF000080").map((v) => Math.round(v * 100) / 100), [1, 0, 0, 0.5]);
  assert.deepEqual(rgba("nonsense"), [0.5, 0.5, 0.5, 1]);
});

// ── moments ──

test("the pick-six lights the Bears' section and nothing else does", () => {
  const s = scene("pick-six");
  assert.equal(s.activeMoment?.kind, "touchdown");
  assert.equal(s.activeMoment?.side, "home");
  assert.ok(celebrates(s.activeMoment));
  assert.equal(s.bowl.sectionTint.side, "home");
  assert.equal(scene("midgame").bowl.sectionTint.side, null);
  assert.equal(celebrates(scene("midgame").activeMoment), false);
});

test("the scene says it is a replay, so the client can say so", () => {
  const s = scene("pick-six");
  assert.equal(s.source, "replay");
  assert.equal(s.replayControl?.replay, true);
  assert.ok(s.replayControl?.speeds.includes(60));
});

// ── motion ──

test("the first drive is history; later plays queue and fly for the scene's duration", () => {
  const s = scene("midgame");
  const drive = shownDrive(s)!;
  const m = new PlayMotion();
  assert.deepEqual(m.arrive({ ...drive, arcs: drive.arcs.slice(0, 2) }, true), []);
  const fresh = m.arrive(drive, false);
  assert.equal(fresh.length, drive.arcs.length - 2);
  const first = m.next(false, s.motion.floorSeconds)!;
  assert.equal(first.arc.id, drive.arcs[2].id);
  assert.ok(first.seconds >= s.motion.floorSeconds);
  assert.equal(m.next(true, s.motion.floorSeconds)?.seconds ?? 0, 0);
});

test("a backlog of more than three plays halves the flight", () => {
  const arcs = scene("final").drives.flatMap((d) => d.arcs).slice(0, 6);
  const m = new PlayMotion();
  m.arrive({ id: "d", team: "", side: null, result: "", arcs }, false);
  const flown = m.next(false, 0)!;
  assert.equal(flown.seconds, arcs[0].duration * 0.5);
});
