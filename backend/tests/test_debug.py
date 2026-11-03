"""Flight recorder: events, client notes, transfer log, bundle download."""

import io
import zipfile

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def _tmpdir(tmp_path, monkeypatch):
    monkeypatch.setenv("METABRIDGE_DEBUG_DIR", str(tmp_path))
    monkeypatch.setenv("ENV", "dev")


def test_client_note_and_events(tmp_path, monkeypatch):
    _tmpdir(tmp_path, monkeypatch)
    r = client.post(
        "/debug/client",
        json={"hud": {"owner": "WIN"}, "log": ["boot"], "shot": ""},
    )
    assert r.status_code == 200
    assert r.json()["stored"] == "ok-no-shot"
    kinds = [e["kind"] for e in client.get("/debug/events?limit=50").json()["events"]]
    assert "client" in kinds


def test_client_note_rejects_oversize(tmp_path, monkeypatch):
    _tmpdir(tmp_path, monkeypatch)
    r = client.post("/debug/client", content=b"x" * 3_000_001)
    assert r.status_code == 413


def test_transfer_is_recorded(tmp_path, monkeypatch):
    _tmpdir(tmp_path, monkeypatch)
    r = client.post(
        "/membrane/transfer-file?transform=ps1-to-sh",
        files={"file": ("a.ps1", b'Write-Output "x"\n')},
    )
    assert r.status_code == 200
    kinds = [e["kind"] for e in client.get("/debug/events?limit=200").json()["events"]]
    assert "transfer" in kinds and "transpile" in kinds


def test_bundle_is_zip(tmp_path, monkeypatch):
    _tmpdir(tmp_path, monkeypatch)
    client.post("/debug/client", json={"hud": {}, "log": [], "shot": ""})
    r = client.get("/debug/bundle")
    assert r.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert "events.jsonl" in names and "state.json" in names
