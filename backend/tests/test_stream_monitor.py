"""Live-agent stream monitor: every failure mode must be detected, not just logged."""

import io

from fastapi.testclient import TestClient
from PIL import Image

from backend.debug import StreamMonitor, jpeg_info
from backend.main import app

client = TestClient(app)


def big_jpg(w=320, h=240) -> bytes:
    b = io.BytesIO()
    Image.effect_noise((w, h), 80).convert("RGB").save(b, format="JPEG", quality=95)
    return b.getvalue()


def test_jpeg_info_dims_and_validity():
    ok, w, h = jpeg_info(big_jpg(320, 240))
    assert (ok, w, h) == (True, 320, 240)
    assert jpeg_info(big_jpg()[:-50])[0] is False  # truncated: no EOI
    assert jpeg_info(b"not a jpeg at all")[0] is False
    assert jpeg_info(b"")[0] is False


def feed(m: StreamMonitor, n: int, t0=1000.0, dt=0.033, **meta):
    for i in range(n):
        m.on_frame(big_jpg(), {"seq": i, "src": "mss", **meta}, now=t0 + i * dt)
    return t0 + (n - 1) * dt


def test_healthy_stream_is_ok():
    m = StreamMonitor()
    end = feed(m, 200)
    h = m.health(viewers=1, now=end)
    assert h["status"] == "OK", h
    assert m.fps(end) > 25


def test_no_frames_is_down_and_no_publisher_flagged():
    m = StreamMonitor()
    m.on_viewers(1, now=100.0)
    m.tick(viewers=1, now=106.0)
    assert m.anomalies.get("no-publisher") == 1
    assert m.health(1, now=106.0)["status"] == "DOWN"


def test_stall_detected_and_recovers():
    m = StreamMonitor()
    end = feed(m, 30)
    m.tick(1, now=end + 3.0)
    assert m.stalled and m.stalls == 1
    assert m.health(1, now=end + 3.0)["status"] == "DOWN"
    m.on_frame(big_jpg(), {"seq": 30, "src": "mss"}, now=end + 3.5)
    assert not m.stalled
    assert "stall-recovered" in m.anomalies


def test_gap_detected():
    m = StreamMonitor()
    end = feed(m, 10)
    found = m.on_frame(big_jpg(), {"seq": 10, "src": "mss"}, now=end + 1.5)
    assert "gap" in found and m.max_gap >= 1.5


def test_synthetic_frames_flagged_as_degraded():
    m = StreamMonitor()
    end = feed(m, 120, src="synthetic")
    h = m.health(1, now=end)
    assert h["status"] == "DEGRADED"
    assert any(c["name"] == "not_synthetic" and not c["ok"] for c in h["checks"])


def test_invalid_and_tiny_frames():
    m = StreamMonitor()
    found = m.on_frame(big_jpg()[:-80], {"seq": 0, "src": "mss"}, now=1.0)
    assert "invalid-frame" in found
    assert "tiny-frame" in m.on_frame(b"\xff\xd8\xff\xd9", {"seq": 1}, now=1.1)


def test_seq_gap_and_reset():
    m = StreamMonitor()
    m.on_frame(big_jpg(), {"seq": 0}, now=1.0)
    m.on_frame(big_jpg(), {"seq": 5}, now=1.1)
    assert m.seq_dropped == 4
    f = m.on_frame(big_jpg(), {"seq": 0}, now=1.2)
    assert "seq-reset" in f and m.seq_resets == 1


def test_resolution_change_and_window_missing_and_errors():
    m = StreamMonitor()
    m.on_frame(big_jpg(320, 240), {"seq": 0, "win": "found"}, now=1.0)
    f = m.on_frame(big_jpg(640, 360), {"seq": 1, "win": "missing", "errs": 3}, now=1.1)
    assert "resolution-change" in f and "agent-publish-errors" in f
    assert m.window == "missing"
    assert any(c["name"] == "window_found" and not c["ok"] for c in m.health(1, now=1.2)["checks"])


def test_fps_low_is_degraded():
    m = StreamMonitor()
    end = feed(m, 20, dt=0.4)  # 2.5 fps
    h = m.health(1, now=end)
    assert any(c["name"] == "fps_ok" and not c["ok"] for c in h["checks"])


def test_event_flood_is_rate_limited():
    m = StreamMonitor()
    for i in range(50):
        m.on_frame(b"\xff\xd8junk", {"seq": i}, now=10.0 + i * 0.01)
    assert m.anomalies["invalid-frame"] == 50  # counted every time
    # ...but logged once per 5s window
    assert m._rl["invalid-frame"] == 10.0


# --- HTTP surface -----------------------------------------------------------


def test_endpoints_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("METABRIDGE_DEBUG_DIR", str(tmp_path))
    client.post("/debug/stream/reset")
    r = client.post("/viewport/frame", content=big_jpg(), headers={"X-MB-Seq": "0", "X-MB-Src": "dxcam", "X-MB-Cap-Ms": "4.2", "X-MB-Win": "found"})
    assert r.status_code == 200
    s = client.get("/debug/stream").json()
    assert s["stream"]["frames"] == 1
    assert s["stream"]["src"] == {"dxcam": 1}
    assert s["stream"]["dims"] == [320, 240]
    assert s["stream"]["agent_cap_ms_avg"] == 4.2
    # empty post is counted, not silently ignored
    client.post("/viewport/frame", content=b"")
    assert client.get("/debug/stream").json()["stream"]["empty_posts"] == 1


def test_ws_viewer_receives_frames_and_broadcast_timed(tmp_path, monkeypatch):
    monkeypatch.setenv("METABRIDGE_DEBUG_DIR", str(tmp_path))
    client.post("/debug/stream/reset")
    with client.websocket_connect("/ws/viewport") as ws:
        client.post("/viewport/frame", content=big_jpg(), headers={"X-MB-Seq": "0", "X-MB-Src": "mss"})
        got = ws.receive_bytes()
        assert jpeg_info(got)[0]
        s = client.get("/debug/stream").json()
        assert s["stream"]["sent"] == 1 and s["viewers"] == 1


def test_client_event_roundtrip_and_validation(tmp_path, monkeypatch):
    monkeypatch.setenv("METABRIDGE_DEBUG_DIR", str(tmp_path))
    r = client.post("/debug/client-event", json={"kind": "ws-close", "data": {"code": 1006}})
    assert r.json()["stored"] == "ok"
    kinds = [e["kind"] for e in client.get("/debug/events?limit=20").json()["events"]]
    assert "client:ws-close" in kinds
    assert client.post("/debug/client-event", content=b"nope").status_code == 400
    assert client.post("/debug/client-event", content=b"x" * 25_000).status_code == 413
    assert client.post("/debug/client-event", json=[1, 2]).status_code == 400
    # hostile kind is sanitized
    client.post("/debug/client-event", json={"kind": "../../etc/passwd\n", "data": "str"})
    ev = client.get("/debug/events?limit=3").json()["events"][-1]["kind"]
    assert "/" not in ev and "\n" not in ev


def test_bundle_includes_stream_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("METABRIDGE_DEBUG_DIR", str(tmp_path))
    client.post("/viewport/frame", content=big_jpg())
    import json, zipfile
    z = zipfile.ZipFile(io.BytesIO(client.get("/debug/bundle").content))
    st = json.loads(z.read("state.json"))
    assert "stream" in st and st["stream"]["frames"] >= 1
