// Primitives into mesh data: yards in, points and triangles out.
//
// A line-for-line port of apple/FantasyEdge/Sources/Stadium/SceneMath.swift
// and the mesh builders in StadiumMeshes.swift, with no Three.js in it, so the
// tests can count what a scene produces and a third renderer (Android) can
// port this file and nothing more. Nothing here decides anything about the
// game: apex, lane and colour come from the scene; this only turns them into
// geometry the same way the headset does.
//
// Space: midfield is the origin, x along the field (yards from the home goal
// line minus 50), y up, z toward the home sideline. A root scales yards to
// metres.

import type { Arc, Scene, Shape, Tier, WinProbability, Seat } from "./spec.ts";

export type Vec3 = [number, number, number];

export function local(x: number, y = 0, z = 0): Vec3 {
  return [x - 50, y, z];
}

/** A point on a play's arc: a parabola whose middle is exactly `arc.apex`. */
export function arcPoint(arc: Arc, t: number): Vec3 {
  const u = Math.max(0, Math.min(1, t));
  const x = arc.fromX + (arc.toX - arc.fromX) * u;
  return local(x, arc.apex * 4 * u * (1 - u), arc.lane);
}

export function arcSamples(arc: Arc, count = 24): Vec3[] {
  const n = Math.max(2, count);
  return Array.from({ length: n }, (_, i) => arcPoint(arc, i / (n - 1)));
}

const dist = (a: Vec3, b: Vec3) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);

/** The pieces a dashed arc draws; `dash` is [on, off] in yards along the arc. */
export function arcDashes(arc: Arc, count = 48): Vec3[][] {
  const pts = arcSamples(arc, count);
  const pattern = arc.dash;
  if (!pattern || pattern.length !== 2 || pattern[0] <= 0) return [pts];
  const pieces: Vec3[][] = [];
  let current: Vec3[] = [pts[0]];
  let travelled = 0;
  const on = pattern[0], period = pattern[0] + pattern[1];
  for (let i = 1; i < pts.length; i++) {
    travelled += dist(pts[i - 1], pts[i]);
    const drawing = travelled % period < on;
    if (drawing) current.push(pts[i]);
    else if (current.length > 1) { pieces.push(current); current = [pts[i]]; }
    else current = [pts[i]];
  }
  if (current.length > 1) pieces.push(current);
  return pieces;
}

export function bowlPoint(shape: Shape, m: number, t: number): { x: number; z: number } {
  const a = shape.halfLength + m, b = shape.halfWidth + m;
  const e = 2 / shape.exponent;
  const c = Math.cos(t), s = Math.sin(t);
  return {
    x: a * (c < 0 ? -1 : 1) * Math.pow(Math.abs(c), e),
    z: b * (s < 0 ? -1 : 1) * Math.pow(Math.abs(s), e),
  };
}

export function tierHeight(tier: Tier, m: number): number {
  const span = Math.max(1e-6, tier.outer - tier.inner);
  const f = Math.max(0, Math.min(1, (m - tier.inner) / span));
  return tier.rise[0] + (tier.rise[1] - tier.rise[0]) * f;
}

export function horizonPoints(wp: WinProbability): Vec3[] {
  const s = wp.series;
  if (s.length < 2) return [];
  const h = wp.horizon;
  return s.map((p, i) => local(h.x0 + ((h.x1 - h.x0) * i) / (s.length - 1), h.y0 + (h.y1 - h.y0) * p, h.z));
}

/** Where the root goes so the seat is at the viewer, eyes `eye` metres up. */
export function stadiumRoot(seat: Seat, metersPerYard: number, eye = 1.2): Vec3 {
  const at = local(seat.x, seat.y, seat.z).map((v) => v * metersPerYard) as Vec3;
  return [-at[0], eye - at[1], -at[2]];
}

/** "#RRGGBB" or "#RRGGBBAA" as 0..1 components and alpha. */
export function rgba(hex: string): [number, number, number, number] {
  let h = (hex ?? "").trim();
  if (h.startsWith("#")) h = h.slice(1);
  if (!/^[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$/.test(h)) return [0.5, 0.5, 0.5, 1];
  const n = (i: number) => parseInt(h.slice(i, i + 2), 16) / 255;
  return [n(0), n(2), n(4), h.length === 8 ? n(6) : 1];
}

// ───────────────────────────── the field ─────────────────────────────

export type Rect = [number, number, number, number]; // x0, x1, z0, z1

export interface FieldData {
  surround: Rect;
  stripesA: Rect[];
  stripesB: Rect[];
  homeEndZone: Rect;
  awayEndZone: Rect;
  heavy: Rect[];
  light: Rect[];
  hashes: Rect[];
  numbers: { label: string; x: number; z: number }[];
}

/** The field's flat pieces, with the headset's line weights and offsets. */
export function fieldData(s: Scene): FieldData {
  const f = s.field;
  const half = f.width / 2;
  const stripesA: Rect[] = [], stripesB: Rect[] = [];
  for (let x = 0, i = 0; x < f.length; x += f.stripeEvery, i++) {
    (i % 2 === 0 ? stripesB : stripesA).push([x, x + f.stripeEvery, -half, half]);
  }
  const heavy: Rect[] = [], light: Rect[] = [];
  for (let yard = 0; yard <= f.length; yard += f.stripeEvery) {
    if (yard % 10 === 0) heavy.push([yard - 0.22, yard + 0.22, -half, half]);
    else light.push([yard - 0.14, yard + 0.14, -half, half]);
  }
  const hash = half - f.hashFromSideline;
  const hashes: Rect[] = [];
  for (let y = 1; y < f.length; y++) {
    for (const z of [hash, -hash]) hashes.push([y - 0.06, y + 0.06, z - 0.35, z + 0.35]);
  }
  const numbers: FieldData["numbers"] = [];
  for (let n = f.numbersEvery; n < f.length; n += f.numbersEvery) {
    numbers.push({ label: String(n <= 50 ? n : f.length - n), x: n, z: half - 9 });
  }
  return {
    surround: [-f.endZone - 6, f.length + f.endZone + 6, -half - 6, half + 6],
    stripesA, stripesB,
    homeEndZone: [-f.endZone, 0, -half, half],
    awayEndZone: [f.length, f.length + f.endZone, -half, half],
    heavy, light, hashes, numbers,
  };
}

// ───────────────────────────── the bowl ─────────────────────────────

export interface MeshData { positions: number[]; indices: number[] }

/** A tier as a grid of rows between its inner and outer edge. Positions are
 * already in field-local space (the bowl's centre is midfield). */
export function tierMesh(tier: Tier, shape: Shape, segments = 96, rows = 5): MeshData {
  const positions: number[] = [], indices: number[] = [];
  for (let r = 0; r <= rows; r++) {
    const m = tier.inner + ((tier.outer - tier.inner) * r) / rows;
    const y = tierHeight(tier, m);
    for (let s = 0; s <= segments; s++) {
      const p = bowlPoint(shape, m, (s / segments) * 2 * Math.PI);
      positions.push(p.x, y, p.z);
    }
  }
  const cols = segments + 1;
  for (let r = 0; r < rows; r++) {
    for (let s = 0; s < segments; s++) {
      const a = r * cols + s, b = a + 1, c = a + cols, d = c + 1;
      indices.push(a, c, b, b, c, d);
    }
  }
  return { positions, indices };
}

/** The headset's seeded generator, bit for bit (a 64-bit LCG), so a web
 * crowd and a Vision Pro crowd for the same game are the same people. */
export class Rng {
  private s: bigint;
  constructor(seed = 12n) { this.s = seed; }
  next(): number {
    this.s = (this.s * 6364136223846793005n + 1442695040888963407n) & 0xFFFFFFFFFFFFFFFFn;
    return Number(this.s >> 11n) / 2 ** 53;
  }
}

/** Crowd quads bucketed by section (the sideline a tint lights) and colour. */
export function crowdData(s: Scene, tiers: Tier[], count: number): Map<string, Map<string, number[]>> {
  const rng = new Rng(12n);
  const shape = s.bowl.shape, crowd = s.bowl.crowd, pal = s.palette;
  const out = new Map<string, Map<string, number[]>>();
  if (!tiers.length) return out;
  for (let i = 0; i < count; i++) {
    const tier = tiers[Math.min(tiers.length - 1, Math.floor(rng.next() * tiers.length))];
    const m = tier.inner + 0.5 + (tier.outer - tier.inner - 1) * rng.next();
    const t = rng.next() * 2 * Math.PI;
    const { x, z } = bowlPoint(shape, m, t);
    const y = tierHeight(tier, m) + 0.4;
    const section = z >= 0 ? "home" : "away";
    const r = rng.next();
    const visitors = x > 40 && z < -10;
    const neutral = pal[crowd.neutral] ?? "#F4F1EA", dark = pal[crowd.dark] ?? "#2A2A2A";
    const colour = visitors ? (r < 0.8 ? crowd.away : neutral)
      : r < 0.62 ? crowd.home : r < 0.86 ? neutral : dark;
    const bySection = out.get(section) ?? new Map<string, number[]>();
    const list = bySection.get(colour) ?? [];
    list.push(x, y, z);
    bySection.set(colour, list);
    out.set(section, bySection);
  }
  return out;
}

/** Rim light positions on the far rim, as the headset places them. */
export function rimLightData(s: Scene, rim: number, height: number): Vec3[] {
  const lights = s.bowl.rimLights;
  const out: Vec3[] = [];
  for (let k = 0; k < lights.count; k++) {
    const t = (k * Math.PI) / Math.max(1, Math.floor(lights.count / 2)) + 0.3;
    const { x, z } = bowlPoint(s.bowl.shape, rim, t);
    if (lights.side === "far" && z > 12) continue;
    out.push([x, height, z]);
  }
  return out;
}

export type Mode = "tabletop" | "stadium";

export function tiersFor(s: Scene, mode: Mode): Tier[] {
  const names = mode === "tabletop" ? s.presentation.tabletop.bowlTiers : s.presentation.stadium.bowlTiers;
  return s.bowl.tiers.filter((t) => names.includes(t.name));
}

export const CROWD_COUNT: Record<Mode, number> = { tabletop: 1800, stadium: 6000 };

/** Everything a scene draws, counted. The contract the tests hold a port to. */
export function primitiveCounts(s: Scene, mode: Mode) {
  const f = fieldData(s);
  const tiers = tiersFor(s, mode);
  const crowd = crowdData(s, tiers, CROWD_COUNT[mode]);
  let people = 0;
  for (const sec of crowd.values()) for (const list of sec.values()) people += list.length / 3;
  const outer = tiers[tiers.length - 1];
  const rim = outer ? rimLightData(s, outer.outer + 1, outer.rise[1] + (mode === "tabletop" ? 4 : 9)) : [];
  const drive = s.currentDrive !== null ? s.drives[s.currentDrive] : s.drives[s.drives.length - 1];
  return {
    stripes: f.stripesA.length + f.stripesB.length,
    yardLines: f.heavy.length + f.light.length,
    hashes: f.hashes.length,
    numbers: f.numbers.length,
    tiers: tiers.length,
    crowd: people,
    rimLights: rim.length,
    arcs: drive ? drive.arcs.length : 0,
    lasers: s.lasers.length,
    beacon: s.ball ? 1 : 0,
    horizonPoints: horizonPoints(s.winProbability).length,
  };
}
