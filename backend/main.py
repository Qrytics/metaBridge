"""FastAPI + WebSocket bridge server.

Run:  python -m backend.main [--sim-dual] [--port 8000] [--role win|mac]
Sim-dual serves one process driving both viewports for local testing.
"""

import argparse
import time
from collections import deque

from fastapi import FastAPI, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import bezel, membrane

ROLE_WIN = "win"
ROLE_MAC = "mac"

app = FastAPI(title="MetaBridge Bridge Server")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_state = {
    "role": ROLE_WIN,
    "sim_dual": False,
    "cursor_owner": bezel.CURSOR_OWNER_WIN,
    "straddle_offset_px": 0,
    "fps": 60,
    "latency_ms": 1.2,
    "viewers": 0,
    "last_input_ts": 0.0,
    "started_at": time.time(),
}

_last_input: dict = {}


def inbox_dir() -> str:
    import os

    d = os.environ.get("METABRIDGE_INBOX") or os.path.join(
        os.path.expanduser("~"), "MetaBridge-Inbox"
    )
    os.makedirs(d, exist_ok=True)
    return d
_viewport_subs: set[WebSocket] = set()
_input_history: deque = deque(maxlen=240)  # ~2s @120Hz


class SamRipBody(BaseModel):
    prompt: str = Field(default="player character")
    point: list[float] = Field(default=[0.5, 0.5])
    image_b64: str = ""


class RestyleBody(BaseModel):
    image_b64: str = ""
    style: str = "concept-art-hd"


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "metaBridge-bridge"}


@app.get("/state")
def state() -> dict:
    return dict(_state)


@app.post("/membrane/transfer-file")
async def transfer_file(file: UploadFile, transform: str = "none", land: int = 0) -> dict:
    content = await file.read()
    result = membrane.transpile_with_critic(file.filename or "upload.bin", content, transform)
    if land:
        import base64

        raw = base64.b64decode(result["content_b64"])
        dest = inbox_dir()
        name = result["target_name"]
        # Contain the landed file inside the inbox (no path traversal).
        safe = "".join(c for c in name if c.isalnum() or c in "._-") or "upload.bin"
        path = f"{dest}/{safe}"
        with open(path, "wb") as f:
            f.write(raw)
        result["landed_path"] = path
    return result


@app.post("/membrane/sam-rip")
def sam_rip(body: SamRipBody) -> dict:
    if not membrane.is_dev():
        live = membrane.sam_rip_live(body.image_b64, body.prompt, body.point)
        if live:
            return live
    return membrane.sam_rip_fallback(body.prompt)


@app.post("/membrane/voice-command")
async def voice_command(request: Request) -> dict:
    # FFmpeg 16kHz mono PCM WAV precondition enforced by producer;
    # dev fallback validates non-empty and returns canned action.
    body = await request.body()
    if not body:
        return {"transcript": "", "action": "none", "model": membrane.VOICE_MODEL}
    if not membrane.is_dev():
        live = membrane.voice_command_live(body)
        if live:
            return live
    return membrane.voice_fallback(body)


@app.post("/membrane/voice-command-raw")
async def voice_command_raw(request: Request) -> dict:
    """Mic path: accept any recorded audio (e.g. browser MediaRecorder),
    transcode to 16kHz mono PCM WAV via FFmpeg when available, then run the
    voice membrane. Dev fallback when FFmpeg is missing."""
    import shutil
    import subprocess

    body = await request.body()
    if not body:
        return {"transcript": "", "action": "none", "model": membrane.VOICE_MODEL}
    converted = None
    if shutil.which("ffmpeg"):
        try:
            p = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
                 "-ar", "16000", "-ac", "1", "-f", "wav", "pipe:1"],
                input=body, capture_output=True, timeout=20,
            )
            if p.returncode == 0 and p.stdout:
                converted = p.stdout
        except Exception:
            converted = None
    audio = converted or body
    if not membrane.is_dev():
        live = membrane.voice_command_live(audio)
        if live:
            live["received_bytes"] = len(body)
            live["normalized"] = converted is not None
            return live
    out = membrane.voice_fallback(audio)
    out["received_bytes"] = len(body)
    out["normalized"] = converted is not None
    return out


@app.post("/input/event")
async def input_event(request: Request) -> dict:
    """HTTP fallback for agent input telemetry (WS /ws/input preferred)."""
    try:
        event = await request.json()
    except Exception:
        event = {}
    _last_input.clear()
    _last_input.update(event if isinstance(event, dict) else {})
    cx = int(_last_input.get("cx", 0))
    w_left = int(_last_input.get("w_left", 1920))
    _state["cursor_owner"] = bezel.cursor_owner(cx, w_left)
    _state["last_input_ts"] = time.time()
    return {"owner": _state["cursor_owner"]}


@app.post("/membrane/restyle-asset")
def restyle_asset(body: RestyleBody) -> dict:
    if not membrane.is_dev():
        live = membrane.restyle_live(body.image_b64, body.style)
        if live:
            return live
    return membrane.restyle_fallback(body.image_b64, body.style)


@app.websocket("/ws/viewport")
async def ws_viewport(ws: WebSocket) -> None:
    """Live viewport bus: binary JPEG/WebP from a publisher (agent) is
    rebroadcast to every other subscriber; text frames get a tick reply."""
    await ws.accept()
    _viewport_subs.add(ws)
    _state["viewers"] = len(_viewport_subs)
    try:
        while True:
            msg = await ws.receive()
            if msg.get("bytes") is not None:
                await broadcast_frame(msg["bytes"], exclude=ws)
            elif msg.get("text") is not None:
                await ws.send_json({"tick": time.time()})
            elif msg.get("type") == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    finally:
        _viewport_subs.discard(ws)
        _state["viewers"] = len(_viewport_subs)


async def broadcast_frame(payload: bytes, exclude: WebSocket | None = None) -> None:
    dead = []
    for ws in list(_viewport_subs):
        if ws is exclude:
            continue
        try:
            await ws.send_bytes(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _viewport_subs.discard(ws)
    _state["viewers"] = len(_viewport_subs)


@app.post("/viewport/frame")
async def viewport_frame(request: Request) -> dict:
    """HTTP publisher path for agent/capture.py::publish_loop."""
    body = await request.body()
    if body:
        await broadcast_frame(body)
    return {"viewers": len(_viewport_subs), "bytes": len(body)}


@app.websocket("/ws/input")
async def ws_input(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            msg = await ws.receive_json()
            if "ping" in msg:  # latency probe: echo for RTT measurement
                await ws.send_json({"pong": msg["ping"], "server_ts": time.time()})
                continue
            msg["server_ts"] = time.time()
            _input_history.append(msg)
            cx = int(msg.get("cx", 0))
            w_left = int(msg.get("w_left", 1920))
            _state["cursor_owner"] = bezel.cursor_owner(cx, w_left)
            _state["last_input_ts"] = time.time()
            await ws.send_json({"owner": _state["cursor_owner"]})
    except WebSocketDisconnect:
        pass


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--sim-dual", action="store_true")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--role", default=ROLE_WIN, choices=[ROLE_WIN, ROLE_MAC])
    args = parser.parse_args()
    _state["role"] = args.role
    _state["sim_dual"] = args.sim_dual
    uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
