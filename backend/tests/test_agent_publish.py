"""Agent publisher: sends seq/src/timing headers, survives a dead bridge, flags synthetic."""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from agent import capture


class _H(BaseHTTPRequestHandler):
    got: list = []

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self.rfile.read(n)
        _H.got.append({k.lower(): v for k, v in self.headers.items()})
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *a):
        pass


def test_publish_sends_metadata_headers(monkeypatch, tmp_path):
    monkeypatch.setenv("METABRIDGE_DEBUG_DIR", str(tmp_path))
    monkeypatch.setattr(capture, "capture_window_frame", lambda r=None, q=92: (capture.synthetic_frame(), "synthetic"))
    _H.got = []
    srv = HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    n = capture.publish_loop(url=f"http://127.0.0.1:{srv.server_port}/viewport/frame", fps=60, duration=0.25)
    srv.shutdown()
    assert n >= 5 and len(_H.got) >= 5
    seqs = [int(h["x-mb-seq"]) for h in _H.got]
    assert seqs == list(range(len(seqs)))  # monotonic, no gaps
    assert {h["x-mb-src"] for h in _H.got} == {"synthetic"}
    assert "x-mb-cap-ms" in _H.got[0]
    assert "x-mb-post-ms" in _H.got[-1]  # reported once a POST has been timed


def test_publish_survives_dead_bridge_and_counts_errors(monkeypatch, tmp_path):
    monkeypatch.setenv("METABRIDGE_DEBUG_DIR", str(tmp_path))
    n = capture.publish_loop(url="http://127.0.0.1:9/viewport/frame", fps=30, duration=0.3)
    assert n >= 3  # keeps capturing; does not raise
    log = (tmp_path / "agent.jsonl").read_text()
    assert "publish-error" in log  # the failure is recorded, not swallowed


def test_capture_fallback_is_labelled_synthetic():
    # mss may or may not work in CI; whichever wins must be labelled truthfully.
    frame, src = capture.capture_window_frame(None)
    assert src in ("dxcam", "mss", "synthetic") and len(frame) > 1000
