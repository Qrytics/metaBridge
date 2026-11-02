"""Meta AI Bezel Membrane routers (deterministic ENV=dev fallbacks).

Model IDs (exact):
  draft:  meta-models/muse-spark-open-1026 (Baseten, OpenAI-compatible)
  critic: muse-wonder-1.0 (Meta Model API), MAX_CRITIC_RETRIES = 3
  rip:    sam-3.1 (Meta Model API)
  voice:  muse-voice-transcribe (Meta Model API), 16kHz mono PCM WAV in
  image:  muse-image (Meta Model API)

Static JSON schemas live in the system prompts below (prompt caching).
With ENV=dev (default) or missing keys, every provider returns a
deterministic local fallback with zero network traffic.
"""

import base64
import os

from .bezel import MAX_CRITIC_RETRIES

DRAFT_MODEL = "meta-models/muse-spark-open-1026"
CRITIC_MODEL = "muse-wonder-1.0"
RIP_MODEL = "sam-3.1"
VOICE_MODEL = "muse-voice-transcribe"
IMAGE_MODEL = "muse-image"

FILE_TRANSFER_SCHEMA = (
    '{"type":"object","required":["target_name","content_b64","transform"],'
    '"properties":{"target_name":{"type":"string"},"content_b64":{"type":"string"},'
    '"transform":{"type":"string"},"notes":{"type":"string"}}}'
)
SAM_RIP_SCHEMA = (
    '{"type":"object","required":["bbox","cutout_png_b64"],'
    '"properties":{"bbox":{"type":"array","items":{"type":"number"}},'
    '"cutout_png_b64":{"type":"string"}}}'
)
VOICE_SCHEMA = (
    '{"type":"object","required":["transcript","action"],'
    '"properties":{"transcript":{"type":"string"},"action":{"type":"string"}}}'
)
RESTYLE_SCHEMA = (
    '{"type":"object","required":["image_b64"],'
    '"properties":{"image_b64":{"type":"string"}}}'
)

TRANSPILER_SYSTEM = (
    "You are the MetaBridge bezel file transpiler. Draft model "
    + DRAFT_MODEL
    + ". Convert Windows .ps1/.bat to macOS .sh and back. "
    "Static output schema for prompt caching: " + FILE_TRANSFER_SCHEMA
)
CRITIC_SYSTEM = (
    "You are the MetaBridge transpiler critic (" + CRITIC_MODEL + "). "
    "Verify the draft script is syntactically valid and equivalent. "
    "Static verdict schema for prompt caching: "
    '{"type":"object","required":["ok","fixed","notes"],'
    '"properties":{"ok":{"type":"boolean"},"fixed":{"type":"string"},'
    '"notes":{"type":"string"}}}'
    f" Retry at most {MAX_CRITIC_RETRIES} times."
)


def is_dev() -> bool:
    return os.environ.get("ENV", "dev") != "prod"


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def sh_to_ps1(text: str) -> str:
    """Deterministic dev fallback: minimal .sh -> .ps1 rewrite."""
    out = ["# Transpiled by MetaBridge bezel membrane (dev fallback)"]
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#!"):
            continue
        if s.startswith("echo "):
            out.append("Write-Output " + s[5:])
        elif s.startswith("export "):
            kv = s[len("export "):]
            if "=" in kv:
                k, v = kv.split("=", 1)
                out.append(f"$env:{k} = {v}")
            else:
                out.append("$env:" + kv)
        else:
            out.append(line)
    return "\n".join(out) + "\n"


def ps1_to_sh(text: str) -> str:
    """Deterministic dev fallback: minimal .ps1 -> .sh rewrite."""
    out = ["#!/bin/sh", "# Transpiled by MetaBridge bezel membrane (dev fallback)"]
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            continue
        if s.startswith("Write-Output "):
            out.append("echo " + s[len("Write-Output "):])
        elif s.startswith("$env:"):
            rest = s[len("$env:"):]
            if "=" in rest:
                k, v = rest.split("=", 1)
                out.append(f"export {k.strip()}={v.strip()}")
            else:
                out.append("# " + line)
        else:
            out.append(line)
    return "\n".join(out) + "\n"


def transpile_with_critic(filename: str, content: bytes, transform: str) -> dict:
    """Draft (Spark) + critic (Wonder, <=3 retries). Dev = local rewrite."""
    text = content.decode("utf-8", errors="replace")
    target = filename
    notes = "dev-fallback"
    if transform == "sh-to-ps1":
        fixed = sh_to_ps1(text)
        target = filename.rsplit(".", 1)[0] + ".ps1"
    elif transform == "ps1-to-sh":
        fixed = ps1_to_sh(text)
        target = filename.rsplit(".", 1)[0] + ".sh"
    elif transform in ("none", "config-normalize"):
        fixed = text
    else:
        fixed = text
        notes = f"unknown-transform:{transform}; passthrough"
    # Prod path would call DRAFT_MODEL then CRITIC_MODEL up to
    # MAX_CRITIC_RETRIES; dev short-circuits with the deterministic draft.
    _ = MAX_CRITIC_RETRIES
    return {
        "target_name": target,
        "content_b64": _b64(fixed.encode("utf-8")),
        "transform": transform,
        "notes": notes,
    }


def sam_rip_fallback(prompt: str) -> dict:
    """Deterministic dev fallback: center-box pseudo mask + echo cutout."""
    return {
        "bbox": [0.25, 0.25, 0.75, 0.75],
        "cutout_png_b64": _b64(f"metaBridge-dev-cutout:{prompt}".encode()),
        "model": RIP_MODEL,
    }


def voice_fallback(wav: bytes) -> dict:
    _ = wav  # validated for 16kHz mono PCM upstream; dev ignores bytes
    return {
        "transcript": "slide the game window to my mac and screenshot the boss",
        "action": "slide-window-to-mac+screenshot",
        "model": VOICE_MODEL,
    }


def restyle_fallback(image_b64: str, style: str) -> dict:
    return {"image_b64": image_b64, "style": style, "model": IMAGE_MODEL}
