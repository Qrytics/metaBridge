# MetaBridge

The Multimodal Cross-OS Neural KVM & Workspace Fabric — use the same keyboard/mouse across macOS and Windows, click-and-drag files (and live game windows) from one screen to the other, and cast it all to your phone.

Built for the Meta Global AI Developer Hackathon (deadline Nov 4). See [specifications.md](/Users/mario-ibm/gitProjects/metaBridge/specifications.md) for the full design and [AGENTS.md](/Users/mario-ibm/gitProjects/metaBridge/AGENTS.md) for the locked architecture (topology, bezel math, model IDs, verification bar).

## What this is

- **One input, two OSes.** Slide a single mouse/keyboard across the MacBook and Windows PC screen edge. The cursor hands off at the bezel (`CURSOR_OWNER: WIN | MAC`) with measured `LATENCY_MS` in the HUD.
- **Live window straddling.** Drag the game window's title bar (`TERRARIA.EXE [PID 4812] // 60 FPS STREAM`) across the center bezel: the left part stays live on Windows while the right part renders live at 60fps from the Mac's edge — one continuous image across the gap.
- **SPAN mode.** `[SPAN BOTH SCREENS]` turns both screens into one 1920px Terraria world rendered 1:1 with zero stretch — Eyefinity-style, left half on one screen, right half on the other.
- **Desktop projection.** `[PROJECT ON DESKTOP]` removes the game's sky so the world floats over each OS desktop (blue Windows wallpaper left, graphite macOS right). Works in window and SPAN mode.
- **Cross-screen file drag & drop.** Drag a `.ps1`/`.bat` across the bezel and it lands on the other OS as verified `.sh` (transpiled mid-flight); real Finder/Explorer files work via drag-and-drop onto the portal. Landed files are written to `~/MetaBridge-Inbox` (`METABRIDGE_INBOX` overrides).
- **AI membrane (5 Meta models).** SAM 3.1 entity rips (Alt+click the boss → draggable sprite card → 1-click Muse Image restyle), voice commands (`[VOICE KVM MIC]` or quick commands glide/teleport the window with spring physics), and the Spark-draft + Wonder-critic file transpiler (≤3 retries, side-by-side diff + Critic Inspector modal).
- **Phone/tablet cast.** `?cast=1` is a fullscreen view-only spectator: open it in iOS Safari, Add to Home Screen, and Terraria plays live from your home screen (wake lock keeps it awake).
- **Playable everywhere.** A/D + Space, mining/placing clicks, and reverse-input tunneling work whether the game is on Windows, straddling, on the Mac, or spanned.

## Quick start (single machine)

```bash
cd /Users/mario-ibm/gitProjects/metaBridge
./start-mac.sh            # macOS: venv + deps + bridge + host agent + portal
# open http://127.0.0.1:5173/?sim-dual=1 in a browser
```

Windows equivalent: `powershell -ExecutionPolicy Bypass -File .\start-win.ps1`.

This launches: bridge API on `:8000`, the host capture/input agent following the live `Terraria` window, and the portal on `:5173`. Try: drag the game title bar across the bezel → `[SPAN BOTH SCREENS]` → `[PROJECT ON DESKTOP]` → drag `deploy_server.ps1` across and inspect the diff modal.

## macOS as host (Terraria on your MacBook)

1. Install Terraria via Steam, run it **windowed**.
2. Grant permissions (macOS blocks both silently otherwise):
   - System Settings → Privacy & Security → **Screen Recording** → your terminal/IDE.
   - System Settings → Privacy & Security → **Accessibility** → your terminal/IDE (input hooks).
3. `brew install ffmpeg` (mic + audio normalize path).
4. `./start-mac.sh` — captures the live Terraria window (`--title Terraria`) via `mss`, streams frames over `WS /ws/viewport`, publishes 120Hz input over `WS /ws/input` (HTTP fallback included).
5. Without permissions the agent logs `SYNTHETIC` and the portal still runs the playable sandbox — grant + restart for live pixels.

## Windows as host (Terraria on your PC)

1. Steam → Terraria → run **windowed**. Keep this PC as the mouse/keyboard machine.
2. `powershell -ExecutionPolicy Bypass -File .\start-win.ps1`.
3. Allow TCP 8000 when the firewall prompts (LAN peers need it).
4. Optional 60fps GPU capture: `.venv\Scripts\pip install dxcam`. Mic path needs `ffmpeg` on PATH.
5. Your LAN IP is printed — point other portals at `http://<lan-ip>:8000`.

## Two-machine LAN run

- **Host** (game + mouse/keyboard): `./start-mac.sh <host-lan-ip>` or `start-win.ps1 <host-lan-ip>`.
- **Client** (second screen): `cd frontend && VITE_BRIDGE_URL=http://<host-lan-ip>:8000 npm run build && npx vite preview --port 5173 --host`, then open `http://<client-ip>:5173/?sim-dual=0`.
- Portal shows measured `LATENCY_MS` (WS round-trip) and `CURSOR_OWNER`.

## iPhone / iPad cast

1. Mac running `./start-mac.sh` (note its LAN IP), iPhone/iPad on the **same Wi-Fi**.
2. Safari → `http://<mac-lan-ip>:5173/?sim-dual=1&cast=1` — fullscreen live Terraria, view-only.
3. Share → **Add to Home Screen** for a one-tap fullscreen icon (iOS web-clip meta tags included; wake lock keeps the screen on).
4. Honest limit: stock iOS widgets/wallpapers cannot stream live video — the fullscreen home-screen icon is the iOS-sanctioned version of "Terraria on my home screen."

## AI membrane + API keys

Default `ENV=dev`: deterministic fallbacks, no network, no keys. For live models:

```bash
ENV=prod BASETEN_API_KEY=... META_API_KEY=... ./start-mac.sh
```

| Variable | Used for | Required? |
|---|---|---|
| `BASETEN_API_KEY` | Draft transpiles via `meta-models/muse-spark-open-1026` (Baseten) | Only with `ENV=prod` |
| `META_API_KEY` | Critic fixes (`muse-wonder-1.0`), SAM 3.1, voice transcribe, image restyle (Meta Model API) | Only with `ENV=prod` |
| `BASETEN_API_URL` / `META_API_URL` | Endpoint bases | Optional (sane defaults) |
| `META_SAM_URL` / `META_VOICE_URL` / `META_IMAGE_URL` | Per-model endpoint overrides | Optional |

All five membranes go live under `ENV=prod` and fall back to deterministic results on any failure (or missing key): Spark drafts + Wonder criticizes (≤3 retries); SAM 3.1 segments the real posted frame; voice transcribes the real mic audio then keyword-maps to a cross-OS action; Muse Image restyles the real sprite crop. Voice/mic additionally needs `ffmpeg` on PATH and a mic grant (MediaRecorder → `POST /membrane/voice-command-raw` → 16kHz mono normalize).

## Verify (gates — run after any change)

```bash
.venv/bin/python -m pytest backend/tests -q   # 33 tests: bezel math, critic, SAM mapping, landing, live-path parsing
cd frontend && npm test -- --run              # 19 tests: bezel math, sandbox physics, spring, projection
npm run build                                 # clean vite build
```

Headless Playwright (needs bridge on `:8000` + `vite preview` on `:4173`):

```bash
node verify-bezel.mjs     # title-bar drag, dual render, reverse input, projection, SPAN
node verify-membrane.mjs  # file transfer + critic modal, SAM rip card, voice glide
node verify-cast.mjs      # phone-viewport fullscreen spectator
```

All three must end `VERIFY PASS ... zero console errors`.

## Repo contents

- `backend/` — FastAPI + WebSocket bridge: `main.py` (REST + `/ws/viewport` + `/ws/input`), `bezel.py` (straddle/camera/input math, mirrored in JS), `membrane.py` (5-model routers, live + dev paths), `tests/`.
- `agent/` — host node: `capture.py` (mss/dxcam/HWND-title follow + frame publisher), `input_agent.py` (OS hooks + 120Hz WS/HTTP stream), `host_node.py` runner.
- `frontend/` — dual-viewport portal: `src/main.js` (window/SPAN/projection/cast orchestrator), `src/game.js` (60fps sandbox), `src/bezel.js` (shared math), `src/membrane.js` (API client), `src/desktop.js` (wallpapers), `src/style.css` (square KVM HUD), `tests/` + `verify-*.mjs`.
- `bridge-node/start.py` — one-command launcher per machine (`start-mac.sh` / `start-win.ps1` wrap it with venv + LAN IP).
- `specifications.md`, `Meta Global AI Developer Hackathon - Guide & Strategy Doc.pdf`, `AGENTS.md`.

## Troubleshooting

- **Spam of `POST 200 OK`s**: fixed — the launcher runs uvicorn with `--no-access-log`. Run the bridge manually (without those flags) only when debugging traffic.
- **`SYNTHETIC` agent on macOS**: grant Screen Recording + Accessibility, restart the launcher.
- **Portal can't reach bridge**: same network? firewall TCP 8000 open on host? `VITE_BRIDGE_URL` baked at `npm run build` time — rebuild after changing it.
- **Mic button falls back instantly**: browser blocked mic permission, or bridge unreachable — the canned command still fires so the demo continues.
- **Black viewport on phone**: check the URL has `?sim-dual=1&cast=1` and the Mac's LAN IP (not `localhost` — that's the phone itself).
