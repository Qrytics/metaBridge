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
