# MetaBridge

The Multimodal Cross-OS Neural KVM & Workspace Fabric — use the same keyboard/mouse across macOS and Windows, and click-and-drag files (and live game windows) from one screen to the other.

## What this is

- **One input, two OSes:** slide a single mouse/keyboard across the MacBook Pro (macOS) and Windows PC screen edge with <2ms LAN input streaming.
- **Cross-screen file drag & drop:** drag a file to the screen border and it materializes on the other OS.
- **Live window teleport:** stream an interactive Windows window (e.g. Terraria) onto macOS while it keeps executing on Windows.
- **AI membrane (Meta models):** semantic drag-and-drop conversion (Muse Spark / Wonder), point-and-grab object segmentation (SAM 3.1 + Muse Image), and voice-driven cross-machine actions (Muse Voice Transcribe + Wonder).

See [specifications.md](/Users/mario-ibm/gitProjects/metaBridge/specifications.md) for the full under-the-hood design, and `Meta Global AI Developer Hackathon - Guide & Strategy Doc.pdf` for the hackathon guide.

## Repo contents

- `specifications.md` — full technical + hackathon spec
- `Meta Global AI Developer Hackathon - Guide & Strategy Doc.pdf` — hackathon guide (copied from `metaAria/`)

## Status

Scaffolding only — `bridge-node` implementation (Python + React/Electron agent) goes here next.
