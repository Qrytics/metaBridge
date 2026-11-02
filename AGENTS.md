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

## 7. Agent working agreements

- Keep bezel math in sync across `backend/bezel.py` ↔ `frontend/src/bezel.js`; change both + both test files together.
- Membrane routers stay thin; model calls isolated in `backend/membrane.py` provider functions for easy mocking.
- `ENV=dev` default; no live model calls in tests (mock providers or assert fallback outputs).
- Conventional commits; Stage 1 scope only — no driver/kernel code.
