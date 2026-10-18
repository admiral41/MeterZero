"""Keep the last successful live Gemini run of each kind, for an honest offline fallback.

Demos die on venue Wi-Fi. Every successful live run (investigation, briefing,
logbook reading) is saved here with its time and model. If Gemini isn't reachable,
the UI can show the saved run, clearly labelled as a recording, instead of a blank page.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path


def runs_dir() -> Path:
    return Path(os.environ.get("METERZERO_RUNS", Path(__file__).resolve().parents[1] / "artifacts" / "gemini_runs"))


def save(kind: str, payload: dict, model: str) -> None:
    try:
        path = runs_dir() / f"{kind}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {"kind": kind, "model": model, "recorded_at": time.strftime("%Y-%m-%d %H:%M"), "payload": payload}
        path.write_text(json.dumps(record, default=str, indent=1), encoding="utf-8")
    except OSError:
        pass  # a read-only disk (e.g. some hosting) must never break the live feature


def load(kind: str) -> dict | None:
    path = runs_dir() / f"{kind}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
