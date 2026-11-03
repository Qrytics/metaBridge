"""Cross-screen input agent: cursor/keys -> 120Hz WS telemetry.

Tracks (cx, cy) + key state via pynput with safe permission checks
(Quartz CGEventTap on macOS / Win32 hooks may need accessibility
permission; without it we run in synthetic/sim mode). Hands off to
REMOTE_MAC when cx >= W_left - 2 moving right; reverse tunnel maps
macOS clicks/keys back into host game-local coords.
"""

import time
from dataclasses import dataclass, field
from .diag import log as diag_log

try:
    from pynput import keyboard, mouse  # type: ignore
except Exception:  # pragma: no cover - optional dep
    keyboard = None
    mouse = None

from backend.bezel import (
    CURSOR_OWNER_MAC,
    CURSOR_OWNER_WIN,
    clamp_cursor,
    cursor_owner,
    mac_to_host_game_coords,
)

HZ = 120


@dataclass
class InputAgent:
    w_left: int = 1920
    h_left: int = 1080
    cx: int = 960
    cy: int = 540
    owner: str = CURSOR_OWNER_WIN
    keys: set = field(default_factory=set)
    buttons: int = 0
    permitted: bool = False

    def check_permissions(self) -> bool:
        """Probe OS hooks; False -> synthetic/sim mode (never raises)."""
        if keyboard is None or mouse is None:
            self.permitted = False
            return False
        try:
            k = keyboard.Listener(on_press=lambda e: None)
            k.start()
            k.stop()
            self.permitted = True
        except Exception:
            self.permitted = False
        return self.permitted

    def on_move(self, dx: int, dy: int) -> dict:
        self.cx += dx
        self.cy += dy
        prev = self.owner
        # Clamp locally while WIN owns; MAC side clamps remotely.
        if self.owner == CURSOR_OWNER_WIN:
            self.cx, self.cy = clamp_cursor(self.cx, self.cy, self.w_left, self.h_left)
        self.owner = cursor_owner(self.cx, self.w_left)
        crossed = prev == CURSOR_OWNER_WIN and self.owner == CURSOR_OWNER_MAC
        return self.packet(crossed_edge=crossed)

    def on_key(self, key: str, down: bool) -> dict:
        if down:
            self.keys.add(key)
        else:
            self.keys.discard(key)
        return self.packet()

    def packet(self, crossed_edge: bool = False) -> dict:
        return {
            "cx": self.cx,
            "cy": self.cy,
            "dx": 0,
            "dy": 0,
            "buttons": self.buttons,
            "keys": sorted(self.keys),
            "owner": self.owner,
            "w_left": self.w_left,
            "crossed_edge": crossed_edge,
            "ts": time.time(),
        }

    def reverse_to_game(
        self,
        mac_x: int,
        mac_y: int,
        mac_win_x: int,
        mac_win_y: int,
        win_w: int,
        win_h: int,
    ) -> dict:
        gx, gy = mac_to_host_game_coords(mac_x, mac_y, mac_win_x, mac_win_y, win_w, win_h)
        return {"game_x": gx, "game_y": gy, "keys": sorted(self.keys)}

    def attach_hooks(self) -> bool:
        """Attach OS mouse/keyboard hooks. False -> synthetic mode (no raise).

        macOS needs Accessibility permission for the process; Windows hooks
        need no elevation for SendInput-level capture via pynput.
        """
        if keyboard is None or mouse is None:
            return False
        try:
            ml = mouse.Listener(
                on_move=lambda x, y: self.on_move_to(x, y),
                on_click=lambda x, y, btn, pressed: self.on_click(btn, pressed),
            )
            kl = keyboard.Listener(
                on_press=lambda k: self.on_key(self._keyname(k), True),
                on_release=lambda k: self.on_key(self._keyname(k), False),
            )
            ml.start()
            kl.start()
            self.permitted = True
            return True
        except Exception:
            self.permitted = False
            return False

    @staticmethod
    def _keyname(k) -> str:
        try:
            return k.char.lower() if getattr(k, "char", None) else str(k).replace("Key.", "")
        except Exception:
            return "unknown"

    def on_move_to(self, x: int, y: int) -> dict:
        dx, dy = x - self.cx, y - self.cy
        self.cx, self.cy = x, y
        prev = self.owner
        self.owner = cursor_owner(self.cx, self.w_left)
        return self.packet(crossed_edge=prev == CURSOR_OWNER_WIN and self.owner == CURSOR_OWNER_MAC)

    def on_click(self, btn, pressed: bool) -> dict:
        self.buttons = 1 if pressed else 0
        return self.packet()

    def stream_loop(
        self,
        bridge: str = "http://localhost:8000",
        hz: float = 120.0,
        duration: float | None = None,
    ) -> int:
        """Publish live input telemetry at `hz` with reconnects.

        Prefers WS /ws/input; falls back to HTTP POST /input/event when the
        `websockets` package (or the socket) is unavailable.
        """
        import json as _json
        import time as _time
        import urllib.request

        try:
            import asyncio as _asyncio

            import websockets as _ws  # type: ignore

            use_ws = True
        except Exception:
            use_ws = False

        def _post(event: dict) -> dict:
            req = urllib.request.Request(
                bridge.rstrip("/") + "/input/event",
                data=_json.dumps(event).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=5) as res:
                    return _json.loads(res.read() or b"{}")
            except Exception:
                return {}

        period, sent, start = 1.0 / max(1.0, hz), 0, _time.time()
        if use_ws:
            async def _run() -> int:
                n = 0
                while True:
                    try:
                        async with _ws.connect(
                            bridge.replace("http", "ws").rstrip("/") + "/ws/input"
                        ) as sock:
                            while True:
                                await sock.send(_json.dumps(self.packet()))
                                try:
                                    reply = await _asyncio.wait_for(sock.recv(), timeout=period)
                                    _ = _json.loads(reply) if isinstance(reply, str) else None
                                except Exception:
                                    pass
                                n += 1
                                if duration is not None and _time.time() - start >= duration:
                                    return n
                                await _asyncio.sleep(period)
                    except Exception:
                        if duration is not None and _time.time() - start >= duration:
                            return n
                        diag_log("input-ws-reconnect", {})
                        await _asyncio.sleep(1.0)  # reconnect backoff
                return n

            return _asyncio.run(_run())
        while True:  # HTTP fallback path
            _post(self.packet())
            sent += 1
            if duration is not None and _time.time() - start >= duration:
                break
            _time.sleep(period)
        return sent
