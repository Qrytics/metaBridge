"""Stage 2: cross-bezel drag handoff, critic verification, SAM coord mapping."""

from fastapi.testclient import TestClient

from backend import bezel, membrane
from backend.main import app

client = TestClient(app)

W = 960


def test_drag_handoff_sweep_keeps_drag_alive():
    # Sweep a pressed mouse from WIN deep across the bezel.
    states = [bezel.drag_handoff(cx, 300, True, W) for cx in (100, 800, 957, 958, 1000, 1400)]
    assert all(s["dragging"] for s in states)
    assert states[0]["owner"] == "WIN" and not states[0]["crossed"]
    assert states[2]["owner"] == "WIN"  # 957 < 958: still WIN
    assert states[3]["owner"] == "MAC" and states[3]["crossed"]
    assert states[5]["owner"] == "MAC" and states[5]["crossed"]
    # Release on the MAC side: drag ends, ownership stays MAC.
    drop = bezel.drag_handoff(1000, 300, False, W)
    assert drop == {"owner": "MAC", "dragging": False, "crossed": False}


def test_drag_back_to_win():
    assert bezel.drag_handoff(1100, 300, True, W)["owner"] == "MAC"
    assert bezel.drag_handoff(400, 300, True, W)["owner"] == "WIN"


def test_critic_verifies_ps1_to_sh_with_retries():
    draft = 'Write-Output "deploying..."\n$env:APP_PORT = 8080\n'
    verdict = membrane.critic_verify("deploy_server.ps1", draft, "ps1-to-sh")
    assert verdict["target_name"] == "deploy_server.sh"
    assert verdict["ok"] is True
    assert verdict["retries"] <= membrane.MAX_CRITIC_RETRIES
    assert membrane.validate_shell(verdict["content"], "sh") == []
    assert "echo" in verdict["content"] and "export APP_PORT" in verdict["content"]


def test_validator_catches_untranslated_ps1():
    issues = membrane.validate_shell('Write-Output hi\n$env:X = 1\n', "sh")
    assert any("Write-Output" in i for i in issues)
    assert any("$env" in i for i in issues)


def test_transfer_ps1_end_to_end_critic_pass():
    res = client.post(
        "/membrane/transfer-file?transform=ps1-to-sh",
        files={"file": ("deploy_server.ps1", b'Write-Output "x"\n$env:A = 1\n')},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["target_name"] == "deploy_server.sh"
    assert body["ok"] is True
    assert body["retries"] <= 3


def test_sam_click_maps_through_straddled_viewport():
    # Window straddles: mac_win_x = 720 - 960 = -240. Click at MAC local
    # (50, 150) must resolve to the same shared-frame point as the
    # equivalent WIN-side global click (1010, 150).
    v = bezel.straddle_view(720, 100, 480, 320, W)
    assert v.mac_win_x == -240
    fx_mac, fy_mac = bezel.viewport_to_frame(50, 150, v.mac_win_x, v.mac_win_y)
    fx_win, fy_win = bezel.viewport_to_frame(1010, 150, 0, 0)
    assert (fx_mac, fy_mac) == (290, 50)
    assert (fx_win, fy_win) == (1010, 150)
    # Frame-normalized SAM point prompt stays inside the frame.
    nx, ny = fx_mac / 480, fy_mac / 288
    assert 0 <= nx <= 1 and 0 <= ny <= 1


def test_viewport_frame_publish_endpoint():
    res = client.post("/viewport/frame", content=b"\xff\xd8fake-jpeg")
    assert res.status_code == 200
    assert res.json()["bytes"] == 11


def test_viewport_ws_binary_broadcast():
    with client.websocket_connect("/ws/viewport") as viewer:
        with client.websocket_connect("/ws/viewport") as publisher:
            publisher.send_bytes(b"\xff\xd8frame-1")
            assert viewer.receive_bytes() == b"\xff\xd8frame-1"
            viewer.send_text("ping")
            assert viewer.receive_json()["tick"] >= 0
