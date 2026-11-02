"""Bezel-crossing engine: pure coordinate math (single source of truth).

Left screen (Windows host) has width W_left. A target window at
(win_x, win_y) with size (win_w, win_h) straddles the right bezel when
win_x + win_w > W_left. The right screen (macOS client) renders the
overflow at mac_win_x = win_x - W_left, mac_win_y = win_y (+ H_OFFSET
for vertical alignment when screen heights differ).
"""

from dataclasses import dataclass

CURSOR_OWNER_WIN = "WIN"
CURSOR_OWNER_MAC = "MAC"

#: Pixels from the right edge that trigger the cross-screen handoff.
EDGE_THRESHOLD_PX = 2

#: Max Wonder-critic fix retries for the file-transpiler membrane.
MAX_CRITIC_RETRIES = 3


@dataclass(frozen=True)
class StraddleView:
    straddling: bool
    mac_win_x: int
    mac_win_y: int
    left_visible_w: int
    right_visible_w: int
    straddle_offset_px: int


def vertical_offset(h_left: int, h_right: int) -> int:
    """Centering offset applied to mac_win_y when heights differ."""
    return (h_right - h_left) // 2


def straddle_view(
    win_x: int,
    win_y: int,
    win_w: int,
    win_h: int,  # noqa: ARG001 - kept for symmetric call shape with frontend
    w_left: int,
    h_left: int = 0,
    h_right: int = 0,
) -> StraddleView:
    """Compute the dual-viewport split for a window crossing the bezel."""
    h_offset = vertical_offset(h_left, h_right) if h_left and h_right else 0
    overflow = (win_x + win_w) - w_left
    if overflow <= 0:
        return StraddleView(
            straddling=False,
            mac_win_x=0,
            mac_win_y=win_y + h_offset,
            left_visible_w=win_w,
            right_visible_w=0,
            straddle_offset_px=0,
        )
    left_visible_w = max(0, w_left - win_x)
    return StraddleView(
        straddling=True,
        mac_win_x=win_x - w_left,
        mac_win_y=win_y + h_offset,
        left_visible_w=left_visible_w,
        right_visible_w=overflow,
        straddle_offset_px=overflow,
    )


def cursor_owner(cx: int, w_left: int, threshold: int = EDGE_THRESHOLD_PX) -> str:
    """Which screen owns the cursor. Rightward crossing hands off to MAC."""
    if cx >= w_left - threshold:
        return CURSOR_OWNER_MAC
    return CURSOR_OWNER_WIN


def clamp_cursor(cx: int, cy: int, w: int, h: int) -> tuple[int, int]:
    """Warp/clamp a cursor point into a screen rect."""
    return (max(0, min(cx, w - 1)), max(0, min(cy, h - 1)))


def mac_to_host_game_coords(
    mac_cursor_x: int,
    mac_cursor_y: int,
    mac_win_x: int,
    mac_win_y: int,
    win_w: int,
    win_h: int,
) -> tuple[int, int]:
    """Map a macOS click back to host game-window-local coordinates."""
    gx = max(0, min(mac_cursor_x - mac_win_x, win_w - 1))
    gy = max(0, min(mac_cursor_y - mac_win_y, win_h - 1))
    return (gx, gy)


def drag_handoff(
    cx: int,
    cy: int,  # noqa: ARG001 - kept for symmetric call shape with input packets
    dragging: bool,
    w_left: int,
    threshold: int = EDGE_THRESHOLD_PX,
) -> dict:
    """Cross-bezel drag state: owner flips at the edge, drag survives it.

    A single uninterrupted mouse drag pulls the live window from Windows
    straight onto the Mac desktop: `dragging` stays True across the handoff.
    """
    owner = cursor_owner(cx, w_left, threshold)
    return {
        "owner": owner,
        "dragging": dragging,
        "crossed": bool(dragging and owner == CURSOR_OWNER_MAC),
    }


def viewport_to_frame(
    click_x: float,
    click_y: float,
    view_origin_x: float,
    view_origin_y: float,
    scale: float = 1.0,
) -> tuple[float, float]:
    """Map a viewport click to shared-frame coordinates (SAM rip input).

    view_origin_* is the viewport's top-left corner in frame space
    (0,0 for the left viewport; (mac_win_x, mac_win_y) for the right).
    """
    return (
        (click_x - view_origin_x) * scale,
        (click_y - view_origin_y) * scale,
    )


#: SPAN mode: one world rendered 1:1 across both screens (Eyefinity-style).
SPAN_W = 1920  # == W_LEFT + W_RIGHT, both canvases edge-to-edge
SPAN_WORLD_COLS = 120  # 120 tiles * 16px == SPAN_W, zero stretch


def span_cam_x(player_cx: float, view_w: float, world_w: float) -> float:
    """Camera origin keeping the player centered, clamped to the world."""
    if world_w <= view_w:
        return 0.0
    return max(0.0, min(player_cx - view_w / 2, world_w - view_w))


def span_global_to_world(gx: float, gy: float, y_off: float) -> tuple[float, float]:
    """SPAN mode is 1:1, so global x maps straight onto world x."""
    return (gx, gy - y_off)
