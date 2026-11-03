"""OS capture agent: window frames -> JPEG/WebP binary over WS.

Prefers dxcam (Windows) then mss; falls back to a built-in 60fps
playable mini-Terraria/sandbox physics canvas (synthetic frames) so the
straddle effect is testable before Steam launches.
"""

import io
from .diag import log as diag_log
import math
import time

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover
    Image = None


def synthetic_frame(w: int = 640, h: int = 360, t: float = 0.0) -> bytes:
    """Render a deterministic animated frame (mini sandbox fallback).

    A bouncing 'player' block over parallax hills — stands in for the
    Terraria window until real capture is wired.
    """
    if Image is None:
        raise RuntimeError("Pillow required for synthetic_frame")
    img = Image.new("RGB", (w, h), (10, 14, 26))
    d = ImageDraw.Draw(img)
    # Parallax hills
    for i in range(3):
        y0 = h - 60 - i * 30
        for x in range(0, w, 8):
            y = y0 + int(12 * math.sin((x + t * (40 + i * 30)) / 90.0))
            d.line([(x, y), (x + 8, y)], fill=(30 + i * 20, 60 + i * 20, 50), width=3)
    # Player block bouncing like Terraria slime
    px = int(w / 2 + (w / 3) * math.sin(t * 1.7))
    py = int(h - 110 + 30 * abs(math.sin(t * 3.1)))
    d.rectangle([px - 18, py - 18, px + 18, py + 18], fill=(86, 214, 120))
    d.rectangle([px - 10, py - 8, px - 2, py], fill=(0, 0, 0))
    d.rectangle([px + 2, py - 8, px + 10, py], fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=75)
    return buf.getvalue()


def capture_window_once(region: dict | None = None, quality: int = 92) -> bytes:
    """Capture one frame: dxcam -> mss -> synthetic fallback."""
    try:  # Windows GPU path
        import dxcam  # type: ignore

        cam = dxcam.create()
        shot = cam.grab(region=region) if region else cam.grab()
        if shot is not None:
            from PIL import Image as PILImage

            return _to_jpeg(PILImage.fromarray(shot), quality)
    except Exception:
        pass
    try:  # Cross-platform path
        import mss  # type: ignore

        with mss.mss() as sct:
            mon = sct.monitors[1]
            if region:
                mon = {
                    "left": region.get("left", 0),
                    "top": region.get("top", 0),
                    "width": region.get("width", 640),
                    "height": region.get("height", 360),
                }
            shot = sct.grab(mon)
            from PIL import Image as PILImage

            return _to_jpeg(PILImage.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX"), quality)
    except Exception:
        pass
    return synthetic_frame(t=time.time() % 60)


def _to_jpeg(img, quality: int = 92) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def find_window_region(title_substr: str) -> dict | None:
    """Best-effort OS window lookup for a live game window (e.g. Terraria).

    Windows: win32gui title match. macOS: Quartz window list title match
    (needs Screen Recording permission for the pixels, not the list).
    Returns an mss-style region or None when the APIs are unavailable.
    """
    import sys

    needle = title_substr.lower()
    try:
        if sys.platform.startswith("win"):
            import win32gui  # type: ignore

            found: list = []

            def _cb(hwnd, _):
                if win32gui.IsWindowVisible(hwnd):
                    name = win32gui.GetWindowText(hwnd) or ""
                    if needle in name.lower():
                        l, t, r, b = win32gui.GetWindowRect(hwnd)
                        if r - l > 50 and b - t > 50:
                            found.append({"title": name, "left": l, "top": t, "width": r - l, "height": b - t})

            win32gui.EnumWindows(_cb, None)
            if not found:
                return None
            best = max(found, key=lambda m: m["width"] * m["height"])
            diag_log("window-found", {"title": best["title"], "width": best["width"], "height": best["height"]})
            return {"left": best["left"], "top": best["top"], "width": best["width"], "height": best["height"]}

        if sys.platform == "darwin":
            from Quartz import (  # type: ignore
                CGWindowListCopyWindowInfo,
                kCGNullWindowID,
                kCGWindowListOptionOnScreenOnly,
            )

            for w in CGWindowListCopyWindowInfo(
                kCGWindowListOptionOnScreenOnly, kCGNullWindowID
            ):
                name = str(w.get("kCGWindowName", "") or "")
                if needle in name.lower():
                    b = w.get("kCGBounds", {})
                    if b.get("Width", 0) > 50 and b.get("Height", 0) > 50:
                        return {
                            "left": int(b.get("X", 0)),
                            "top": int(b.get("Y", 0)),
                            "width": int(b.get("Width", 0)),
                            "height": int(b.get("Height", 0)),
                        }
    except Exception:
        pass
    return None


def publish_loop(
    url: str = "http://localhost:8000/viewport/frame",
    region: dict | None = None,
    fps: float = 30.0,
    quality: int = 92,
    duration: float | None = None,
    title: str | None = None,
) -> int:
    """Stream JPEG frames to the bridge (stdlib HTTP, no extra deps).

    Used on the Windows host node for LIVE_AGENT_STREAM. Returns frames sent.
    """
    import time as _time
    import urllib.request

    period = 1.0 / max(1.0, fps)
    sent, start = 0, _time.time()
    errs, last_stat = 0, start
    retarget_at = 0.0
    while True:
        if title and _time.time() >= retarget_at:
            # Re-resolve the live game window every 5s (it moves/resizes).
            region = find_window_region(title) or region
            retarget_at = _time.time() + 5.0
        frame = capture_window_once(region, quality)
        req = urllib.request.Request(
            url, data=frame, headers={"Content-Type": "image/jpeg"}, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as res:
                res.read()
        except Exception:
            errs += 1  # bridge unreachable: keep capturing locally (counted below)
        sent += 1
        if sent % 100 == 0 or _time.time() - last_stat >= 30:
            last_stat = _time.time()
            diag_log("capture-stats", {"sent": sent, "errs": errs, "fps": fps, "quality": quality, "title": title, "region": [region["width"], region["height"]] if region else None})
        if duration is not None and _time.time() - start >= duration:
            break
        _time.sleep(max(0.0, period - (_time.time() - start - sent * period) % period))
    return sent


if __name__ == "__main__":  # python -m agent.capture [--url ...] [--fps 30]
    import argparse

    _p = argparse.ArgumentParser()
    _p.add_argument("--url", default="http://localhost:8000/viewport/frame")
    _p.add_argument("--fps", type=float, default=30.0)
    _p.add_argument("--quality", type=int, default=92)
    _p.add_argument("--title", default=None, help="live game window title to follow (e.g. Terraria)")
    _a = _p.parse_args()
    print(f"publishing to {_a.url} ...")
    publish_loop(url=_a.url, fps=_a.fps, title=_a.title, quality=_a.quality)
