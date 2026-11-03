"""Cost guards + state reporting for the membrane routers (Stage 3)."""

from fastapi.testclient import TestClient

from backend.main import MAX_IMAGE_B64, MAX_VOICE_BYTES, app

client = TestClient(app)


def test_state_reports_membrane_mode_and_sim_dual():
    body = client.get("/state").json()
    assert body["membrane_mode"] in ("dev", "live")
    assert body["sim_dual"] is False  # only `start.py --sim-dual` opts in


def test_sam_rip_rejects_oversize_image():
    res = client.post(
        "/membrane/sam-rip",
        json={"prompt": "boss", "point": [0.5, 0.5], "image_b64": "a" * (MAX_IMAGE_B64 + 1)},
    )
    assert res.status_code == 413


def test_sam_rip_accepts_small_image():
    res = client.post(
        "/membrane/sam-rip",
        json={"prompt": "boss", "point": [0.5, 0.5], "image_b64": "aGk="},
    )
    assert res.status_code == 200


def test_restyle_rejects_oversize_image():
    res = client.post(
        "/membrane/restyle-asset",
        json={"image_b64": "a" * (MAX_IMAGE_B64 + 1), "style": "concept-art-hd"},
    )
    assert res.status_code == 413


def test_voice_rejects_oversize_body():
    res = client.post("/membrane/voice-command", content=b"R" * (MAX_VOICE_BYTES + 1))
    assert res.status_code == 413


def test_voice_raw_rejects_oversize_body():
    res = client.post("/membrane/voice-command-raw", content=b"R" * (MAX_VOICE_BYTES + 1))
    assert res.status_code == 413
