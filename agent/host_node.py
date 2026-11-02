"""MetaBridge host-node runner (Windows OR macOS host).

Captures the live game window (Terraria) and streams JPEG frames to the
bridge while publishing 120Hz input telemetry. Run this on the machine with
the physical mouse/keyboard and the game:

    python -m agent.host_node --bridge http://<host-ip>:8000 --title Terraria

macOS needs Screen Recording + Accessibility permission for this process;
Windows needs no elevation (add a firewall allow for TCP 8000 on LAN).
"""

import argparse
import threading

from .capture import publish_loop
from .input_agent import InputAgent


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--bridge", default="http://localhost:8000")
    p.add_argument("--title", default="Terraria", help="live game window title to follow")
    p.add_argument("--fps", type=float, default=30.0)
    p.add_argument("--hz", type=float, default=120.0)
    a = p.parse_args()

    agent = InputAgent()
    hooked = agent.attach_hooks()
    print(f"[host] input hooks: {'LIVE' if hooked else 'SYNTHETIC (grant Accessibility / rerun)'}")

    t = threading.Thread(
        target=publish_loop,
        kwargs={
            "url": a.bridge.rstrip("/") + "/viewport/frame",
            "fps": a.fps,
            "title": a.title,
        },
        daemon=True,
    )
    t.start()
    print(f"[host] capturing '{a.title}' -> {a.bridge} @ {a.fps}fps, input @{a.hz}Hz")
    try:
        agent.stream_loop(bridge=a.bridge, hz=a.hz)
    except KeyboardInterrupt:
        print("[host] stopped")


if __name__ == "__main__":
    main()
