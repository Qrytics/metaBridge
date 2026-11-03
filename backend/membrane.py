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

from . import debug
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


def _openai_chat(url: str, key: str, model: str, system: str, user: str) -> str | None:
    """Minimal OpenAI-compatible chat call (Baseten / Meta Model API).

    Returns the assistant text or None on any failure (caller falls back).
    """
    import json
    import urllib.request

    payload = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
        }
    ).encode()
    req = urllib.request.Request(
        url.rstrip("/") + "/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            body = json.loads(res.read())
        return body["choices"][0]["message"]["content"]
    except Exception:
        return None


def _live_draft(filename: str, text: str, transform: str) -> str | None:
    debug.log_event("draft", {"model": DRAFT_MODEL, "chars": len(text), "transform": transform})
    key = os.environ.get("BASETEN_API_KEY", "")
    if not key:
        return None
    url = os.environ.get("BASETEN_API_URL", "https://inference.baseten.co/v1")
    out = _openai_chat(
        url, key, DRAFT_MODEL, TRANSPILER_SYSTEM,
        f"filename={filename} transform={transform}\n```\n{text}\n```\n"
        "Reply with ONLY the converted script, no fences.",
    )
    if not out:
        return None
    # Strip accidental fences.
    lines = [ln for ln in out.splitlines() if not ln.strip().startswith("```")]
    return "\n".join(lines).strip() + "\n"


def _meta_json(url: str, key: str, payload: dict, timeout: int = 60) -> dict | None:
    """Generic JSON POST to the Meta Model API. None on any failure."""
    import json
    import urllib.request

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return json.loads(res.read())
    except Exception:
        return None


def _meta_multipart(url: str, key: str, fields: dict, files: dict, timeout: int = 60) -> dict | None:
    """Generic multipart POST (audio/images). Files: {name: (filename, bytes, mime)}."""
    import io
    import json
    import urllib.request
    import uuid

    boundary = uuid.uuid4().hex
    buf = io.BytesIO()
    for k, v in fields.items():
        buf.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    for name, (filename, data, mime) in files.items():
        buf.write(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"'
            f"\r\nContent-Type: {mime}\r\n\r\n".encode() + data + b"\r\n"
        )
    buf.write(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(
        url,
        data=buf.getvalue(),
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return json.loads(res.read())
    except Exception:
        return None


def sam_rip_live(image_b64: str, prompt: str, point: list[float]) -> dict | None:
    debug.log_event("sam-live", {"model": RIP_MODEL, "img_chars": len(image_b64)})
    """Live SAM 3.1 segmentation. Returns {bbox, cutout_png_b64} or None."""
    key = os.environ.get("META_API_KEY", "")
    if not key or not image_b64:
        return None
    base = os.environ.get("META_API_URL", "https://api.meta.ai/v1").rstrip("/")
    url = os.environ.get("META_SAM_URL", base + "/sam-3.1/segment")
    body = _meta_json(url, key, {"model": RIP_MODEL, "image_b64": image_b64, "prompt": prompt, "point": point})
    if not body:
        return None
    bbox = body.get("bbox") or [0.25, 0.25, 0.75, 0.75]
    cutout = body.get("cutout_png_b64") or body.get("mask_rle") or ""
    poly = body.get("polygon")
    out: dict = {"bbox": bbox, "cutout_png_b64": cutout, "model": RIP_MODEL}
    if poly:
        out["polygon"] = poly
    return out


def voice_transcribe_live(wav_bytes: bytes) -> str | None:
    debug.log_event("stt-live", {"model": VOICE_MODEL, "bytes": len(wav_bytes)})
    """Live muse-voice-transcribe (OpenAI-compatible transcriptions). Returns text or None."""
    key = os.environ.get("META_API_KEY", "")
    if not key or not wav_bytes:
        return None
    base = os.environ.get("META_API_URL", "https://api.meta.ai/v1").rstrip("/")
    url = os.environ.get("META_VOICE_URL", base + "/audio/transcriptions")
    body = _meta_multipart(
        url, key,
        {"model": VOICE_MODEL, "response_format": "json"},
        {"file": ("command.wav", wav_bytes, "audio/wav")},
    )
    if not body:
        return None
    return body.get("text") or body.get("transcript")


def restyle_live(image_b64: str, style: str) -> dict | None:
    debug.log_event("restyle-live", {"model": IMAGE_MODEL, "img_chars": len(image_b64)})
    """Live muse-image restyle (OpenAI-compatible images). Returns {image_b64} or None."""
    import base64

    key = os.environ.get("META_API_KEY", "")
    if not key or not image_b64:
        return None
    base = os.environ.get("META_API_URL", "https://api.meta.ai/v1").rstrip("/")
    url = os.environ.get("META_IMAGE_URL", base + "/images/edits")
    try:
        raw = base64.b64decode(image_b64)
    except Exception:
        return None
    body = _meta_multipart(
        url, key,
        {"model": IMAGE_MODEL, "prompt": f"restyle as {style}, high-res game concept art"},
        {"image": ("sprite.png", raw, "image/png")},
    )
    if not body:
        return None
    data = (body.get("data") or [{}])[0]
    img = data.get("b64_json") or ""
    if not img and data.get("url"):
        img = data["url"]  # portal renders URLs too
    if not img:
        return None
    return {"image_b64": img, "style": style, "model": IMAGE_MODEL}


def action_from_transcript(transcript: str) -> str:
    """Keyword-map a transcript onto a cross-OS action (shared live/dev)."""
    t = (transcript or "").lower()
    if "transpile" in t and "mac" not in t and "win" not in t:
        return "transpile-all-scripts"
    if "50" in t or "half" in t or ("straddle" in t and "mac" not in t):
        return "glide-50%-straddle"
    if "screenshot" in t or "mac" in t or "teleport" in t:
        return "slide-window-to-mac+screenshot"
    if "win" in t or "back" in t:
        return "slide-window-to-win"
    return "slide-window-to-mac+screenshot"


def voice_command_live(wav_bytes: bytes) -> dict | None:
    """Full live voice path: transcribe, then map onto an action."""
    text = voice_transcribe_live(wav_bytes)
    if not text:
        return None
    return {"transcript": text, "action": action_from_transcript(text), "model": VOICE_MODEL}


def _live_critic_fix(draft: str, issues: list[str], flavor: str) -> str | None:
    debug.log_event("critic-fix", {"model": CRITIC_MODEL, "issues": issues})
    key = os.environ.get("META_API_KEY", "")
    if not key:
        return None
    url = os.environ.get("META_API_URL", "https://api.meta.ai/v1")
    out = _openai_chat(
        url, key, CRITIC_MODEL, CRITIC_SYSTEM,
        f"flavor={flavor} issues={','.join(issues)}\n```\n{draft}\n```\n"
        "Reply with ONLY the fixed script, no fences.",
    )
    if not out:
        return None
    lines = [ln for ln in out.splitlines() if not ln.strip().startswith("```")]
    return "\n".join(lines).strip() + "\n"


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


def validate_shell(text: str, flavor: str = "sh") -> list[str]:
    """Deterministic validator used before/after the Wonder critic pass."""
    issues: list[str] = []
    lines = text.splitlines()
    if flavor == "sh":
        if not lines or not lines[0].startswith("#!"):
            issues.append("missing-shebang")
        for i, ln in enumerate(lines, 1):
            s = ln.strip()
            if s.startswith("Write-Output "):
                issues.append(f"line-{i}:untranslated-Write-Output")
            if "$env:" in s:
                issues.append(f"line-{i}:untranslated-$env")
        if text.count('"') % 2:
            issues.append("unbalanced-double-quotes")
        if text.count("`") % 2:
            issues.append("unbalanced-backticks")
    elif flavor == "ps1":
        for i, ln in enumerate(lines, 1):
            s = ln.strip()
            if s.startswith("#!/"):
                issues.append(f"line-{i}:shebang-in-ps1")
            if s.startswith("echo "):
                issues.append(f"line-{i}:untranslated-echo")
            if s.startswith("export "):
                issues.append(f"line-{i}:untranslated-export")
        if text.count('"') % 2:
            issues.append("unbalanced-double-quotes")
    else:
        issues.append(f"unknown-flavor:{flavor}")
    return issues


def _auto_fix(text: str, flavor: str) -> str:
    """One deterministic critic-fix pass (dev stand-in for muse-wonder-1.0)."""
    lines = text.splitlines()
    if flavor == "sh":
        if not lines or not lines[0].startswith("#!"):
            lines = ["#!/bin/sh"] + lines
        lines = [
            ln.replace("Write-Output ", "echo ") if ln.strip().startswith("Write-Output ") else ln
            for ln in lines
        ]
        fixed = []
        for ln in lines:
            if "$env:" in ln:
                s = ln.strip()
                if s.startswith("$env:") and "=" in s:
                    k, v = s[len("$env:"):].split("=", 1)
                    fixed.append(f"export {k.strip()}={v.strip()}")
                    continue
            fixed.append(ln)
        return "\n".join(fixed) + "\n"
    if flavor == "ps1":
        fixed = []
        for ln in lines:
            s = ln.strip()
            if s.startswith("#!/"):
                continue
            if s.startswith("echo "):
                fixed.append("Write-Output " + s[5:])
                continue
            if s.startswith("export ") and "=" in s:
                k, v = s[len("export "):].split("=", 1)
                fixed.append(f"$env:{k.strip()} = {v.strip()}")
                continue
            fixed.append(ln)
        return "\n".join(fixed) + "\n"
    return text


def critic_verify(filename: str, draft: str, transform: str) -> dict:
    debug.log_event("critic-verify", {"file": filename, "transform": transform})
    """Validator + Wonder critic loop (dev: deterministic auto-fix passes).

    Returns the verified script plus `ok`, `retries` (<= MAX_CRITIC_RETRIES)
    and human-readable `notes` for the Diff & Critic Inspector modal.
    """
    flavor = "sh" if transform in ("ps1-to-sh", "bat-to-sh") else "ps1" if transform in (
        "sh-to-ps1",
        "sh-to-bat",
    ) else None
    target = filename
    if transform in ("ps1-to-sh", "bat-to-sh"):
        target = filename.rsplit(".", 1)[0] + ".sh"
    elif transform in ("sh-to-ps1", "sh-to-bat"):
        target = filename.rsplit(".", 1)[0] + (".ps1" if transform == "sh-to-ps1" else ".bat")
    if flavor is None:  # none / config-normalize / unknown: nothing to verify
        return {
            "target_name": target,
            "content": draft,
            "ok": True,
            "fixed": False,
            "retries": 0,
            "notes": f"no-critic-needed:{transform}",
        }
    current, retries, fixed = draft, 0, False
    issues = validate_shell(current, flavor)
    while issues and retries < MAX_CRITIC_RETRIES:
        live = None if is_dev() else _live_critic_fix(current, issues, flavor)
        current = live if live else _auto_fix(current, flavor)
        fixed = True
        retries += 1
        issues = validate_shell(current, flavor)
    ok = not issues
    notes = (
        f"{CRITIC_MODEL} critic: {'verified clean' if ok else 'remaining: ' + ','.join(issues)}"
        f" after {retries} retr{'y' if retries == 1 else 'ies'} (dev-fallback)"
    )
    return {
        "target_name": target,
        "content": current,
        "ok": ok,
        "fixed": fixed,
        "retries": retries,
        "notes": notes,
    }


def transpile_with_critic(filename: str, content: bytes, transform: str) -> dict:
    debug.log_event("transpile", {"file": filename, "transform": transform, "bytes": len(content)})
    """Draft (Spark) + critic (Wonder, <=3 retries). Dev = local rewrite."""
    text = content.decode("utf-8", errors="replace")
    live_draft = None if is_dev() else _live_draft(filename, text, transform)
    if transform == "sh-to-ps1":
        draft = live_draft or sh_to_ps1(text)
    elif transform in ("ps1-to-sh", "bat-to-sh"):
        draft = live_draft or ps1_to_sh(text)
    elif transform in ("none", "config-normalize"):
        return {
            "target_name": filename,
            "content_b64": _b64(text.encode("utf-8")),
            "transform": transform,
            "notes": "passthrough",
            "ok": True,
            "retries": 0,
        }
    else:
        return {
            "target_name": filename,
            "content_b64": _b64(text.encode("utf-8")),
            "transform": transform,
            "notes": f"unknown-transform:{transform}; passthrough",
            "ok": True,
            "retries": 0,
        }
    # Prod path would call DRAFT_MODEL then CRITIC_MODEL up to
    # MAX_CRITIC_RETRIES; dev runs the deterministic validator loop.
    verdict = critic_verify(filename, draft, transform)
    return {
        "target_name": verdict["target_name"],
        "content_b64": _b64(verdict["content"].encode("utf-8")),
        "transform": transform,
        "notes": verdict["notes"],
        "ok": verdict["ok"],
        "retries": verdict["retries"],
    }


def sam_rip_fallback(prompt: str) -> dict:
    debug.log_event("sam-served", {"mode": "fallback"})
    """Deterministic dev fallback: center-box pseudo mask + echo cutout."""
    return {
        "bbox": [0.25, 0.25, 0.75, 0.75],
        "cutout_png_b64": _b64(f"metaBridge-dev-cutout:{prompt}".encode()),
        "model": RIP_MODEL,
    }


def voice_fallback(wav: bytes) -> dict:
    debug.log_event("voice-served", {"mode": "fallback", "bytes": len(wav)})
    _ = wav  # validated for 16kHz mono PCM upstream; dev ignores bytes
    return {
        "transcript": "slide the game window to my mac and screenshot the boss",
        "action": "slide-window-to-mac+screenshot",
        "model": VOICE_MODEL,
    }


def restyle_fallback(image_b64: str, style: str) -> dict:
    debug.log_event("restyle-fallback", {"img_chars": len(image_b64)})
    return {"image_b64": image_b64, "style": style, "model": IMAGE_MODEL}
