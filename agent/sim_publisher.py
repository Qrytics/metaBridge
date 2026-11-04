"""Controllable fake agent for end-to-end fault injection (test tooling).

Publishes frames exactly like capture.publish_loop (same X-MB-* headers) but
with a chosen size / source / corruption, so a harness can prove the bridge
and portal detect each failure.

    python -m agent.sim_publisher --url http://127.0.0.1:8000/viewport/frame \
        --w 800 --h 450 --fps 30 --src dxcam [--corrupt-every 5] [--seconds 10]
"""

import argparse
import io
import time
import urllib.request

from PIL import Image, ImageDraw


def frame(w: int, h: int, i: int) -> bytes:
    img = Image.new("RGB", (w, h), (20, 30, 60))
    d = ImageDraw.Draw(img)
    for k in range(0, w, 40):  # busy content so the "blank frame" check passes
        d.rectangle([k, (i * 7 + k) % h, k + 30, ((i * 7 + k) % h) + 30], fill=(200, 80 + k % 150, 40))
    d.text((10, 10), f"SIM #{i}", fill=(255, 255, 255))
    b = io.BytesIO()
    img.save(b, format="JPEG", quality=85)
    return b.getvalue()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://127.0.0.1:8000/viewport/frame")
    p.add_argument("--w", type=int, default=800)
    p.add_argument("--h", type=int, default=450)
    p.add_argument("--fps", type=float, default=30)
    p.add_argument("--src", default="dxcam")
    p.add_argument("--win", default="found")
    p.add_argument("--corrupt-every", type=int, default=0, help="every Nth frame is truncated")
    p.add_argument("--blank", action="store_true", help="send flat black frames")
    p.add_argument("--seconds", type=float, default=0, help="0 = until killed")
    p.add_argument("--seq-start", type=int, default=0)
    a = p.parse_args()
    seq, errs, t0 = a.seq_start, 0, time.time()
    while a.seconds == 0 or time.time() - t0 < a.seconds:
        if a.blank:
            b = io.BytesIO()
            Image.new("RGB", (a.w, a.h), (0, 0, 0)).save(b, format="JPEG")
            data = b.getvalue()
        else:
            data = frame(a.w, a.h, seq)
        if a.corrupt_every and seq % a.corrupt_every == a.corrupt_every - 1:
            data = data[: len(data) // 2]
        req = urllib.request.Request(a.url, data=data, method="POST", headers={
            "Content-Type": "image/jpeg", "X-MB-Seq": str(seq), "X-MB-Src": a.src,
            "X-MB-Cap-Ms": "3.0", "X-MB-Errs": str(errs), "X-MB-Win": a.win})
        try:
            urllib.request.urlopen(req, timeout=3).read()
        except Exception:
            errs += 1
        seq += 1
        time.sleep(1.0 / a.fps)


if __name__ == "__main__":
    main()
