# MetaBridge

The Multimodal Cross-OS Neural KVM & Workspace Fabric — use the same keyboard/mouse across macOS and Windows, and click-and-drag files (and live game windows) from one screen to the other.

## What this is

- **One input, two OSes:** slide a single mouse/keyboard across the MacBook Pro (macOS) and Windows PC screen edge with <2ms LAN input streaming.
- **Cross-screen file drag & drop:** drag a file to the screen border and it materializes on the other OS (transpiled mid-flight by the AI membrane on `ENV=prod`).
- **Live window teleport:** stream an interactive Windows window (e.g. Terraria) onto macOS while it keeps executing on Windows.
- **AI membrane (Meta models):** semantic drag-and-drop conversion (Muse Spark / Wonder), point-and-grab object segmentation (SAM 3.1 + Muse Image), and voice-driven cross-machine actions (Muse Voice Transcribe + Wonder).

See [specifications.md](/Users/mario-ibm/gitProjects/metaBridge/specifications.md) for the full design and [AGENTS.md](/Users/mario-ibm/gitProjects/metaBridge/AGENTS.md) for the locked architecture.

## Quick start (single machine, sim-dual)

```bash
./start-mac.sh            # macOS: venv + deps + bridge + host agent + portal
# open http://127.0.0.1:5173/?sim-dual=1 in a browser
```

Windows equivalent: `powershell -ExecutionPolicy Bypass -File .\start-win.ps1`.

What this launches: bridge API on `:8000`, host capture/input agent following the live `Terraria` window, and the portal on `:5173`. Drag the game window's title bar across the center bezel; `WIN_X` slider mirrors as debug readout.

## macOS as host (Terraria on your MacBook)

1. Install Terraria via Steam, run it **windowed**.
2. Grant permissions (macOS blocks both silently otherwise):
   - System Settings → Privacy & Security → **Screen Recording** → your terminal/IDE.
   - System Settings → Privacy & Security → **Accessibility** → your terminal/IDE (input hooks).
3. `brew install ffmpeg` (mic + audio normalize path).
4. `./start-mac.sh` — captures the live Terraria window (`--title Terraria`) via `mss`, streams frames, publishes 120Hz input.
5. Without permissions the agent logs `SYNTHETIC` and the portal still runs the playable sandbox — grant + restart for live pixels.

## Windows as host (Terraria on your PC)

1. Steam → Terraria → run **windowed**. Keep this PC as the mouse/keyboard machine.
2. `powershell -ExecutionPolicy Bypass -File .\start-win.ps1`.
3. Allow TCP 8000 when the firewall prompts (LAN peers need it).
4. Optional 60fps GPU capture: `.venv\Scripts\pip install dxcam`. Mic path needs `ffmpeg` on PATH.
5. Your LAN IP is printed — point the Mac portal at `VITE_BRIDGE_URL=http://<lan-ip>:8000` (rebuild portal or set at serve time).

## Two-machine LAN run

- **Host** (game + mouse/keyboard): `./start-mac.sh <host-lan-ip>` or `start-win.ps1 <host-lan-ip>`.
- **Client** (second screen): `cd frontend && VITE_BRIDGE_URL=http://<host-lan-ip>:8000 npm run build && npx vite preview --port 5173 --host`, open `http://<client-ip>:5173/?sim-dual=0`.
- Portal shows measured `LATENCY_MS` (WS round-trip) and `CURSOR_OWNER`. Files dropped across the bezel land in `~/MetaBridge-Inbox` on the bridge machine (`METABRIDGE_INBOX` overrides).

## AI membrane

Default `ENV=dev`: deterministic fallbacks, no network, no keys. For live models:

```bash
ENV=prod BASETEN_API_KEY=... META_API_KEY=... ./start-mac.sh
```

`meta-models/muse-spark-open-1026` drafts + `muse-wonder-1.0` criticizes (≤3 retries) file transpiles; SAM/voice/image routers expose `/membrane/*` with dev fallbacks until wired.

## Repo contents

- `backend/` — FastAPI + WebSocket bridge (`main.py`, `bezel.py`, `membrane.py`).
- `agent/` — host node: `capture.py` (mss/dxcam/HWND-title follow + frame publisher), `input_agent.py` (hooks + 120Hz WS/HTTP stream), `host_node.py` runner.
- `frontend/` — dual-viewport portal (`?sim-dual=1` local, `?sim-dual=0` linked).
- `bridge-node/start.py` — one-command launcher per machine.
- `specifications.md`, `Meta Global AI Developer Hackathon - Guide & Strategy Doc.pdf`.
