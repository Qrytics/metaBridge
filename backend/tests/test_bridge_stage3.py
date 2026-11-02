"""Stage 3: file landing, voice-raw ingest, input events, window lookup."""

import os

from fastapi.testclient import TestClient

from agent.capture import find_window_region
from backend.main import app

client = TestClient(app)


def test_transfer_land_writes_inbox(tmp_path, monkeypatch):
    monkeypatch.setenv("METABRIDGE_INBOX", str(tmp_path))
    res = client.post(
        "/membrane/transfer-file?transform=ps1-to-sh&land=1",
        files={"file": ("deploy_server.ps1", b'Write-Output "x"\n$env:A = 1\n')},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["landed_path"].startswith(str(tmp_path))
    assert os.path.isfile(body["landed_path"])
    with open(body["landed_path"]) as f:
        text = f.read()
    assert "echo" in text and "export A" in text
    # Traversal-safe: served name cannot escape the inbox.
    assert ".." not in body["landed_path"].replace(str(tmp_path), "")


def test_voice_raw_ingest_keys():
    res = client.post("/membrane/voice-command-raw", content=b"RIFF....fake-audio")
    assert res.status_code == 200
    body = res.json()
    assert body["transcript"] and body["action"]
    assert body["received_bytes"] == 18
    assert "normalized" in body


def test_input_event_flips_owner():
    assert client.post("/input/event", json={"cx": 100, "w_left": 1920}).json()["owner"] == "WIN"
    assert client.post("/input/event", json={"cx": 1919, "w_left": 1920}).json()["owner"] == "MAC"
    state = client.get("/state").json()
    assert state["cursor_owner"] == "MAC"
    assert state["last_input_ts"] > 0


def test_find_window_region_no_match_no_crash():
    assert find_window_region("no-such-window-xyz-123") is None


# --- Live model paths (network faked; keys + ENV=prod exercised) ---

from backend import membrane as membrane_pkg


def _prod(monkeypatch):
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("META_API_KEY", "test-key")


def test_action_from_transcript_mapping():
    assert membrane_pkg.action_from_transcript("teleport the game to my mac") == "slide-window-to-mac+screenshot"
    assert membrane_pkg.action_from_transcript("glide to half straddle") == "glide-50%-straddle"
    assert membrane_pkg.action_from_transcript("transpile all scripts") == "transpile-all-scripts"
    assert membrane_pkg.action_from_transcript("send it back to win") == "slide-window-to-win"


def test_sam_live_parses_bbox_and_polygon(monkeypatch):
    _prod(monkeypatch)
    monkeypatch.setattr(
        membrane_pkg, "_meta_json",
        lambda url, key, payload: {"bbox": [0.1, 0.2, 0.5, 0.8], "polygon": [[1, 2], [3, 4], [5, 6]]},
    )
    out = membrane_pkg.sam_rip_live("aGk=", "boss", [0.5, 0.5])
    assert out["bbox"] == [0.1, 0.2, 0.5, 0.8]
    assert out["polygon"] == [[1, 2], [3, 4], [5, 6]]
    assert out["model"] == "sam-3.1"


def test_sam_live_needs_key_and_image(monkeypatch):
    monkeypatch.delenv("META_API_KEY", raising=False)
    assert membrane_pkg.sam_rip_live("aGk=", "boss", [0.5, 0.5]) is None
    monkeypatch.setenv("META_API_KEY", "k")
    assert membrane_pkg.sam_rip_live("", "boss", [0.5, 0.5]) is None


def test_voice_live_transcribe_and_action(monkeypatch):
    _prod(monkeypatch)
    monkeypatch.setattr(
        membrane_pkg, "_meta_multipart",
        lambda url, key, fields, files: {"text": "glide to half straddle"},
    )
    out = membrane_pkg.voice_command_live(b"RIFFfake")
    assert out == {
        "transcript": "glide to half straddle",
        "action": "glide-50%-straddle",
        "model": "muse-voice-transcribe",
    }


def test_restyle_live_parses_b64(monkeypatch):
    _prod(monkeypatch)
    monkeypatch.setattr(
        membrane_pkg, "_meta_multipart",
        lambda url, key, fields, files: {"data": [{"b64_json": "aGk="}]},
    )
    import base64

    img = base64.b64encode(b"fake-png").decode()
    out = membrane_pkg.restyle_live(img, "concept-art-hd")
    assert out["image_b64"] == "aGk=" and out["model"] == "muse-image"


def test_sam_endpoint_prefers_live(monkeypatch):
    _prod(monkeypatch)
    monkeypatch.setattr(
        membrane_pkg, "_meta_json",
        lambda url, key, payload: {"bbox": [0, 0, 1, 1], "cutout_png_b64": "eA=="},
    )
    res = client.post("/membrane/sam-rip", json={"prompt": "boss", "point": [0.5, 0.5], "image_b64": "aGk="})
    assert res.status_code == 200
    assert res.json()["bbox"] == [0, 0, 1, 1]


def test_sam_endpoint_falls_back_without_key(monkeypatch):
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.delenv("META_API_KEY", raising=False)
    res = client.post("/membrane/sam-rip", json={"prompt": "boss", "point": [0.5, 0.5], "image_b64": "aGk="})
    assert res.status_code == 200
    assert res.json()["bbox"] == [0.25, 0.25, 0.75, 0.75]
