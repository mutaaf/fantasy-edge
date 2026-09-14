// Draws a Scene with Three.js, at tabletop or stadium scale.
//
// The same shape as StadiumRenderer.swift, for the same reasons:
//   * the field, bowl, crowd and rim are built once per pair of teams;
//   * the ball, beacon and lasers are made once and moved, never rebuilt;
//   * a drive's arcs are laid down as the ball finishes flying them.
// It holds no network code and decides nothing about the game.

import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

import type { Arc, Scene } from "./spec.ts";
import { shownDrive } from "./spec.ts";
import {
  arcDashes, arcPoint, arcSamples, bowlPoint, crowdData, fieldData, horizonPoints, local, rimLightData,
  rgba, stadiumRoot, tierHeight, tierMesh, tiersFor, CROWD_COUNT, type Mode, type Rect, type Vec3,
} from "./geometry.ts";
import { PlayMotion } from "./motion.ts";

const FALLBACK = "#808080";

function colour(s: Scene, key: string, fallback = FALLBACK): { c: THREE.Color; a: number } {
  const hex = key.startsWith("#") ? key : s.palette[key] ?? fallback;
  const [r, g, b, a] = rgba(hex);
  return { c: new THREE.Color().setRGB(r, g, b, THREE.SRGBColorSpace), a };
}

function basic(s: Scene, key: string, opts: { opacity?: number; additive?: boolean; fallback?: string } = {}) {
  const { c, a } = colour(s, key, opts.fallback);
  const opacity = opts.opacity ?? a;
  return new THREE.MeshBasicMaterial({
    color: c, side: THREE.DoubleSide,
    transparent: opacity < 0.999 || !!opts.additive, opacity,
    blending: opts.additive ? THREE.AdditiveBlending : THREE.NormalBlending,
    depthWrite: !(opts.additive || opacity < 0.999),
  });
}

function plates(rects: Rect[], y: number): THREE.BufferGeometry {
  const pos: number[] = [], idx: number[] = [];
  for (const [x0, x1, z0, z1] of rects) {
    const b = pos.length / 3;
    for (const [x, z] of [[x0, z0], [x1, z0], [x1, z1], [x0, z1]]) pos.push(...local(x, y, z));
    idx.push(b, b + 1, b + 2, b, b + 2, b + 3);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setIndex(idx);
  return g;
}

function tube(points: Vec3[], radius: number): THREE.BufferGeometry | null {
  if (points.length < 2) return null;
  const curve = new THREE.CatmullRomCurve3(points.map((p) => new THREE.Vector3(...p)));
  return new THREE.TubeGeometry(curve, Math.max(8, points.length * 2), radius, 8, false);
}

function glowTexture(): THREE.Texture {
  const size = 128;
  const cv = document.createElement("canvas");
  cv.width = cv.height = size;
  const g = cv.getContext("2d")!;
  const grad = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  grad.addColorStop(0, "rgba(255,255,255,1)");
  grad.addColorStop(0.22, "rgba(255,255,255,0.55)");
  grad.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, size, size);
  const t = new THREE.CanvasTexture(cv);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

function discTexture(): THREE.Texture {
  const size = 32;
  const cv = document.createElement("canvas");
  cv.width = cv.height = size;
  const g = cv.getContext("2d")!;
  g.fillStyle = "#FFFFFF";
  g.beginPath();
  g.arc(size / 2, size / 2, size / 2 - 2, 0, Math.PI * 2);
  g.fill();
  return new THREE.CanvasTexture(cv);
}

function beamTexture(): THREE.Texture {
  const cv = document.createElement("canvas");
  cv.width = 4; cv.height = 128;
  const g = cv.getContext("2d")!;
  const grad = g.createLinearGradient(0, 128, 0, 0);
  grad.addColorStop(0, "rgba(255,255,255,0.95)");
  grad.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 4, 128);
  return new THREE.CanvasTexture(cv);
}

function labelTexture(text: string, font: string, color: string, w = 256, h = 128): THREE.Texture {
  const cv = document.createElement("canvas");
  cv.width = w; cv.height = h;
  const g = cv.getContext("2d")!;
  g.fillStyle = color;
  g.font = font;
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.fillText(text, w / 2, h / 2);
  const t = new THREE.CanvasTexture(cv);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  return t;
}

function skyMaterial(s: Scene): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    side: THREE.BackSide, depthWrite: false,
    uniforms: {
      top: { value: colour(s, "sky.top", "#03050A").c },
      horizon: { value: colour(s, "sky.horizon", "#1A2436").c },
    },
    vertexShader: "varying vec3 vP; void main(){ vP = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }",
    fragmentShader: "uniform vec3 top; uniform vec3 horizon; varying vec3 vP; void main(){ float h = clamp(vP.y * 2.2, 0.0, 1.0); gl_FragColor = vec4(mix(horizon, top, pow(h, 0.6)), 1.0); #include <colorspace_fragment> }",
  });
}

interface Flight { arc: Arc; start: number; seconds: number }

export class StadiumView {
  readonly renderer: THREE.WebGLRenderer;
  readonly three = new THREE.Scene();
  readonly camera = new THREE.PerspectiveCamera(70, 1, 0.01, 4000);
  mode: Mode;
  spec: Scene | null = null;
  reduceMotion = false;

  private root = new THREE.Group();
  private content = new THREE.Group();
  private dynamic = new THREE.Group();
  private driveRoot = new THREE.Group();
  private horizon = new THREE.Group();
  private staticKey = "";
  private driveID = "";
  private arcs = new Map<string, THREE.Object3D>();
  private crowd = new Map<string, Map<string, THREE.Points>>();
  private ball: THREE.Mesh;
  private beacon: THREE.Mesh;
  private beaconGlow: THREE.Sprite;
  private lasers = new Map<string, THREE.Group>();
  private motion = new PlayMotion();
  private flight: Flight | null = null;
  private tweens: { obj: THREE.Object3D; from: THREE.Vector3; to: THREE.Vector3; start: number; seconds: number }[] = [];
  private horizonKey = "";
  private tintKey = "unset";
  private beaconKey = "";
  private glow = glowTexture();
  private disc = discTexture();
  private beam = beamTexture();
  private composer: EffectComposer;
  private bloom: UnrealBloomPass;
  private orbit: OrbitControls;
  private yaw = 0;
  private pitch = -0.16;
  private drag: { x: number; y: number; yaw: number; pitch: number } | null = null;
  private clock = new THREE.Clock();

  constructor(canvas: HTMLCanvasElement, mode: Mode) {
    this.mode = mode;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.xr.enabled = true;
    this.root.add(this.content);
    this.content.add(this.dynamic);
    this.dynamic.add(this.driveRoot, this.horizon);
    this.three.add(this.root);

    this.ball = new THREE.Mesh(new THREE.SphereGeometry(0.6, 20, 14),
      new THREE.MeshBasicMaterial({ color: new THREE.Color("#7A3E17") }));
    this.ball.scale.set(1.6, 1, 1);
    this.ball.visible = false;
    this.beacon = new THREE.Mesh(new THREE.CylinderGeometry(0.7, 0.7, 1, 24, 1, true),
      new THREE.MeshBasicMaterial({ map: this.beam, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }));
    this.beacon.visible = false;
    this.beaconGlow = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.glow, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true }));
    this.beaconGlow.visible = false;
    this.dynamic.add(this.ball, this.beacon, this.beaconGlow);

    this.composer = new EffectComposer(this.renderer);
    this.composer.addPass(new RenderPass(this.three, this.camera));
    this.bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.42, 0.35, 0.9);
    this.composer.addPass(this.bloom);
    this.composer.addPass(new OutputPass());

    this.orbit = new OrbitControls(this.camera, canvas);
    this.orbit.enableDamping = true;
    this.orbit.minDistance = 0.35;
    this.orbit.maxDistance = 2.4;
    this.orbit.maxPolarAngle = Math.PI * 0.49;
    this.bindLook(canvas);
    this.setMode(mode);
    this.renderer.setAnimationLoop(() => this.frame());
  }

  // ── modes and cameras ──

  setMode(mode: Mode): void {
    this.mode = mode;
    this.staticKey = "";
    this.orbit.enabled = mode === "tabletop";
    // Depth precision: a centimetre near plane is right for a model on a
    // table and ruinous across a stadium, where the crowd sits 40 cm above a
    // tier a hundred metres away.
    this.camera.near = mode === "tabletop" ? 0.01 : 0.3;
    this.camera.far = mode === "tabletop" ? 60 : 1600;
    this.camera.updateProjectionMatrix();
    if (mode === "tabletop") {
      // Portrait screens see less of the table side to side, so sit closer.
      const portrait = window.innerWidth < window.innerHeight;
      this.camera.position.set(0, portrait ? 0.56 : 0.42, portrait ? 0.92 : 0.95);
      this.orbit.target.set(0, -0.2, 0);
      this.orbit.update();
    } else {
      this.yaw = 0;
      this.pitch = -0.16;
    }
    if (this.spec) this.apply(this.spec);
  }

  resize(w: number, h: number): void {
    this.renderer.setSize(w, h, false);
    this.composer.setSize(w, h);
    this.bloom.setSize(w, h);
    this.camera.aspect = w / h;
    // Portrait phones see a slice of the bowl at a desktop FOV; widen it.
    this.camera.fov = this.mode === "stadium" ? (w < h ? 82 : 68) : (w < h ? 64 : 50);
    this.camera.updateProjectionMatrix();
  }

  private bindLook(canvas: HTMLCanvasElement) {
    canvas.addEventListener("pointerdown", (e) => {
      if (this.mode !== "stadium") return;
      this.drag = { x: e.clientX, y: e.clientY, yaw: this.yaw, pitch: this.pitch };
      canvas.setPointerCapture(e.pointerId);
    });
    canvas.addEventListener("pointermove", (e) => {
      if (!this.drag || this.mode !== "stadium") return;
      const k = 0.0042;
      this.yaw = this.drag.yaw - (e.clientX - this.drag.x) * k;
      this.pitch = Math.max(-1.1, Math.min(0.9, this.drag.pitch - (e.clientY - this.drag.y) * k));
    });
    const end = () => { this.drag = null; };
    canvas.addEventListener("pointerup", end);
    canvas.addEventListener("pointercancel", end);
  }

  /** Screen position of a field point, for DOM overlays like the moment banner. */
  project(x: number, y: number, z: number, w: number, h: number): { x: number; y: number; visible: boolean } {
    const p = new THREE.Vector3(...local(x, y, z)).applyMatrix4(this.root.matrixWorld).project(this.camera);
    return { x: (p.x * 0.5 + 0.5) * w, y: (-p.y * 0.5 + 0.5) * h, visible: p.z < 1 && p.z > -1 };
  }

  // ── apply ──

  apply(next: Scene): void {
    const previous = this.spec;
    this.spec = next;
    this.place(next);
    const key = [this.mode, next.league, next.teams.home.chip, next.teams.away.chip, next.teams.home.abbr, next.teams.away.abbr].join("|");
    if (key !== this.staticKey) {
      this.buildStatic(next);
      this.staticKey = key;
    }
    this.updateDrive(next, key === this.staticKey ? previous : null);
    this.updateHorizon(next);
    this.updateTint(next);
    if (!this.flight) this.settle(next, !this.reduceMotion);
  }

  private place(s: Scene) {
    if (this.mode === "tabletop") {
      const t = s.presentation.tabletop;
      this.root.scale.setScalar(t.metersPerYard);
      this.root.position.set(0, t.floor, 0);
    } else {
      const st = s.presentation.stadium;
      this.root.scale.setScalar(st.metersPerYard);
      const eye = this.renderer.xr.isPresenting ? 0 : 1.2;
      this.root.position.set(...stadiumRoot(st.seat, st.metersPerYard, eye));
    }
    this.root.updateMatrixWorld(true);
  }

  // ── static ──

  private buildStatic(s: Scene) {
    for (const child of [...this.content.children]) if (child !== this.dynamic) this.content.remove(child);
    this.three.background = colour(s, this.mode === "stadium" ? "sky.top" : "plate", "#121417").c;
    const f = fieldData(s);
    const add = (g: THREE.BufferGeometry, m: THREE.Material) => {
      const mesh = new THREE.Mesh(g, m);
      this.content.add(mesh);
      return mesh;
    };
    add(plates([f.surround], -0.02), basic(s, "turf.surround"));
    add(plates(f.stripesA, 0), basic(s, this.mode === "tabletop" ? "turf.tabletopA" : "turf.a"));
    add(plates(f.stripesB, 0), basic(s, this.mode === "tabletop" ? "turf.tabletopB" : "turf.b"));
    add(plates([f.homeEndZone], 0.005), basic(s, s.teams.home.chip));
    add(plates([f.awayEndZone], 0.005), basic(s, s.teams.away.chip));
    add(plates(f.heavy, 0.01), basic(s, "line.yard", { opacity: 0.7 }));
    add(plates(f.light, 0.01), basic(s, "line.yard", { opacity: 0.42 }));
    add(plates(f.hashes, 0.01), basic(s, "line.yard", { opacity: 0.45 }));
    const ink = s.palette["line.yard"] ?? "#FFFFFF";
    for (const n of f.numbers) {
      const tex = labelTexture(n.label, "700 92px 'Big Shoulders Display', 'Arial Narrow', sans-serif", ink);
      const m = new THREE.Mesh(new THREE.PlaneGeometry(6, 3),
        new THREE.MeshBasicMaterial({ map: tex, transparent: true, opacity: 0.72, depthWrite: false }));
      m.rotation.x = -Math.PI / 2;
      m.position.set(...local(n.x, 0.02, n.z));
      this.content.add(m);
    }
    // Club names in the end zones, read from the home sideline.
    for (const [side, x] of [["home", -s.field.endZone / 2], ["away", s.field.length + s.field.endZone / 2]] as const) {
      const t = s.teams[side];
      const tex = labelTexture(t.name.split(" ").slice(-1)[0].toUpperCase(), "900 150px 'Big Shoulders Display', 'Arial Narrow', sans-serif", t.chipText || "#FFFFFF", 1024, 200);
      const m = new THREE.Mesh(new THREE.PlaneGeometry(s.field.width * 0.8, s.field.width * 0.16),
        new THREE.MeshBasicMaterial({ map: tex, transparent: true, opacity: 0.9, depthWrite: false }));
      m.rotation.set(-Math.PI / 2, 0, side === "home" ? -Math.PI / 2 : Math.PI / 2);
      m.position.set(...local(x, 0.03, 0));
      this.content.add(m);
    }

    const tiers = tiersFor(s, this.mode);
    for (const t of tiers) {
      const d = tierMesh(t, s.bowl.shape);
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(d.positions, 3));
      g.setIndex(d.indices);
      const shade: number[] = [];
      for (let i = 0; i < d.positions.length / 3; i++) {
        const y = d.positions[i * 3 + 1];
        const k = 1.25 - 0.45 * (y - t.rise[0]) / Math.max(1e-6, t.rise[1] - t.rise[0]);
        shade.push(k, k, k);
      }
      g.setAttribute("color", new THREE.Float32BufferAttribute(shade, 3));
      const tierMat = basic(s, t.color, { fallback: "#302722" });
      tierMat.vertexColors = true;
      add(g, tierMat);
      // Risers: faint rings so a tier reads as rows of seats.
      const rows = 5;
      for (let r = 1; r < rows; r++) {
        const m = t.inner + ((t.outer - t.inner) * r) / rows;
        const pts: THREE.Vector3[] = [];
        const y = tierHeight(t, m) + 0.05;
        for (let k = 0; k <= 120; k++) {
          const p = bowlPoint(s.bowl.shape, m, (k / 120) * 2 * Math.PI);
          pts.push(new THREE.Vector3(p.x, y, p.z));
        }
        const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),
          new THREE.LineBasicMaterial({ color: 0xfff0dc, transparent: true, opacity: 0.08 }));
        this.content.add(line);
      }
    }
    // The bowl is centred on midfield in its own coordinates; the field's
    // local() already is, so both share the content group.
    this.crowd.clear();
    const buckets = crowdData(s, tiers, CROWD_COUNT[this.mode]);
    // Point size is in world units and ignores the root's scale, so it is
    // given in yards and converted to metres here.
    const mpy = this.mode === "tabletop" ? s.presentation.tabletop.metersPerYard : s.presentation.stadium.metersPerYard;
    const dot = (this.mode === "tabletop" ? 1.4 : 1.15) * mpy;
    for (const [section, colours] of buckets) {
      const bySection = new Map<string, THREE.Points>();
      for (const [col, raw] of colours) {
        // In the stadium the viewer sits among these people; the few within
        // arm's reach would draw as discs the size of a hand, so they are left
        // out of the drawing (not the data).
        let list = raw;
        if (this.mode === "stadium") {
          const seat = local(s.presentation.stadium.seat.x, s.presentation.stadium.seat.y, s.presentation.stadium.seat.z);
          list = [];
          for (let i = 0; i < raw.length; i += 3) {
            if (Math.hypot(raw[i] - seat[0], raw[i + 1] - seat[1], raw[i + 2] - seat[2]) > 18) list.push(raw[i], raw[i + 1], raw[i + 2]);
          }
        }
        const g = new THREE.BufferGeometry();
        g.setAttribute("position", new THREE.Float32BufferAttribute(list, 3));
        const { c } = colour(s, col);
        const pts = new THREE.Points(g, new THREE.PointsMaterial({ color: c, size: dot, sizeAttenuation: true, map: this.disc, transparent: true, alphaTest: 0.02 }));
        bySection.set(col, pts);
        this.content.add(pts);
      }
      this.crowd.set(section, bySection);
    }
    const outer = tiers[tiers.length - 1];
    if (outer) {
      const rim = rimLightData(s, outer.outer + 1, outer.rise[1] + (this.mode === "tabletop" ? 4 : 9));
      const lamp = this.mode === "tabletop" ? [6, 2] : [10, 4];
      const lampColour = s.bowl.rimLights.color;
      for (const [x, y, z] of rim) {
        const bar = new THREE.Mesh(new THREE.BoxGeometry(lamp[0], lamp[1], 0.6), basic(s, lampColour, { fallback: "#FFF8E6" }));
        bar.position.set(x, y, z);
        bar.lookAt(0, 0, 0);
        this.content.add(bar);
        const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.glow, color: colour(s, lampColour, "#FFF8E6").c, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, opacity: 0.7 }));
        halo.scale.setScalar(this.mode === "tabletop" ? 16 : 26);
        halo.position.set(x, y, z);
        this.content.add(halo);
        // The pole down to the rim.
        const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.25, 0.25, y - outer.rise[1], 6), basic(s, "bowl.upper", { fallback: "#4A4038" }));
        pole.position.set(x, (y + outer.rise[1]) / 2, z);
        this.content.add(pole);
      }
    }
    if (this.mode === "stadium") {
      const sky = new THREE.Mesh(new THREE.SphereGeometry(700, 32, 16), skyMaterial(s));
      this.content.add(sky);
      // Warm haze over the far rim, where the lights are.
      const haze = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.glow, color: new THREE.Color("#FFE9C4"), blending: THREE.AdditiveBlending, transparent: true, opacity: 0.14, depthWrite: false }));
      haze.scale.set(360, 90, 1);
      haze.position.set(0, 55, -95);
      this.content.add(haze);
    }
    this.ball.geometry.dispose();
    this.ball.geometry = new THREE.SphereGeometry(this.mode === "tabletop" ? 1.2 : 0.6, 20, 14);
    this.tintKey = "unset";
    this.beaconKey = "";
    this.horizonKey = "";
    for (const l of this.lasers.values()) this.dynamic.remove(l);
    this.lasers.clear();
    this.tearDownDrive();
  }

  // ── the drive ──

  private tearDownDrive() {
    this.flight = null;
    this.driveRoot.clear();
    this.arcs.clear();
    this.motion.reset();
    this.driveID = "";
  }

  private arcObject(arc: Arc, s: Scene): THREE.Object3D {
    const radius = this.mode === "tabletop" ? 0.45 : 0.22;
    const emphasis = arc.style === "score";
    const holder = new THREE.Group();
    holder.name = `arc.${arc.id}`;
    const halo = tube(arcSamples(arc), radius * 2.4);
    if (halo) holder.add(new THREE.Mesh(halo, basic(s, arc.color, { opacity: emphasis ? 0.22 : 0.1, additive: true, fallback: "#FFFFFF" })));
    for (const piece of arcDashes(arc)) {
      const core = tube(piece, radius * (emphasis ? 1.5 : 1));
      if (core) holder.add(new THREE.Mesh(core, basic(s, arc.color, { fallback: "#FFFFFF" })));
    }
    return holder;
  }

  private updateDrive(s: Scene, previous: Scene | null) {
    const drive = shownDrive(s);
    if (!drive) { this.tearDownDrive(); return; }
    const prevShown = previous ? shownDrive(previous) : null;
    const oldIDs = new Set(prevShown?.arcs.map((a) => a.id) ?? []);
    const nowIDs = new Set(drive.arcs.map((a) => a.id));
    const lostAPlay = oldIDs.size > 0 && drive.id === this.driveID && [...oldIDs].some((id) => !nowIDs.has(id));
    // A new drive right after the old one is the game moving on, and its plays
    // fly. Anything else - a scrub, a jump, the first scene - is laid down.
    const nextDrive = previous
      ? drive.id !== this.driveID && s.drives.length >= previous.drives.length &&
        s.drives.findIndex((d) => d.id === drive.id) === (previous.drives.findIndex((d) => d.id === this.driveID) ?? -2) + 1
      : false;
    if (drive.id !== this.driveID || lostAPlay) {
      this.tearDownDrive();
      this.driveID = drive.id;
      const initial = !nextDrive;
      this.motion.arrive(drive, initial);
      if (initial) { for (const a of drive.arcs) this.addArc(a, s); return; }
    } else {
      this.motion.arrive(drive, false);
    }
    this.startNextFlight();
  }

  private addArc(arc: Arc, s: Scene) {
    if (this.arcs.has(arc.id)) return;
    const o = this.arcObject(arc, s);
    this.arcs.set(arc.id, o);
    this.driveRoot.add(o);
  }

  private startNextFlight() {
    if (this.flight || !this.spec) return;
    const next = this.motion.next(this.reduceMotion, this.spec.motion.floorSeconds);
    if (!next) { this.settle(this.spec, !this.reduceMotion); return; }
    this.ball.visible = true;
    this.flight = { arc: next.arc, start: this.clock.getElapsedTime(), seconds: next.seconds };
  }

  // ── ball, beacon, lasers ──

  private settle(s: Scene, animated: boolean) {
    const seconds = animated ? 0.35 : 0;
    if (s.ball) {
      this.ball.visible = this.beacon.visible = this.beaconGlow.visible = true;
      this.tween(this.ball, new THREE.Vector3(...local(s.ball.x, 0.8, s.ball.z)), seconds);
      const height = s.ball.beacon.height;
      const key = `${height}|${s.ball.beacon.color}|${this.mode}`;
      if (key !== this.beaconKey) {
        this.beaconKey = key;
        const r = this.mode === "tabletop" ? 1.4 : 0.7;
        this.beacon.geometry.dispose();
        this.beacon.geometry = new THREE.CylinderGeometry(r * 0.45, r * 1.2, height, 24, 1, true);
        const mat = this.beacon.material as THREE.MeshBasicMaterial;
        mat.color = colour(s, s.ball.beacon.color, "#BFE3FF").c;
        mat.opacity = 0.45;
        (this.beaconGlow.material as THREE.SpriteMaterial).color = mat.color;
        this.beaconGlow.scale.setScalar(this.mode === "tabletop" ? 10 : 6);
      }
      this.tween(this.beacon, new THREE.Vector3(...local(s.ball.x, height / 2, s.ball.z)), seconds);
      this.tween(this.beaconGlow, new THREE.Vector3(...local(s.ball.x, 0.3, s.ball.z)), seconds);
    } else {
      this.ball.visible = this.beacon.visible = this.beaconGlow.visible = false;
    }
    const want = new Map(s.lasers.map((l) => [l.kind, l]));
    for (const [kind, g] of this.lasers) {
      if (!want.has(kind)) { this.dynamic.remove(g); this.lasers.delete(kind); }
    }
    for (const [kind, laser] of want) {
      let g = this.lasers.get(kind);
      if (!g) {
        g = new THREE.Group();
        const core = new THREE.Mesh(new THREE.BoxGeometry(0.35, 0.08, s.field.width), basic(s, laser.color, { fallback: "#FFD400" }));
        const glow = new THREE.Mesh(new THREE.BoxGeometry(1.0, 0.04, s.field.width), basic(s, laser.color, { opacity: 0.14, additive: true, fallback: "#FFD400" }));
        g.add(glow, core);
        g.position.set(...local(laser.x, 0.05));
        this.dynamic.add(g);
        this.lasers.set(kind, g);
      }
      this.tween(g, new THREE.Vector3(...local(laser.x, 0.05)), seconds);
    }
  }

  private tween(obj: THREE.Object3D, to: THREE.Vector3, seconds: number) {
    this.tweens = this.tweens.filter((t) => t.obj !== obj);
    if (seconds <= 0) { obj.position.copy(to); return; }
    this.tweens.push({ obj, from: obj.position.clone(), to, start: this.clock.getElapsedTime(), seconds });
  }

  // ── horizon and tint ──

  private updateHorizon(s: Scene) {
    const series = s.winProbability.series;
    const key = `${this.mode}|${series.length}|${series[series.length - 1] ?? -1}`;
    if (key === this.horizonKey) return;
    this.horizonKey = key;
    this.horizon.clear();
    const pts = horizonPoints(s.winProbability);
    if (pts.length < 2) return;
    const h = s.winProbability.horizon;
    const thin = this.mode === "tabletop" ? 0.35 : 0.18;
    const rail = (y: number): Vec3[] => [local(h.x0, y, h.z), local(h.x1, y, h.z)];
    for (const [pp, r, o] of [[rail(h.y0), thin, 0.18], [rail(h.y1), thin, 0.18], [rail((h.y0 + h.y1) / 2), thin * 0.7, 0.3]] as const) {
      const g = tube(pp as Vec3[], r);
      if (g) this.horizon.add(new THREE.Mesh(g, basic(s, "#FFFFFF", { opacity: o })));
    }
    const line = tube(pts, thin * 2.2);
    if (line) this.horizon.add(new THREE.Mesh(line, basic(s, "ink", { opacity: 1, fallback: "#F7F6F2" })));
    const glow = tube(pts, thin * (this.mode === "tabletop" ? 3 : 5));
    if (glow) this.horizon.add(new THREE.Mesh(glow, basic(s, "ink", { opacity: 0.08, additive: true, fallback: "#F7F6F2" })));
  }

  private updateTint(s: Scene) {
    const tint = s.bowl.sectionTint;
    const key = tint.side ?? "none";
    if (key === this.tintKey) return;
    this.tintKey = key;
    const teamColours = new Set([s.bowl.crowd.home, s.bowl.crowd.away]);
    for (const [section, colours] of this.crowd) {
      for (const [col, pts] of colours) {
        const m = pts.material as THREE.PointsMaterial;
        if (!tint.side) {
          m.color = colour(s, col).c; m.opacity = 1;
        } else if (tint.side === section) {
          m.color = colour(s, teamColours.has(col) ? tint.color ?? col : col).c; m.opacity = 1;
        } else {
          m.color = colour(s, col).c; m.opacity = tint.dim;
        }
        m.needsUpdate = true;
      }
    }
  }

  // ── frame ──

  private frame() {
    const now = this.clock.getElapsedTime();
    if (this.flight && this.spec) {
      const f = this.flight;
      const t = f.seconds <= 0 ? 1 : (now - f.start) / f.seconds;
      this.ball.position.set(...arcPoint(f.arc, Math.min(1, t)));
      if (t >= 1) {
        this.addArc(f.arc, this.spec);
        this.flight = null;
        this.startNextFlight();
      }
    }
    this.tweens = this.tweens.filter((tw) => {
      const k = Math.min(1, (now - tw.start) / tw.seconds);
      const e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
      tw.obj.position.lerpVectors(tw.from, tw.to, e);
      return k < 1;
    });
    if (this.mode === "tabletop") {
      this.orbit.update();
    } else if (!this.renderer.xr.isPresenting) {
      this.camera.position.set(0, 1.2, 0);
      // Face midfield, then the viewer's own look-around on top.
      const target = new THREE.Vector3().copy(this.root.position);
      const base = Math.atan2(target.x, -target.z);
      const dir = new THREE.Vector3(Math.sin(base + this.yaw) * Math.cos(this.pitch), Math.sin(this.pitch), -Math.cos(base + this.yaw) * Math.cos(this.pitch));
      this.camera.lookAt(this.camera.position.clone().add(dir));
    }
    if (this.renderer.xr.isPresenting) this.renderer.render(this.three, this.camera);
    else this.composer.render();
  }
}
