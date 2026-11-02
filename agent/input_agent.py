"""Cross-screen input agent: cursor/keys -> 120Hz WS telemetry.

Tracks (cx, cy) + key state via pynput with safe permission checks
(Quartz CGEventTap on macOS / Win32 hooks may need accessibility
permission; without it we run in synthetic/sim mode). Hands off to
REMOTE_MAC when cx >= W_left - 2 moving right; reverse tunnel maps
macOS clicks/keys back into host game-local coords.
"""

import time
from dataclasses import dataclass, field

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
