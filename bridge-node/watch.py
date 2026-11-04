"""Live health watcher for the LIVE_AGENT_STREAM path (run during a real session).

    python bridge-node/watch.py http://<windows-ip>:8000

Prints one line per second; prints a loud block whenever a check flips to
failing, naming the check and its detail. Ctrl+C to stop. Stdlib only.
"""

import json
import sys
import time
import urllib.request


def get(base: str) -> dict:
    with urllib.request.urlopen(base.rstrip("/") + "/debug/stream", timeout=3) as r:
        return json.load(r)


def main() -> None:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    failing: set = set()
    print(f"watching {base}/debug/stream  (Ctrl+C to stop)")
    while True:
        try:
            d = get(base)
        except Exception as exc:
            print(f"!! BRIDGE UNREACHABLE: {exc}")
            time.sleep(1)
            continue
        s, h = d["stream"], d["health"]
        print(f"{time.strftime('%H:%M:%S')} {h['status']:<8} fps={s['fps_5s']:<5} age={s['age_s']}s dims={s['dims']} "
              f"viewers={d['viewers']} src={s['src']} cap={s['agent_cap_ms_avg']}ms bcast={s['bridge_broadcast_ms_avg']}ms "
              f"inv={s['invalid']} gaps_max={s['max_gap_s']}s seq_lost={s['seq_dropped']}")
        now = {c["name"] for c in h["checks"] if not c["ok"]}
        for c in h["checks"]:
            if c["name"] in now - failing:
                print(f"\n  >>> FAIL  {c['name']}: {c['detail']}\n")
            elif c["name"] in failing - now:
                print(f"  <<< recovered  {c['name']}")
        failing = now
        time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
