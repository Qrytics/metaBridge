# MetaBridge — Specifications

> The Multimodal Cross-OS Neural KVM & Workspace Fabric — connect macOS and Windows so you can use the same keyboard/mouse, and click-and-drag files (and possibly live game windows) from one screen to the other.

## 1. How the Cross-OS Hardware Bridge Actually Works (Under the Hood)

Three things happening seamlessly between your MacBook Pro (macOS) and your Windows PC over your local Wi-Fi/LAN (or a direct Thunderbolt/USB-C bridge):

### A. Single Mouse (USB Dongle) & Keyboard Sliding Across Both Screens

**How it works:** The machine with the physical USB dongle/keyboard runs a lightweight Input Capture Daemon (using `pynput` / Quartz `CGEventTap` on macOS or Win32 `SendInput` / `LowLevelMouseProc` on Windows).

**The Edge Trigger:** When your cursor hits `x == screen_width - 1` (right edge of Laptop 1), the daemon hides/locks the local cursor and streams raw `[dx, dy, button, keycode]` UDP/WebSocket packets at 120Hz (<2ms LAN latency) to Laptop 2, which injects them natively into the OS!

**Playing Terraria Across Machines:**

- **Scenario 1 (Side-by-Side):** Terraria is running on your Windows screen, and your mouse/keyboard are plugged into your MacBook. You slide your mouse off the right edge of your MacBook straight onto the Windows screen and play Terraria at full native FPS with <2ms input latency!
- **Scenario 2 (Windowed Cross-OS Portal):** You drag the actual Terraria window from your Windows PC onto your MacBook screen! Using a low-latency MJPEG/WebRTC/H.264 stream (via FFmpeg/`mss` screen capture of just the Terraria `HWND` window handle), Terraria renders inside a native-looking window on your MacBook while executing on Windows.

### B. Clicking & Dragging Files Across Screens

When you start dragging a file on Machine A and your cursor crosses the screen boundary into Machine B:

1. Machine A detects the drag state + file path (or a Floating Edge Drop Shelf pops up seamlessly at the screen border).
2. Machine A streams the file bytes over a local FastAPI/WebSocket tunnel to Machine B's temp/Desktop directory.
3. Machine B automatically materializes the file right under your cursor!

## 2. The Catch: How to Make It Legal & High-Scoring for the Meta Hackathon

Remember Stage One Judging (Pass/Fail Viability) and Use of Meta AI Tooling (25%):

> "Your project must incorporate Meta's models. Use the Muse Spark series, Muse Wonder, Muse Image, Muse Voice Transcribe and SAM 3.1 through Meta Model API, run Meta open weights models Muse Glimmer and Muse Spark Open..."

If you build only a standard KVM switch (like Synergy, Barrier, or Deskflow), judges might fail it in Stage 1 for not being an AI project. Wait until you see what happens when you make it an **AI-Powered Cross-OS Neural Bridge** ("NexusOS" / "MetaBridge"):

**The Winning Pitch:** "MetaBridge — The Multimodal Cross-OS Neural KVM & Workspace Fabric"

Instead of just moving raw files and mouse clicks between macOS and Windows, the border between your MacBook and your Windows PC becomes an intelligent AI membrane powered by all 5 Meta models:

### Smart Cross-OS Semantic Drag & Drop (Muse Spark Open 1026 + Muse Wonder 1.0)

- Drag a macOS `.sh` script or Apple Silicon binary across the border onto Windows → Muse Wonder / Muse Spark 1.3 intercepts it mid-drag and automatically transpiles it into a Windows `.ps1` PowerShell script or cross-platform Docker container before it lands on the Windows desktop!
- Drag a messy table screenshot from Windows onto your MacBook → it lands on macOS as a clean `.csv` or TypeScript interface!

### Visual "Point-and-Grab" Object Teleportation (SAM 3.1 + Muse Image)

You're playing Terraria on Windows (or looking at a design/video). Hold a hotkey and click any object or boss sprite inside the Windows game/screen. SAM 3.1 instantly segments just that object out of the Windows screen with zero background, Muse Image upscales or remixes it into a crisp asset, and you drag that segmented cut-out directly across the screen border into an app on your MacBook!

### Cross-OS Voice Command & Co-Op Game Copilot (Muse Voice Transcribe + Muse Wonder)

Speak into one mic: *"Send my active Terraria world save from Windows to my MacBook and look up the crafting tree for the Zenith sword on my second screen."* Muse Voice Transcribe transcribes the command, and Muse Wonder (which is specifically built for "advanced computer use") autonomously controls both the Windows and macOS cursors to locate the `.wld` file, transfer it across the bridge, and open the crafting tree on the other laptop!

## 3. How to Build & Demo This in 48 Hours (Without Driver Hell)

To guarantee a working, rock-solid live demo by Wednesday night, build a 2-Node Python + React/Electron Agent (`bridge-node`) that runs on both your MacBook and your Windows PC:

| # | Feature in Your 3-Min Demo Video | How We Implement It Fast & Reliably |
|---|----------------------------------|-------------------------------------|
| 1 | 1 Mouse + 1 Keyboard across Mac & Windows | Python `pynput` + `websockets` daemon (or wrapping `deskflow-core` / `input-leap` CLI under the hood so you get rock-solid 1000Hz gaming mouse polling in Terraria instantly without debugging OS cursor lock quirks!) |
| 2 | Dragging Files Across the Screen Edge | When your cursor approaches the right edge of Mac (`x > width - 30`), a sleek glowing "Neural Portal Strip" lights up on the edge of both screens. Drop or drag any file/window into the strip, and it instantly materializes on the other OS's screen! |
| 3 | Playing Terraria Across Laptops | Run Terraria on Windows. Move your MacBook-connected mouse/keyboard seamlessly across the screen border into Windows to fight a boss — OR click "Teleport Window to Mac" to stream the live interactive Terraria window onto your MacBook via low-latency WebSocket/MJPEG frame capture + remote input injection! |
| 4 | The Meta AI Magic (SAM 3.1, Muse Wonder, Spark 1026, Voice, Image) | Toggle "AI Membrane Mode" on the Neural Portal Strip: drag a Mac bash script to Windows → auto-converts to PowerShell via `meta-models/muse-spark-open-1026`; click an item/boss in Terraria on Windows → `sam-3.1` segments it out so you can drag the clean sprite straight onto your Mac; speak a voice command → `muse-voice-transcribe` + `muse-wonder-1.0` executes cross-machine computer use across both OSes simultaneously! |

## Reference

- `Meta Global AI Developer Hackathon - Guide & Strategy Doc.pdf` (copied from `metaAria/`) — full hackathon guide & strategy.
