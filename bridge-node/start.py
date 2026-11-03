"""bridge-node: one-command MetaBridge launcher per machine.

Runs the bridge server, the host capture/input agent, and serves the portal
(dist/ must be built: `cd frontend && npm run build`). Example:

    python bridge-node/start.py --sim-dual             # single-machine sim-dual
    python bridge-node/start.py --lan 192.168.1.20    # bind LAN for 2-machine
    python bridge-node/start.py --title Terraria --fps 30

Ctrl+C stops everything.
"""

import argparse
import ipaddress
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8000, help="bridge port")
    p.add_argument("--serve-port", type=int, default=5173, help="portal static port")
    p.add_argument("--lan", default="", help="LAN IP to bind (default: localhost only)")
    p.add_argument("--title", default="Terraria", help="live game window title to follow")
    p.add_argument("--fps", type=float, default=30.0)
    p.add_argument("--quality", type=int, default=92, help="JPEG quality for live frames")
    p.add_argument("--sim-dual", action="store_true", help="single-machine dual viewport (sets BRIDGE_SIM_DUAL=1)")
    p.add_argument("--no-agent", action="store_true", help="portal-only machine (no capture)")
    a = p.parse_args()

    host = a.lan
    if host:
        ipaddress.ip_address(host)  # fail fast on typos
    bind = host or "127.0.0.1"
    bridge = f"http://{bind}:{a.port}"
    dist = os.path.join(ROOT, "frontend", "dist")
    if not os.path.isdir(dist):
        print("frontend/dist missing — run: cd frontend && npm install && npm run build")
        return 1

    env = dict(os.environ)
    # Local secrets: repo-root `.env` (KEY=value, never committed) feeds the
    # bridge + agent without touching the shell profile.
    try:
        with open(os.path.join(ROOT, ".env")) as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    env.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))
    except OSError:
        pass
    if a.sim_dual:
        env["BRIDGE_SIM_DUAL"] = "1"
    py = sys.executable
    procs = []
    try:
        procs.append(subprocess.Popen(
            [py, "-m", "uvicorn", "backend.main:app", "--host", bind, "--port", str(a.port),
             "--log-level", "warning", "--no-access-log"],
            cwd=ROOT, env=env,
        ))
        if not a.no_agent:
            procs.append(subprocess.Popen(
                [py, "-m", "agent.host_node", "--bridge", bridge, "--title", a.title, "--fps", str(a.fps), "--quality", str(a.quality)],
                cwd=ROOT, env=env,
            ))
        procs.append(subprocess.Popen(
            [py, "-m", "http.server", str(a.serve_port), "--bind", bind, "--directory", dist],
        ))
        print(f"[bridge-node] bridge {bridge} | portal http://{bind}:{a.serve_port}/?sim-dual=1")
        print(f"[bridge-node] debug bundle: {bridge}/debug/bundle (download after your run)")
        print("[bridge-node] Ctrl+C to stop")
        for proc in procs:
            proc.wait()
    except KeyboardInterrupt:
        print("\n[bridge-node] stopping...")
    finally:
        for proc in procs:
            try:
                proc.terminate()
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
