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
    "started_at": time.time(),
}
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
async def transfer_file(file: UploadFile, transform: str = "none") -> dict:
    content = await file.read()
    result = membrane.transpile_with_critic(file.filename or "upload.bin", content, transform)
    return result


@app.post("/membrane/sam-rip")
def sam_rip(body: SamRipBody) -> dict:
    if membrane.is_dev():
        return membrane.sam_rip_fallback(body.prompt)
    return membrane.sam_rip_fallback(body.prompt)  # prod wiring point


@app.post("/membrane/voice-command")
async def voice_command(request: Request) -> dict:
    # FFmpeg 16kHz mono PCM WAV precondition enforced by producer;
    # dev fallback validates non-empty and returns canned action.
    body = await request.body()
    if not body:
        return {"transcript": "", "action": "none", "model": membrane.VOICE_MODEL}
    return membrane.voice_fallback(body)


@app.post("/membrane/restyle-asset")
def restyle_asset(body: RestyleBody) -> dict:
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
            msg["server_ts"] = time.time()
            _input_history.append(msg)
            cx = int(msg.get("cx", 0))
            w_left = int(msg.get("w_left", 1920))
            _state["cursor_owner"] = bezel.cursor_owner(cx, w_left)
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
