import base64

from fastapi.testclient import TestClient

from backend import bezel
from backend.main import app
from backend.membrane import ps1_to_sh, sh_to_ps1

client = TestClient(app)


def test_no_straddle_when_fully_left():
    v = bezel.straddle_view(100, 50, 800, 600, 1920)
    assert not v.straddling
    assert v.right_visible_w == 0
    assert v.left_visible_w == 800
    assert v.straddle_offset_px == 0


def test_straddle_math_mac_win_x():
    # Window 200px over the right bezel of a 1920 left screen.
    v = bezel.straddle_view(1720, 100, 400, 300, 1920)
    assert v.straddling
    assert v.mac_win_x == 1720 - 1920  # == -200
    assert v.mac_win_y == 100
    assert v.left_visible_w == 1920 - 1720  # 200
    assert v.right_visible_w == (1720 + 400) - 1920  # 200
    assert v.straddle_offset_px == 200


def test_straddle_touching_edge_not_straddling():
    v = bezel.straddle_view(1120, 0, 800, 600, 1920)
    assert not v.straddling
    assert v.mac_win_x == 0


def test_vertical_offset_centers():
    assert bezel.vertical_offset(1080, 1200) == 60
    v = bezel.straddle_view(1800, 100, 400, 300, 1920, 1080, 1200)
    assert v.mac_win_y == 160


def test_cursor_handoff_at_edge():
    assert bezel.cursor_owner(1918, 1920) == "MAC"
    assert bezel.cursor_owner(1917, 1920) == "WIN"
    assert bezel.cursor_owner(100, 1920) == "WIN"


def test_clamp_cursor():
    assert bezel.clamp_cursor(9999, -5, 1920, 1080) == (1919, 0)


def test_reverse_game_input_mapping():
    # mac_win at (-200, 100), 400x300 game; click at mac (50, 150) -> (250, 50)
    gx, gy = bezel.mac_to_host_game_coords(50, 150, -200, 100, 400, 300)
    assert (gx, gy) == (250, 50)
    # Clamped at edges
    gx, gy = bezel.mac_to_host_game_coords(-5000, 9999, -200, 100, 400, 300)
    assert (gx, gy) == (0, 299)


def test_membrane_sh_to_ps1_dev():
    out = sh_to_ps1("#!/bin/sh\necho hi\nexport FOO=bar\n")
    assert "Write-Output hi" in out
    assert "$env:FOO = bar" in out


def test_membrane_ps1_to_sh_dev():
    out = ps1_to_sh("Write-Output hi\n$env:FOO = bar\n")
    assert "echo hi" in out
    assert "export FOO=bar" in out


def test_transfer_file_endpoint_transpiles():
    res = client.post(
        "/membrane/transfer-file?transform=sh-to-ps1",
        files={"file": ("setup.sh", b"#!/bin/sh\necho hi\n")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["target_name"] == "setup.ps1"
    assert "Write-Output hi" in base64.b64decode(body["content_b64"]).decode()


def test_sam_rip_endpoint_dev():
    res = client.post("/membrane/sam-rip", json={"prompt": "boss", "point": [0.5, 0.5]})
    assert res.status_code == 200
    assert res.json()["bbox"] == [0.25, 0.25, 0.75, 0.75]


def test_voice_endpoint_dev():
    res = client.post("/membrane/voice-command", content=b"RIFF....fake-wav")
    assert res.status_code == 200
    assert res.json()["action"] == "slide-window-to-mac+screenshot"


def test_state_and_health():
    assert client.get("/health").json()["ok"] is True
    assert "cursor_owner" in client.get("/state").json()
