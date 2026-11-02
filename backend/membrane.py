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
        current = _auto_fix(current, flavor)
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
    """Draft (Spark) + critic (Wonder, <=3 retries). Dev = local rewrite."""
    text = content.decode("utf-8", errors="replace")
    if transform == "sh-to-ps1":
        draft = sh_to_ps1(text)
    elif transform in ("ps1-to-sh", "bat-to-sh"):
        draft = ps1_to_sh(text)
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
