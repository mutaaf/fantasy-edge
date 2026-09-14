// The web client: poll the scene, hand it to the renderer, drive the replay.
//
// URL parameters, for links and screenshots:
//   ?event=401772810   load this captured game into the replay
//   &at=1929           ... at this game second
//   &speed=60          replay speed
//   &play=1            start playing
//   &mode=stadium      or tabletop
//   &live=EVENT        draw /api/scene/EVENT instead of the replay
//   &reduce=1          reduce motion
//   &api=http://host   an API somewhere else (CORS is open on it)

import { VRButton } from "three/addons/webxr/VRButton.js";
import tokens from "../../../design/tokens.json";
import { Api, ApiError, type ReplayState } from "./api.ts";
import { celebrates, parseScene, shownDrive, type Scene, type Team } from "./spec.ts";
import { StadiumView } from "./render.ts";
import type { Mode } from "./geometry.ts";

// ── tokens into CSS ──
const root = document.documentElement.style;
for (const [key, value] of Object.entries(tokens.color as Record<string, string>)) {
  root.setProperty(`--${key.replace(/\./g, "-").toLowerCase()}`, value);
}
root.setProperty("--plate-solid", (tokens.color as Record<string, string>)["plate"].slice(0, 7));
root.setProperty("--chip-text", tokens.chip.text);

const q = new URLSearchParams(location.search);
const api = new Api(q.get("api") ?? "");
const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const canvas = $<HTMLCanvasElement>("stage");
const reduce = q.get("reduce") === "1" || matchMedia("(prefers-reduced-motion: reduce)").matches;

let mode: Mode = q.get("mode") === "tabletop" ? "tabletop" : "stadium";
const view = new StadiumView(canvas, mode);
view.reduceMotion = reduce;

function resize() {
  view.resize(window.innerWidth, window.innerHeight);
}
addEventListener("resize", resize);
resize();

// Offer VR only where a headset can actually be entered.
const xr = (navigator as Navigator & { xr?: { isSessionSupported(m: string): Promise<boolean> } }).xr;
xr?.isSessionSupported("immersive-vr").then((ok) => {
  if (ok) $("vr").appendChild(VRButton.createButton(view.renderer));
}).catch(() => {});

// ── state ──
let scene: Scene | null = null;
let replay: ReplayState | null = null;
let scrubbing = false;
let lastMomentKey = "";
const live = q.get("live");

const ICON = {
  play: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 4.5v15l13-7.5z"/></svg>',
  pause: '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4.5" width="4" height="15" rx="1"/><rect x="14" y="4.5" width="4" height="15" rx="1"/></svg>',
};

function esc(s: unknown): string {
  return String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]!));
}

function chip(t: Team): string {
  return `<span class="chip${t.hatch ? " hatch" : ""}" style="background-color:${esc(t.chip)};color:${esc(t.chipText)}">${esc(t.abbr)}</span>`;
}

function showStatus(title: string, body: string, fix?: string) {
  const el = $("status");
  el.innerHTML = `<b>${esc(title)}</b>${esc(body)}${fix ? `<br><code>${esc(fix)}</code>` : ""}`;
  el.hidden = false;
}

function hideStatus() { $("status").hidden = true; }

// ── rendering the chrome ──

function renderScorebug(s: Scene) {
  const st = s.status;
  const badges = [
    s.source === "replay" ? '<span class="badge replay">Replay</span>' : "",
    st.redZone ? '<span class="badge redzone">Red zone</span>' : "",
    celebrates(s.activeMoment) ? '<span class="badge scored">Score</span>' : "",
  ].join("");
  const label = st.state === "post" ? "Final" : st.state === "pre" ? "Pre-game" : st.label.replace(" - ", " · ");
  $("scorebug").innerHTML =
    `<div class="side">${chip(s.teams.away)}<span class="score">${esc(st.awayScore)}</span></div>` +
    `<div class="mid"><span class="label">${esc(label)}</span><span class="dd">${esc(st.downDistance || " ")}</span><div class="badges">${badges}</div></div>` +
    `<div class="side"><span class="score">${esc(st.homeScore)}</span>${chip(s.teams.home)}</div>`;
}

function renderDrive(s: Scene) {
  const d = shownDrive(s);
  const el = $("drive");
  if (!d || !d.arcs.length) { el.innerHTML = ""; return; }
  const t = d.side ? s.teams[d.side] : null;
  const items = d.arcs.map((a, i) => {
    const text = a.text.replace(/^\(\d+:\d+\)\s*(\(Shotgun\)\s*)?(Shotgun\s*)?/, "");
    const dd = a.down ? `${a.down}${["st", "nd", "rd", "th"][Math.min(a.down, 4) - 1]} & ${a.distance ?? ""}` : "";
    const style = s.palette[a.color] ?? "";
    return `<li class="${i === d.arcs.length - 1 ? "last" : ""}"><span class="n" style="--style:${esc(style)}">${i + 1}</span><span>${dd ? `<b>${esc(dd)}</b> · ` : ""}${esc(text)}</span></li>`;
  }).join("");
  el.innerHTML = `<h2>This drive <small>${t ? esc(t.abbr) + " · " : ""}${d.arcs.length} plays${d.result ? " · " + esc(d.result) : ""}</small></h2><ol>${items}</ol>`;
}

const WORD: Record<string, string> = { touchdown: "TOUCHDOWN", fieldGoal: "FIELD GOAL", safety: "SAFETY" };

function renderMoment(s: Scene) {
  const el = $("moment");
  const m = s.activeMoment;
  if (!celebrates(m) || !m) { el.hidden = true; lastMomentKey = ""; return; }
  const key = `${m.playId}|${m.kind}`;
  const t = s.teams[m.side];
  el.innerHTML = `<div>${chip(t)}</div><div class="word">${esc(WORD[m.kind] ?? m.kind.toUpperCase())}</div><div class="play">${esc(m.text)}</div>`;
  el.hidden = false;
  if (key !== lastMomentKey && !reduce) {
    el.classList.remove("enter");
    void el.offsetWidth;
    el.classList.add("enter");
  }
  lastMomentKey = key;
}

/** Keep the banner over the end zone the scoring side attacks. The home side
 * defends x = 0 and attacks toward 100 (scene.py's axes), so its end zone to
 * score in is the away one, and the reverse. */
function placeMoment() {
  const el = $("moment");
  if (el.hidden || !scene?.activeMoment) return;
  const f = scene.field;
  const [z0, z1] = scene.activeMoment.side === "home" ? f.awayEndZone : f.homeEndZone;
  const w = innerWidth, h = innerHeight;
  const p = view.project((z0 + z1) / 2, mode === "stadium" ? 26 : 30, 0, w, h);
  const half = el.offsetWidth / 2 + 16;
  const x = p.visible ? Math.max(half, Math.min(w - half, p.x)) : w / 2;
  // Never over the scorebug: the banner's top sits below the header.
  const floor = document.querySelector(".top")!.getBoundingClientRect().bottom + 14 + el.offsetHeight;
  const y = Math.max(floor, p.visible ? Math.min(h * 0.6, p.y) : h * 0.42);
  el.style.left = `${x}px`;
  el.style.top = `${y}px`;
}

function renderControls(r: ReplayState | null) {
  const playing = !!r?.playing;
  const play = $<HTMLButtonElement>("play");
  play.innerHTML = playing ? ICON.pause : ICON.play;
  play.setAttribute("aria-label", playing ? "Pause" : "Play");
  const scrub = $<HTMLInputElement>("scrub");
  if (r?.length) scrub.max = String(r.length);
  if (!scrubbing && r?.gameSeconds !== undefined) scrub.value = String(r.gameSeconds);
  $("clock").textContent = r?.label ?? "—";
  const speed = $<HTMLSelectElement>("speed");
  const speeds = r?.speeds ?? [];
  if (speed.options.length !== speeds.length) {
    speed.innerHTML = speeds.map((v) => `<option value="${v}">${v}×</option>`).join("");
  }
  if (r) speed.value = String(r.speed);
  $<HTMLButtonElement>("replay-drive").disabled = r?.driveStart == null;
  for (const [id, m] of [["mode-tabletop", "tabletop"], ["mode-stadium", "stadium"]] as const) {
    $(id).setAttribute("aria-selected", String(mode === m));
  }
}

function renderGames(r: ReplayState) {
  const sel = $<HTMLSelectElement>("game");
  const games = r.games ?? [];
  const html = games.map((g) => {
    const name = `${g.away?.abbr ?? "?"} at ${g.home?.abbr ?? "?"}`;
    const date = (g.date ?? "").slice(0, 10);
    return `<option value="${esc(g.event)}">${esc(name)}${date ? " · " + esc(date) : ""}</option>`;
  }).join("");
  if (sel.dataset.html !== html) { sel.innerHTML = html; sel.dataset.html = html; }
  if (r.event) sel.value = r.event;
}

// ── the loop ──

function applyScene(payload: unknown) {
  const parsed = parseScene(payload);
  if (!parsed.ok) { showStatus("This scene can’t be drawn", parsed.error); return; }
  hideStatus();
  scene = parsed.scene;
  if (scene.replayControl) replay = { ...replay, ...scene.replayControl } as ReplayState;
  view.apply(scene);
  renderScorebug(scene);
  renderDrive(scene);
  renderMoment(scene);
  renderControls(replay);
}

async function poll() {
  try {
    if (live) {
      applyScene(await api.scene(live));
    } else {
      applyScene(await api.replayScene());
    }
  } catch (err) {
    if (err instanceof ApiError && err.status === 404 && !live) {
      showStatus("No game loaded", "Pick a game to replay.", err.fix);
    } else if (err instanceof ApiError) {
      showStatus(err.status ? "The API refused" : "Can’t reach the API", err.message, err.fix);
    }
  }
  setTimeout(poll, live ? 3000 : 700);
}

async function control(body: Record<string, unknown>) {
  try {
    replay = await api.control(body);
    renderControls(replay);
    renderGames(replay);
  } catch (err) {
    if (err instanceof ApiError) showStatus("The replay didn’t move", err.message, err.fix);
  }
}

function frame() {
  placeMoment();
  requestAnimationFrame(frame);
}

// ── wiring ──

$("play").addEventListener("click", () => control({ action: replay?.playing ? "pause" : "play" }));
const scrub = $<HTMLInputElement>("scrub");
scrub.addEventListener("input", () => { scrubbing = true; });
scrub.addEventListener("change", async () => {
  await control({ action: "seek", at: Number(scrub.value) });
  scrubbing = false;
});
$<HTMLSelectElement>("speed").addEventListener("change", (e) => control({ action: "speed", speed: Number((e.target as HTMLSelectElement).value) }));
$("replay-drive").addEventListener("click", () => {
  if (replay?.driveStart != null) control({ action: "seek", at: replay.driveStart });
});
$<HTMLSelectElement>("game").addEventListener("change", (e) => control({ action: "load", event: (e.target as HTMLSelectElement).value, at: 0 }));
for (const [id, m] of [["mode-tabletop", "tabletop"], ["mode-stadium", "stadium"]] as const) {
  $(id).addEventListener("click", () => {
    mode = m;
    view.setMode(m);
    resize();
    renderControls(replay);
    const u = new URL(location.href);
    u.searchParams.set("mode", m);
    history.replaceState(null, "", u);
  });
}
$("drive-toggle").addEventListener("click", () => $("drive").classList.toggle("open"));

async function start() {
  renderControls(null);
  if (!live) {
    try {
      replay = await api.replay();
      renderGames(replay);
      const event = q.get("event") ?? (replay.loaded ? null : replay.games?.[0]?.event ?? null);
      if (event && (event !== replay.event || q.has("at"))) {
        await control({ action: "load", event, at: Number(q.get("at") ?? 0) });
      }
      if (q.has("speed")) await control({ action: "speed", speed: Number(q.get("speed")) });
      if (q.get("play") === "1") await control({ action: "play" });
    } catch (err) {
      if (err instanceof ApiError) showStatus("Can’t reach the API", err.message, err.fix);
    }
  }
  poll();
  frame();
}

start();
