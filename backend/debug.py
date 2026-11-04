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


def note_frame(payload: bytes, meta: dict | None = None) -> None:
    """Called per published viewport frame: counters always, disk at most every 10s."""
    global _last_frame_disk
    stream.on_frame(payload, meta)
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


# --- Live-agent stream monitor ------------------------------------------------

STALL_S = 2.0        # no frame for this long while a publisher existed -> stall
GAP_S = 1.0          # inter-frame gap that counts as a visible hitch
NO_PUBLISHER_S = 5.0 # viewer connected, still zero frames after this long
MIN_FPS = 10.0
SLOW_BCAST_S = 0.1   # fan-out slower than this blocks the publisher POST


def jpeg_info(b: bytes) -> tuple[bool, int, int]:
    """(valid, width, height). JPEG: SOI at start + EOI at end, dims from SOF.
    WebP (RIFF....WEBP) is accepted as valid with unknown dims."""
    if len(b) >= 12 and b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return True, 0, 0
    if len(b) < 4 or b[0] != 0xFF or b[1] != 0xD8:
        return False, 0, 0
    ok = b[-2:] == b"\xff\xd9"
    w = h = 0
    i, n = 2, len(b)
    while i + 9 < n:
        if b[i] != 0xFF:
            i += 1
            continue
        m = b[i + 1]
        if m == 0xFF or m in (0x01,) or 0xD0 <= m <= 0xD8:
            i += 1 if m == 0xFF else 2
            continue
        if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
            h = (b[i + 5] << 8) | b[i + 6]
            w = (b[i + 7] << 8) | b[i + 8]
            break
        i += 2 + ((b[i + 2] << 8) | b[i + 3])
    return ok, w, h


class StreamMonitor:
    """Watches the publisher->bridge->viewer frame path and flags anomalies.

    Pure state + injected clock (`now`) so it is unit-testable. Every anomaly
    is counted; the event log is rate-limited per kind to avoid flooding.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.frames = 0
        self.bytes = 0
        self.invalid = 0
        self.synthetic = 0
        self.first_ts = 0.0
        self.last_ts = 0.0
        self._ts: deque = deque(maxlen=400)
        self.max_gap = 0.0
        self.seq: int | None = None
        self.seq_dropped = 0
        self.seq_resets = 0
        self.dims: tuple[int, int] | None = None
        self.src_counts: dict = {}
        self.cap_ms: deque = deque(maxlen=120)
        self.post_ms: deque = deque(maxlen=120)
        self.bcast_ms: deque = deque(maxlen=120)
        self.agent_errs = 0
        self.window = "unknown"
        self.stalled = False
        self.stall_started = 0.0
        self.stalls = 0
        self.sent = 0
        self.send_failed = 0
        self.empty_posts = 0
        self.anomalies: dict = {}
        self.viewer_since = 0.0
        self.last_synth_ts = 0.0
        self.last_invalid_ts = 0.0
        self.last_gap_ts = 0.0
        self.last_err_growth_ts = 0.0
        self._rl: dict = {}

    # -- internals --
    def _emit(self, kind: str, data: dict, now: float, every: float = 5.0) -> None:
        self.anomalies[kind] = self.anomalies.get(kind, 0) + 1
        if every and now - self._rl.get(kind, -1e9) < every:
            return
        self._rl[kind] = now
        log_event("stream-" + kind, data)

    @staticmethod
    def _avg(d: deque) -> float:
        return round(sum(d) / len(d), 1) if d else 0.0

    # -- inputs --
    def on_empty_post(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        self.empty_posts += 1
        self._emit("empty-post", {"count": self.empty_posts}, now)

    def on_frame(self, payload: bytes, meta: dict | None = None, now: float | None = None) -> list[str]:
        now = time.time() if now is None else now
        meta = meta or {}
        found: list[str] = []
        gap = now - self.last_ts if self.last_ts else 0.0
        self.frames += 1
        self.bytes += len(payload)
        if not self.first_ts:
            self.first_ts = now
            log_event("stream-first-frame", {"bytes": len(payload), "src": meta.get("src")})
        if self.stalled:
            self.stalled = False
            self._emit("stall-recovered", {"down_s": round(now - self.stall_started, 2)}, now, every=0)
        if gap > GAP_S:
            self.max_gap = max(self.max_gap, gap)
            self.last_gap_ts = now
            found.append("gap")
            self._emit("gap", {"gap_s": round(gap, 2)}, now)
        elif gap:
            self.max_gap = max(self.max_gap, gap)
        self.last_ts = now
        self._ts.append(now)

        ok, w, h = jpeg_info(payload)
        if not ok:
            self.invalid += 1
            self.last_invalid_ts = now
            found.append("invalid-frame")
            self._emit("invalid-frame", {"bytes": len(payload), "head": payload[:8].hex(), "tail": payload[-4:].hex()}, now)
        elif w and h:
            if self.dims and self.dims != (w, h):
                found.append("resolution-change")
                self._emit("resolution-change", {"from": list(self.dims), "to": [w, h]}, now, every=0)
            self.dims = (w, h)
        if len(payload) < 1000:
            found.append("tiny-frame")
            self._emit("tiny-frame", {"bytes": len(payload)}, now)

        src = str(meta.get("src") or "unknown")
        self.src_counts[src] = self.src_counts.get(src, 0) + 1
        if src == "synthetic":
            self.synthetic += 1
            self.last_synth_ts = now
            found.append("synthetic")
            self._emit("synthetic", {"total": self.synthetic, "note": "agent capture failed; fake frames are streaming"}, now)

        seq = meta.get("seq")
        if isinstance(seq, int):
            if self.seq is not None:
                if seq < self.seq:
                    self.seq_resets += 1
                    found.append("seq-reset")
                    self._emit("seq-reset", {"was": self.seq, "now": seq, "note": "agent restarted or two publishers"}, now, every=0)
                elif seq > self.seq + 1:
                    self.seq_dropped += seq - self.seq - 1
                    found.append("seq-gap")
                    self._emit("seq-gap", {"missing": seq - self.seq - 1, "total": self.seq_dropped}, now)
            self.seq = seq

        for key, dq in (("cap_ms", self.cap_ms), ("post_ms", self.post_ms)):
            v = meta.get(key)
            if isinstance(v, (int, float)) and v >= 0:
                dq.append(float(v))
        errs = meta.get("errs")
        if isinstance(errs, int):
            if errs > self.agent_errs:
                self.last_err_growth_ts = now
                found.append("agent-publish-errors")
                self._emit("agent-publish-errors", {"total": errs}, now)
            self.agent_errs = errs
        if meta.get("win"):
            if meta["win"] == "missing" and self.window != "missing":
                self._emit("window-missing", {"note": "agent cannot find the game window; capturing fallback region"}, now, every=0)
            self.window = str(meta["win"])
        return found

    def on_broadcast(self, sent: int, failed: int, took_s: float, now: float | None = None) -> None:
        now = time.time() if now is None else now
        self.sent += sent
        self.send_failed += failed
        self.bcast_ms.append(took_s * 1000.0)
        if failed:
            self._emit("viewer-send-failed", {"failed": failed}, now, every=0)
        if took_s > SLOW_BCAST_S:
            self._emit("slow-broadcast", {"ms": round(took_s * 1000), "note": "a slow viewer is back-pressuring the publisher"}, now)

    def on_viewers(self, n: int, now: float | None = None) -> None:
        now = time.time() if now is None else now
        if n > 0 and not self.viewer_since:
            self.viewer_since = now
        elif n == 0:
            self.viewer_since = 0.0

    def tick(self, viewers: int = 0, now: float | None = None) -> None:
        """Call ~2Hz. Detects silence, which no per-frame hook can see."""
        now = time.time() if now is None else now
        if self.frames and not self.stalled and now - self.last_ts > STALL_S:
            self.stalled = True
            self.stall_started = self.last_ts
            self.stalls += 1
            self._emit("stall", {"silent_s": round(now - self.last_ts, 1), "viewers": viewers}, now, every=0)
        if not self.frames and viewers and self.viewer_since and now - self.viewer_since > NO_PUBLISHER_S:
            self._emit("no-publisher", {"viewers": viewers, "waiting_s": round(now - self.viewer_since, 1),
                                        "note": "viewer is waiting but the agent never posted a frame"}, now, every=30)

    # -- outputs --
    def fps(self, now: float | None = None, window: float = 5.0) -> float:
        now = time.time() if now is None else now
        n = sum(1 for t in self._ts if now - t <= window)
        span = min(window, now - self.first_ts) if self.first_ts else 0
        return round(n / span, 1) if span > 0.5 else 0.0

    def summary(self, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        return {
            "frames": self.frames, "bytes": self.bytes, "fps_5s": self.fps(now),
            "age_s": round(now - self.last_ts, 2) if self.last_ts else None,
            "max_gap_s": round(self.max_gap, 2), "invalid": self.invalid,
            "synthetic": self.synthetic, "src": dict(self.src_counts),
            "dims": list(self.dims) if self.dims else None,
            "seq_dropped": self.seq_dropped, "seq_resets": self.seq_resets,
            "agent_cap_ms_avg": self._avg(self.cap_ms), "agent_post_ms_avg": self._avg(self.post_ms),
            "bridge_broadcast_ms_avg": self._avg(self.bcast_ms),
            "agent_publish_errors": self.agent_errs, "window": self.window,
            "stalled": self.stalled, "stalls": self.stalls,
            "sent": self.sent, "send_failed": self.send_failed, "empty_posts": self.empty_posts,
            "anomalies": dict(self.anomalies),
        }

    def health(self, viewers: int = 0, now: float | None = None) -> dict:
        now = time.time() if now is None else now

        def recent(ts: float, within: float = 30.0) -> bool:
            return bool(ts) and now - ts <= within

        age = now - self.last_ts if self.last_ts else None
        fps = self.fps(now)
        checks = [
            ("publisher_alive", bool(self.frames) and age is not None and age <= STALL_S,
             "no frame ever received" if not self.frames else f"last frame {age:.1f}s ago"),
            ("fps_ok", fps >= MIN_FPS, f"{fps} fps over 5s (min {MIN_FPS})"),
            ("not_synthetic", not recent(self.last_synth_ts, 10), f"{self.synthetic} synthetic frames"),
            ("frames_valid", not recent(self.last_invalid_ts), f"{self.invalid} invalid frames"),
            ("no_hitches", not recent(self.last_gap_ts), f"max gap {self.max_gap:.2f}s"),
            ("agent_publish_ok", not recent(self.last_err_growth_ts), f"{self.agent_errs} agent POST errors"),
            ("window_found", self.window != "missing", f"window={self.window}"),
            ("viewers_connected", viewers >= 1, f"{viewers} viewer(s)"),
        ]
        alive = checks[0][1]
        status = "DOWN" if not alive else ("OK" if all(c[1] for c in checks) else "DEGRADED")
        return {"status": status, "checks": [{"name": n, "ok": bool(ok), "detail": d} for n, ok, d in checks]}


stream = StreamMonitor()

_ev_times: deque = deque(maxlen=100)


def client_event(kind: str, data, host: str = "") -> str:
    """Portal-reported event (stream stalls, ws closes, console errors...)."""
    now = time.time()
    while _ev_times and now - _ev_times[0] > 10:
        _ev_times.popleft()
    if len(_ev_times) >= 100:
        count("client_events_dropped")
        return "dropped"
    _ev_times.append(now)
    kind = "".join(c for c in str(kind)[:64] if c.isalnum() or c in "-_:.") or "unknown"
    if not isinstance(data, dict):
        data = {"value": str(data)[:500]}
    if len(json.dumps(data, default=str)) > 8000:
        data = {"truncated": True, "keys": list(data)[:20]}
    log_event("client:" + kind, {**data, "host": host})
    return "ok"


def snapshot(state: dict) -> dict:
    return {
        "stream": stream.summary(),
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
