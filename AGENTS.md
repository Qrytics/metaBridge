# AGENTS.md — MetaBridge (Stage 1 locked)

> Cross-OS Live Window Straddling, Single-Mouse/Keyboard KVM, and Multimodal AI Bezel Membrane (Windows ↔ macOS). Hackathon deadline: Nov 4.

## 1. Topology (do not change without updating this file)

- **Windows Host Node (Left Screen)** — owns the physical USB mouse/keyboard; runs Steam games (e.g. Terraria windowed) or live video/GIF windows. Runs `agent/` (capture + input) and one `backend/` bridge server instance.
- **macOS Client Node (Right Screen)** — receives 60fps window streams, remote cursor/keyboard telemetry, cross-OS dragged files; renders the synchronized straddling viewport. Runs `frontend/` portal + one `backend/` bridge server instance (same code, `ROLE=mac`).
- **Single-Machine Dual-Viewport Simulator (`--sim-dual`)** — both "Windows Left" and "macOS Right" viewports side-by-side on ONE machine for local testing + Playwright verification. Backend flag: `python -m backend.main --sim-dual`. Frontend: `?sim-dual=1` renders both viewports. Playwright targets the sim-dual page.

```
[Windows Left: agent capture → backend :8000 ←→ backend :8000 ← frontend :5173 :macOS Right]
                    │  WS /ws/viewport (JPEG/WebP binary, 60fps)  │
                    │  WS /ws/input (JSON [dx,dy,buttons,keys], 120Hz) │
                    │  REST /membrane/* (AI bezel membrane) │
```

Ports (defaults, override via env): `BRIDGE_PORT=8000`, `VITE_BRIDGE_URL=http://localhost:8000`.

## 2. Bezel-Crossing math (single source of truth)

Implemented in `backend/bezel.py`, mirrored in `frontend/src/bezel.js`. Tests pin both.

- Left screen width: `W_left`. Target window: `(win_x, win_y, win_w, win_h)`.
- Straddle condition: `win_x + win_w > W_left`.
- Right-screen viewport origin: `mac_win_x = win_x - W_left`, `mac_win_y = win_y` (normalized for vertical alignment via `H_OFFSET = (H_right - H_left) / 2` when heights differ; default 0).
- Visible split: left keeps `(W_left - win_x)` px wide; right renders `(win_x + win_w) - W_left` px wide from the Mac screen's left edge at 60fps. Continuous image across the physical gap.
- Cursor handoff: `(cx, cy)` tracked via `pynput`/OS hooks (permission-checked). When `cx >= W_left - 2` moving right → focus `REMOTE_MAC`, warp/clamp local cursor, stream `[dx, dy, buttons, keys]` at 120Hz.
- Reverse game input: macOS clicks/keys mapped back to host game-local coords: `game_x = mac_cursor_x - mac_win_x`, `game_y = mac_cursor_y - mac_win_y`, clamped to `[0, win_w] × [0, win_h]`; `WASD/Space/Inventory` state forwarded so the Steam game stays playable from the Mac screen.

## 3. Transport

- `GET /health`, `GET /state` (role, cursor owner, straddle offset, fps, latency).
- `WS /ws/viewport` — server→client binary JPEG/WebP frames (query `?role=left|right`).
- `WS /ws/input` — bidirectional JSON telemetry `{dx, dy, buttons, keys, cx, cy, owner}` @120Hz.
- `POST /membrane/transfer-file` — multipart file + `transform: none|ps1-to-sh|sh-to-ps1|config-normalize`; streams bytes + optional transpilation.
- `POST /membrane/sam-rip` — `{frame_id|image_b64, prompt, point:[x,y]}` → `{mask_rle|bbox, cutout_png_b64}`.
- `POST /membrane/voice-command` — 16kHz mono PCM WAV body → `{transcript, action}`.
- `POST /membrane/restyle-asset` — `{image_b64, style}` → `{image_b64}`.

## 4. Meta AI Bezel Membrane — model IDs (exact, do not rename)

| Capability | Model ID | Via | Notes |
|---|---|---|---|
| Bezel File Transpiler (draft) | `meta-models/muse-spark-open-1026` | Baseten, OpenAI-compatible | mid-flight `.ps1`/`.bat` ↔ `.sh`, config translation |
| Transpiler Critic (verify) | `muse-wonder-1.0` | Meta Model API | verifies draft; `MAX_CRITIC_RETRIES = 3` |
| Live Entity Rip (segment) | `sam-3.1` | Meta Model API | text/point-prompted mask → draggable sticker |
| Voice Teleport (STT) | `muse-voice-transcribe` | Meta Model API | FFmpeg 16kHz mono PCM WAV precondition |
| Asset Restyle | `muse-image` | Meta Model API | sprite/image → hi-res concept art at the border |

Rules:

- `ENV=dev` (or missing keys) → deterministic local fallbacks, no network: echo/sh↔ps1 header rewrite, center-box pseudo-mask, canned transcript/action, tint restyle. Production paths only when `META_API_KEY` / `BASETEN_API_KEY` set.
- All five membranes have live paths with identical fallback semantics (try live → None on any failure → dev fallback): Spark draft + Wonder critic (`chat/completions`), SAM 3.1 (`POST {META_SAM_URL|{META_API_URL}/sam-3.1/segment}` JSON, accepts `bbox`/`polygon`/`cutout_png_b64`/`mask_rle`), voice (`POST {META_VOICE_URL|{META_API_URL}/audio/transcriptions}` multipart, OpenAI-compatible), image (`POST {META_IMAGE_URL|{META_API_URL}/images/edits}` multipart, accepts `b64_json` or `url`). Endpoint shapes are overridable per-model env (`META_SAM_URL`, `META_VOICE_URL`, `META_IMAGE_URL`, `BASETEN_API_URL`) without code changes.
- Static JSON schemas live in system prompts (prompt caching); never build schemas dynamically per request.
- `MAX_CRITIC_RETRIES = 3` for the Wonder critic loop (draft → critic → fix, max 3 fixes).
- Never commit keys. Env: `META_API_KEY`, `BASETEN_API_KEY`, `ENV=dev|prod`.

## 5. Aesthetic (frontend, enforced)

Sleek hardware-KVM + Neural Bezel HUD: `border-radius: 0` everywhere, square corners, 1px grid lines, monospace telemetry. HUD must show live `FPS`, `LATENCY_MS`, `STRADDLE_OFFSET_PX`, `CURSOR_OWNER: WIN | MAC`. No rounded cards, no gradients-as-brand.

## 6. Deliverables & verification (Stage 1)

- `backend/` — FastAPI + WebSocket bridge server (`main.py`, `bezel.py`, `membrane.py`).
- `agent/` — OS capture & input agent (`capture.py` via `mss`/`dxcam` w/ 60fps mini-Terraria/sandbox canvas fallback; `input_agent.py` via `pynput` w/ permission checks).
- `frontend/` — dual-screen / frameless portal (`index.html`, `src/`, `vite.config.js`), sim-dual mode.
- Tests: `pytest backend/tests/` (bezel math `mac_win_x = win_x - W_left`, membrane transpile, input mapping) + `vitest` (`frontend/tests/bezel.test.js`) + clean `vite build`.
- Run: `python -m pytest backend/tests -q` · `cd frontend && npm test -- --run && npm run build`.

## 7. Stage 2 — live streaming, direct drag, playable sandbox, membrane DnD

- **SPAN mode (`[SPAN BOTH SCREENS]`):** one 120-column world (1920px, 16px tiles)
  rendered 1:1 with zero stretch: left canvas shows global `[0,960)`, right
  shows `[960,1920)` from a single `spanCanvas` buffer. The floating window
  is parked; player/inventory/day carry over (`carryPlayer`). All input, SAM
  rip, and reverse-tunnel logging route into the span world; title-bar drag
  and voice glides are window-mode only (they auto-exit SPAN first).
  `bezel.spanCamX` / `spanGlobalToWorld` (mirrored py/js) own the math.
- **Desktop projection (`[PROJECT ON DESKTOP]`):** `renderGame(..., {sky:false})`
  skips the sky band/sun so tiles/player/entities float over the OS desktop:
  `frontend/src/desktop.js` paints per-side procedural wallpapers (win blue,
  mac graphite) on each viewport canvas, and the window/span buffers go
  transparent where the sky was. Works in window and SPAN modes; file icons
  (HTML layer) stay on top like real desktop icons.
- **Direct title-bar drag (primary; `WIN_X` slider is debug readout only).**
  Window lives in global desktop coords: left viewport covers `[0, W_LEFT)`,
  right covers `[W_LEFT, W_LEFT + W_RIGHT)`. Mousedown hit-tests the 28px
  title bar (`TERRARIA.EXE [PID 4812] // 60 FPS STREAM`) in either canvas;
  mousemove converts to global x; crossing `x >= W_left` hands active drag
  state + `CURSOR_OWNER WIN -> MAC` so one uninterrupted drag pulls the live
  window Windows -> Mac and back. Slider mirrors `winX` (read-only sync).
- **Sources (KVM bar select):** `LIVE_AGENT_STREAM` = binary JPEG/WebP frames
  from `agent/capture.py` broadcast over `WS /ws/viewport` (publisher: WS
  binary send or `POST /viewport/frame`; viewers: all other subscribers).
  `PLAYABLE_TERRARIA_SANDBOX` = `frontend/src/game.js` 60fps 2D pixel-art
  sandbox (A/D move, Space/W jump, left-click mine, right-click place,
  day/night cycle, inventory bar, King Slime + Eye of Cthulhu bosses). One
  shared state object renders both viewports: left clips `[0, W_LEFT)`, right
  draws overflow at `mac_win_x` — pixel-for-pixel, zero tearing.
- **Reverse input:** A/D/W/S/Space + clicks in either viewport route into the
  shared game state (MAC-side inputs logged as
  `MAC -> WIN INPUT TUNNEL: KEY_SPACE, CLICK (x,y)`). Playable at 100% WIN,
  50/50 straddle, or 100% MAC.
- **Membrane DnD:** desktop file icons (WIN: `deploy_server.ps1`,
  `win_firewall_rules.bat`, `terraria_world.wld`; MAC: `setup_mac_daemon.sh`).
  Dragging a WIN file past the bezel flashes it amber, calls
  `POST /membrane/transfer-file`, runs deterministic `validate_shell` +
  `muse-wonder-1.0` critic loop (`MAX_CRITIC_RETRIES = 3`), drops the `.sh`
  icon on the MAC desktop, opens the Code Diff & Critic Inspector modal.
  `[SAM 3.1 RIP MODE]` toggle / Alt+Click in-game calls
  `POST /membrane/sam-rip`, draws neon polygon contour, mints a draggable
  sprite card (draggable across bezel) with `[MUSE IMAGE HD RESTYLE]`
  (`POST /membrane/restyle-asset`). `[VOICE KVM MIC]` + quick commands call
  `POST /membrane/voice-command`; actions animate `winX` via closed-form
  damped spring (`springStep` in `frontend/src/bezel.js`, frontend-only).
- **New/tested helpers:** `bezel.drag_handoff` (py) / `dragHandoff` (js),
  `bezel.viewport_to_frame` (py) / `viewportToFrame` (js) for SAM click
  mapping, `membrane.validate_shell` + `membrane.critic_verify`,
  `POST /viewport/frame` publisher endpoint, `agent/capture.py::publish_loop`.
- **Verification:** `pytest backend/tests`, `vitest`, clean `vite build`,
  headless Playwright Chromium drags the title bar across the bezel and
  asserts `STRADDLE_OFFSET_PX` updates, both canvases non-blank, zero console
  errors.

## 8. Stage 3 — demo path + hardening (macOS host, landing, launcher)

- **Either OS hosts.** `agent/host_node.py` runs on the mouse/keyboard + game
  machine (macOS or Windows): `find_window_region` follows the live Terraria
  window (win32gui / Quartz, graceful None), `publish_loop` streams frames,
  `InputAgent.stream_loop` publishes 120Hz (WS `/ws/input`, HTTP
  `POST /input/event` fallback, 1s reconnect backoff). macOS needs Screen
  Recording + Accessibility; without them the agent logs SYNTHETIC.
- **File landing.** `POST /membrane/transfer-file?land=1` writes the converted
  file to `~/MetaBridge-Inbox` (`METABRIDGE_INBOX` overrides, traversal-safe)
  and returns `landed_path`; portal logs it + shows it in the inspector modal.
  Real Finder/Explorer drops land via the `#osdrop` overlay (same pipeline).
- **Prod models.** `ENV=prod` + `BASETEN_API_KEY`/`META_API_KEY` (+ optional
  `*_API_URL`) switches the transpiler draft + Wonder critic fixes to live
  OpenAI-compatible calls; any failure falls back to the deterministic
  validator loop. Dev stays network-free.
- **Mic.** Portal `[VOICE KVM MIC]` records ~2s via MediaRecorder and posts to
  `POST /membrane/voice-command-raw` (FFmpeg-normalized to 16kHz mono WAV when
  available); denial/unavailability falls back to the canned command.
- **Latency.** Portal holds `WS /ws/input` with 2s ping probes; HUD shows
  measured RTT (`/ws/input` echoes `pong`). All clicks/keys also forward as
  events; the game stays locally playable on link flap.
- **Launcher.** `bridge-node/start.py` = bridge + host agent + static portal
  per machine; `start-mac.sh` / `start-win.ps1` build venvs and print the LAN
  IP for the peer. `frontend/dist`, `.venv`, `node_modules` never committed.

## 9. Agent working agreements

- Keep bezel math in sync across `backend/bezel.py` ↔ `frontend/src/bezel.js`; change both + both test files together.
- Membrane routers stay thin; model calls isolated in `backend/membrane.py` provider functions for easy mocking.
- `ENV=dev` default; no live model calls in tests (mock providers or assert fallback outputs).
- Conventional commits; Stage 1 scope only — no driver/kernel code.
