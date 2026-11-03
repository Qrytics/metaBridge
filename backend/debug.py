"""Flight recorder for live runs: events, frames, client telemetry, bundles.

Events append to JSONL on disk (crash-safe) plus an in-memory ring.
GET /debug/bundle zips everything for post-run analysis. Never logs keys.
"""

import json
import os
import tempfile
import time
import zipfile
from collections import deque

MAX_EVENTS = 2000
MAX_SHOTS = 40
FRAME_DISK_EVERY_S = 10.0

_events: deque = deque(maxlen=MAX_EVENTS)
_counts: dict = {}
_store: dict = {}
_frames: deque = deque(maxlen=5)
_last_frame_disk = 0.0


def debug_dir() -> str:
    if "PYTEST_CURRENT_TEST" in os.environ and not os.environ.get("METABRIDGE_DEBUG_DIR"):
        d = os.path.join(tempfile.gettempdir(), "MetaBridge-Debug-test")
    else:
        d = os.environ.get("METABRIDGE_DEBUG_DIR") or os.path.join(
            os.path.expanduser("~"), "MetaBridge-Debug"
        )
    os.makedirs(d, exist_ok=True)
    return d


def _append_jsonl(name: str, obj: dict) -> None:
    try:
        with open(os.path.join(debug_dir(), name), "a", encoding="utf-8") as f:
            f.write(json.dumps(obj) + "\n")
    except OSError:
        pass


def log_event(kind: str, data: dict | None = None) -> dict:
    ev = {"ts": time.time(), "kind": kind, "data": data or {}}
    _events.append(ev)
    _append_jsonl("events.jsonl", ev)
    return ev


def recent(limit: int = 200) -> list:
    return list(_events)[-max(1, limit):]


def count(name: str, n: int = 1) -> int:
    _counts[name] = _counts.get(name, 0) + n
    return _counts[name]


def get(key: str, default=None):
    return _store.get(key, default)


def set(key: str, value) -> None:
    _store[key] = value


def note_frame(payload: bytes) -> None:
    """Called per published viewport frame: counters always, disk at most every 10s."""
    global _last_frame_disk
    count("viewport_frames")
    count("viewport_bytes", len(payload))
    _frames.append({"ts": time.time(), "bytes": len(payload)})
    now = time.time()
    if now - _last_frame_disk >= FRAME_DISK_EVERY_S:
        _last_frame_disk = now
        try:
            with open(os.path.join(debug_dir(), "latest-frame.jpg"), "wb") as f:
                f.write(payload)
        except OSError:
            pass


def client_note(hud: dict, log_tail: list, shot_b64: str) -> str:
    _append_jsonl("client.jsonl", {"ts": time.time(), "hud": hud, "log": (log_tail or [])[-30:]})
    log_event("client", {"hud": hud})
    if not shot_b64:
        return "ok-no-shot"
    import base64

    try:
        raw = base64.b64decode(shot_b64)
    except (ValueError, Exception):
        return "bad-shot"
    if len(raw) > 2_000_000:
        return "too-large"
    try:
        shots = os.path.join(debug_dir(), "shots")
        os.makedirs(shots, exist_ok=True)
        names = sorted(os.listdir(shots))
        while len(names) >= MAX_SHOTS:
            os.remove(os.path.join(shots, names.pop(0)))
        with open(os.path.join(shots, f"{time.time():.0f}.jpg"), "wb") as f:
            f.write(raw)
    except OSError:
        return "disk-error"
    return "ok"


def snapshot(state: dict) -> dict:
    return {
        "state": dict(state),
        "counts": dict(_counts),
        "recent_frames": list(_frames),
        "recent_events": recent(100),
        "env": {
            "ENV": os.environ.get("ENV", "dev"),
            "has_meta_key": bool(os.environ.get("META_API_KEY")),
            "has_baseten_key": bool(os.environ.get("BASETEN_API_KEY")),
        },
    }


def build_bundle(state: dict) -> str:
    d = debug_dir()
    with open(os.path.join(d, "state.json"), "w", encoding="utf-8") as f:
        json.dump(snapshot(state), f, indent=2)
    zp = os.path.join(d, "metabridge-debug-bundle.zip")
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for name in ("events.jsonl", "client.jsonl", "state.json", "latest-frame.jpg", "agent.jsonl"):
            p = os.path.join(d, name)
            if os.path.exists(p):
                z.write(p, name)
        shots = os.path.join(d, "shots")
        if os.path.isdir(shots):
            for n in sorted(os.listdir(shots)):
                z.write(os.path.join(shots, n), f"shots/{n}")
    return zp
