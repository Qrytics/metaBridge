#!/bin/bash
# MetaBridge macOS host setup + launch (mac = host with Terraria + mouse/keyboard).
set -euo pipefail
cd "$(dirname "$0")"

python3 -m venv .venv 2>/dev/null || true
.venv/bin/pip install -q -r backend/requirements.txt -r agent/requirements.txt

echo "== macOS permissions =="
echo "Grant Screen Recording + Accessibility to your terminal/IDE:"
echo "  System Settings > Privacy & Security > Screen Recording"
echo "  System Settings > Privacy & Security > Accessibility"
echo "FFmpeg (mic + audio normalize): brew install ffmpeg"
echo ""

LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "")
if [ -n "$LAN_IP" ]; then
  echo "LAN IP: $LAN_IP  (Windows portal uses VITE_BRIDGE_URL=http://$LAN_IP:8000)"
fi

# Always rebuild the portal so start.py never serves a stale frontend/dist.
if command -v npm >/dev/null 2>&1; then
  echo "== Building portal =="
  (cd frontend && npm install --silent && npm run build --silent)
else
  echo "WARNING: npm not found - serving existing frontend/dist (may be stale)."
fi

.venv/bin/python bridge-node/start.py --lan "${1:-}" --title Terraria
