// The scene spec, as fantasyedge/scene.py builds it and /api/scene serves it.
//
// This file declares shapes and checks that a payload is one this client can
// draw. It computes nothing about football: every number a renderer needs -
// apex, lane, duration, chip colour, which moment is active - arrives in the
// payload. Unknown fields are ignored, so the server can add to the spec
// without breaking a deployed client; a new MAJOR version is refused, because
// that is the server saying the old reading is wrong.

export const SUPPORTED_MAJOR = 1;

export interface Team {
  abbr: string;
  name: string;
  id: string;
  color: string;
  chip: string;
  chipText: string;
  hatch: boolean;
  score: number;
}

export interface Field {
  length: number;
  endZone: number;
  width: number;
  hashFromSideline: number;
  goalPostWidth: number;
  stripeEvery: number;
  numbersEvery: number;
  league: string;
  homeEndZone: [number, number];
  awayEndZone: [number, number];
}

export interface Arc {
  id: string;
  style: string;
  shape: string;
  type: string;
  fromX: number;
  toX: number;
  lane: number;
  apex: number;
  color: string;
  dash: [number, number] | null;
  seconds: number;
  duration: number;
  side: "home" | "away" | null;
  text: string;
  period: number | null;
  clock: string;
  down: number | null;
  distance: number | null;
}

export interface Drive {
  id: string;
  team: string;
  side: "home" | "away" | null;
  result: string;
  arcs: Arc[];
}

export interface Moment {
  kind: string;
  side: "home" | "away";
  team: string;
  points: number;
  playId: string;
  text: string;
  period: number | null;
  clock: string;
}

export interface Tier {
  name: string;
  inner: number;
  outer: number;
  rise: [number, number];
  color: string;
}

export interface Shape {
  type: string;
  exponent: number;
  halfLength: number;
  halfWidth: number;
}

export interface Bowl {
  shape: Shape;
  tiers: Tier[];
  concourse: { inner: number; outer: number; color: string };
  rimLights: { count: number; offset: number; height: number; side: string; color: string };
  crowd: { home: string; away: string; neutral: string; dark: string; awaySection: { side: string; fromX: number } };
  sectionTint: { side: "home" | "away" | null; color: string | null; dim: number };
}

export interface Seat { x: number; y: number; z: number }

export interface Presentation {
  tabletop: { metersPerYard: number; volume: [number, number, number]; floor: number; bowlTiers: string[] };
  stadium: { metersPerYard: number; seat: Seat; bowlTiers: string[] };
  horizon: { z: number; y0: number; y1: number };
  beaconHeight: number;
}

export interface WinProbability {
  side: "home" | "away";
  series: number[];
  horizon: { z: number; y0: number; y1: number; x0: number; x1: number };
}

export interface Status {
  state: "pre" | "in" | "post" | string;
  label: string;
  clock: string;
  period: number;
  homeScore: number;
  awayScore: number;
  possession: "home" | "away" | null;
  down: number | null;
  distance: number | null;
  downDistance: string;
  redZone: boolean;
}

export interface Motion {
  minSeconds: number;
  maxSeconds: number;
  referenceSpeed: number;
  floorSeconds: number;
  sectionDim: number;
  reduceMotion: string;
}

export interface ReplayControl {
  replay: true;
  loaded: boolean;
  event?: string;
  playing: boolean;
  speed: number;
  speeds: number[];
  gameSeconds?: number;
  length?: number;
  progress?: number;
  state?: string;
  label?: string;
  homeScore?: number;
  awayScore?: number;
  driveStart?: number | null;
}

export interface Scene {
  version: string;
  kind: string;
  league: string;
  event: string;
  source: "live" | "replay" | string;
  speed: number;
  field: Field;
  teams: { home: Team; away: Team };
  status: Status;
  ball: { x: number; y: number; z: number; beacon: { height: number; color: string } } | null;
  lasers: { kind: string; x: number; color: string }[];
  drives: Drive[];
  currentDrive: number | null;
  winProbability: WinProbability;
  moments: Moment[];
  activeMoment: Moment | null;
  bowl: Bowl;
  presentation: Presentation;
  palette: Record<string, string>;
  motion: Motion;
  replayControl?: ReplayControl;
}

export type Parsed = { ok: true; scene: Scene; minor: number } | { ok: false; error: string };

const REQUIRED: (keyof Scene)[] = [
  "version", "field", "teams", "status", "lasers", "drives", "winProbability",
  "moments", "bowl", "presentation", "palette", "motion",
];

export function parseVersion(v: unknown): { major: number; minor: number } | null {
  if (typeof v !== "string" && typeof v !== "number") return null;
  const m = /^(\d+)(?:\.(\d+))?/.exec(String(v));
  if (!m) return null;
  return { major: Number(m[1]), minor: Number(m[2] ?? 0) };
}

/** Accept a scene this client can draw, or say plainly why not. */
export function parseScene(payload: unknown): Parsed {
  if (!payload || typeof payload !== "object") {
    return { ok: false, error: "The scene is not a JSON object." };
  }
  const p = payload as Record<string, unknown>;
  const version = parseVersion(p.version);
  if (!version) {
    return { ok: false, error: `The scene has no readable version (got ${JSON.stringify(p.version)}).` };
  }
  if (version.major !== SUPPORTED_MAJOR) {
    return {
      ok: false,
      error: `This client draws scene version ${SUPPORTED_MAJOR}.x; the server sent ${p.version}. ` +
        (version.major > SUPPORTED_MAJOR ? "Update the web client." : "Update the server."),
    };
  }
  const missing = REQUIRED.filter((k) => p[k] === undefined);
  if (missing.length) {
    return { ok: false, error: `The scene is missing ${missing.join(", ")}.` };
  }
  const teams = p.teams as Record<string, unknown>;
  if (!teams?.home || !teams?.away) return { ok: false, error: "The scene has no teams." };
  if (!Array.isArray(p.drives)) return { ok: false, error: "The scene's drives are not a list." };
  return { ok: true, scene: payload as Scene, minor: version.minor };
}

/** The drive to draw: the one the scene names, else the last. The server
 * already chose it (a moment holds its own drive); this only indexes. */
export function shownDrive(s: Scene): Drive | null {
  if (s.currentDrive !== null && s.currentDrive >= 0 && s.currentDrive < s.drives.length) {
    return s.drives[s.currentDrive];
  }
  return s.drives.length ? s.drives[s.drives.length - 1] : null;
}

/** The moments the stadium stops for. The same list the visionOS client
 * uses; see the report - this belongs in the spec as a field. */
export const CELEBRATES = new Set(["touchdown", "fieldGoal", "safety"]);

export function celebrates(m: Moment | null): boolean {
  return !!m && CELEBRATES.has(m.kind);
}

export function team(s: Scene, side: "home" | "away" | null): Team | null {
  return side ? s.teams[side] : null;
}
