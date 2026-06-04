"""Phase state machine — INCEPTION → CONSTRUCTION → OPERATION.

State file: ~/.hermes/ai-dlc/phase.json
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

VALID_PHASES = ["INCEPTION", "CONSTRUCTION", "OPERATION"]

# Define allowed transitions
TRANSITIONS = {
    "INCEPTION": ["CONSTRUCTION"],
    "CONSTRUCTION": ["OPERATION"],
    "OPERATION": [],
}


def _home() -> Path:
    """Resolve HOME at call time to avoid stale module-level Path.home()."""
    return Path(os.path.expanduser("~"))


def _state_dir() -> Path:
    return _home() / ".hermes" / "ai-dlc"


def _phase_file() -> Path:
    return _state_dir() / "phase.json"


def _ensure_dir():
    os.makedirs(_state_dir(), exist_ok=True)


def _read_phase() -> dict:
    """Read phase state from file."""
    _ensure_dir()
    phase_file = _phase_file()
    if not phase_file.exists():
        return {
            "phase": None,
            "history": [],
            "current_phase_start": None,
        }
    try:
        return json.loads(phase_file.read_text())
    except (json.JSONDecodeError, OSError):
        return {"phase": None, "history": [], "current_phase_start": None}


def _write_phase(data: dict):
    """Atomic write phase state."""
    _ensure_dir()
    fd, tmp = tempfile.mkstemp(dir=str(_state_dir()), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, default=str)
            f.flush()
            os.fsync(fd)
        os.replace(tmp, str(_phase_file()))
    except Exception:
        os.unlink(tmp)
        raise


def get_phase() -> Optional[str]:
    """Get current phase. Returns None if not set."""
    data = _read_phase()
    return data.get("phase")


def set_phase(phase: str, reason: str = "") -> dict:
    """Set phase directly (for migration/admin)."""
    if phase not in VALID_PHASES:
        return {"ok": False, "error": f"Invalid phase: {phase}. Valid: {VALID_PHASES}"}

    data = _read_phase()
    old = data.get("phase")
    now = datetime.now(timezone.utc).isoformat()

    entry = {
        "from": old,
        "to": phase,
        "timestamp": now,
        "reason": reason or f"Set to {phase}",
    }

    data["phase"] = phase
    data.setdefault("history", []).append(entry)
    data["current_phase_start"] = now
    _write_phase(data)

    return {"ok": True, "phase": phase, "old": old}


def promote_phase() -> dict:
    """Promote to next phase. Returns result dict."""
    current = get_phase()
    if current is None:
        return {"ok": False, "error": "No phase set. Use set_phase('INCEPTION') first."}

    next_phases = TRANSITIONS.get(current, [])
    if not next_phases:
        return {"ok": False, "error": f"Cannot promote from {current} — already at terminal phase"}

    next_phase = next_phases[0]
    return set_phase(next_phase, reason=f"Promoted from {current}")


def can_write_in_phase(phase: Optional[str], file_path: str) -> tuple:
    """Check if writing this file type is allowed in current phase.

    Returns:
        (allowed: bool, reason: str)
    """
    if phase is None:
        return True, "no phase set"

    # Detect file type
    ext = os.path.splitext(file_path)[1].lower()

    if phase == "INCEPTION":
        code_exts = {".py", ".rs", ".ts", ".js", ".tsx", ".jsx", ".go", ".java",
                     ".c", ".cpp", ".swift", ".kt", ".rb"}
        if ext in code_exts:
            return False, "INCEPTION phase: write specs/requirements, not code"
        return True, "INCEPTION: spec files allowed"

    if phase == "CONSTRUCTION":
        return True, "CONSTRUCTION: code writing allowed"

    if phase == "OPERATION":
        config_exts = {".yaml", ".yml", ".json", ".toml"}
        if ext in config_exts:
            return True, "OPERATION: config changes allowed"
        return True, "OPERATION: hotfix allowed (but prefer CI/CD)"

    return True, "unknown phase — allowing"


def get_status() -> dict:
    """Get full phase status for display."""
    data = _read_phase()
    return {
        "phase": data.get("phase"),
        "history": data.get("history", []),
        "current_phase_start": data.get("current_phase_start"),
        "valid_phases": VALID_PHASES,
        "transitions": TRANSITIONS,
    }
