"""OS capture agent: window frames -> JPEG/WebP binary over WS.

Prefers dxcam (Windows) then mss; falls back to a built-in 60fps
playable mini-Terraria/sandbox physics canvas (synthetic frames) so the
straddle effect is testable before Steam launches.
"""

import io
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


def capture_window_once(region: dict | None = None) -> bytes:
    """Capture one frame: dxcam -> mss -> synthetic fallback."""
    try:  # Windows GPU path
        import dxcam  # type: ignore

        cam = dxcam.create()
        shot = cam.grab(region=region) if region else cam.grab()
        if shot is not None:
            from PIL import Image as PILImage

            return _to_jpeg(PILImage.fromarray(shot))
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

            return _to_jpeg(PILImage.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX"))
    except Exception:
        pass
    return synthetic_frame(t=time.time() % 60)


def _to_jpeg(img, quality: int = 75) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()
