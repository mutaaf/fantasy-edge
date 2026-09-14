# Web stadium

A thin web renderer of `/api/scene`: the stadium and the tabletop, drawn with Three.js from the scene spec and nothing else. It is the proof that a second platform ports the scene and the replay controls without re-deciding anything about the game.

```bash
cd clients/web
npm install
npm run stage                                   # capture dir from tests/fixtures
FANTASYEDGE_REPLAY_DIR=clients/web/.replay \
  python3 -m fantasyedge api --port 8793        # from the repo root
npm run dev                                     # http://127.0.0.1:5193
```

Open `http://127.0.0.1:5193/?event=401772810&at=1929&mode=stadium` for the Bears' pick-six. The other URL parameters (`play`, `speed`, `live`, `reduce`, `api`) are listed at the top of `src/main.ts`.

## Layout

| File | Role |
|---|---|
| `src/spec.ts` | Scene types and `parseScene`. It gates on the major version, tolerates unknown fields, and decides nothing. |
| `src/geometry.ts` | Primitives to mesh data. A port of `SceneMath.swift` and the builders in `StadiumMeshes.swift`, with no Three.js. |
| `src/motion.ts` | The ball's play queue, a port of `PlayMotion`. |
| `src/render.ts` | Three.js: the field, bowl, crowd, rim, arcs, lasers, beacon, horizon and tint, plus bloom. |
| `src/main.ts` | Polling, replay controls, scorebug, drive log, moment banner, and tokens into CSS. |
| `tools/fixtures.py` | Stages captures and records the test scenes in-process, deterministically. |
| `tools/shoot.sh` | Headless Chrome screenshots. `tools/frame.html` holds phone sizes. |

## Rules

- **Clients draw; the server decides.** A number a renderer would have to invent belongs in `fantasyedge/scene.py`.
- **Colours come from `design/tokens.json`.** For the scene they arrive embedded as `palette`; for the chrome they are CSS variables set at start-up.
- **Test fixtures are recorded.** Run `npm run fixtures`, never edit them by hand. `npm test` type-checks and runs the suite with no network.
- **Dependencies are pinned:** `three` 0.186.0, `vite` 8.3.0 and `typescript` 7.0.2, plus `@types/three` 0.186.0 for the type-check.
