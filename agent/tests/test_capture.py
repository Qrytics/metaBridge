"""Agent capture: the 1:1 demo needs high-quality JPEGs and a working publish loop."""

import agent.capture as cap


def test_synthetic_frame_is_jpeg():
    assert cap.synthetic_frame()[:2] == b"\xff\xd8"


def test_capture_defaults_to_quality_92(monkeypatch):
    seen = {}

    def fake_jpeg(img, quality=75):
        seen["quality"] = quality
        return b"\xff\xd8fake"

    monkeypatch.setattr(cap, "_to_jpeg", fake_jpeg)
    assert cap.capture_window_once() == b"\xff\xd8fake"
    assert seen["quality"] == 92


def test_publish_loop_sends_without_bridge():
    # Unreachable bridge: frames are captured locally, errors swallowed.
    assert cap.publish_loop(url="http://127.0.0.1:9/viewport/frame", duration=0, quality=50) == 1
