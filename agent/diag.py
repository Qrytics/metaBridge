"""Append-only JSONL diagnostics for the host agent.

Shares METABRIDGE_DEBUG_DIR with the bridge flight recorder so one
/debug/bundle download covers the whole live run.
"""

import json
import os
import tempfile
import time


def log(kind: str, data: dict | None = None) -> None:
    if "PYTEST_CURRENT_TEST" in os.environ and not os.environ.get("METABRIDGE_DEBUG_DIR"):
        d = os.path.join(tempfile.gettempdir(), "MetaBridge-Debug-test")
    else:
        d = os.environ.get("METABRIDGE_DEBUG_DIR") or os.path.join(
            os.path.expanduser("~"), "MetaBridge-Debug"
        )
    try:
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "agent.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "kind": kind, "data": data or {}}) + "\n")
    except OSError:
        pass
