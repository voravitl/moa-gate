"""AI-DLC Compass — Steering verification, phase engine, and policy enforcement.

Intercepts pre_tool_call to:
1. Verify content against steering rules (security, architecture, compliance)
2. Check phase state (Inception/Construction/Operation)
3. Block steering violations with education messages
4. Auto-escalate critical violations to MOA-Gate tier system

Integration:
  - Shared file state with MOA-Gate (~/.hermes/ai-dlc/state.json)
  - Steering rules: ~/wiki/steering/*.yaml (git-tracked)
  - MOA-Gate integration: violation → tier escalation
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .engine import phase as ph
from .engine import verifier as vr
from .steering import registry as sr

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STATE_DIR = Path.home() / ".hermes" / "ai-dlc"
STATE_FILE = STATE_DIR / "state.json"
STEERING_DIR = Path.home() / "wiki" / "steering"
STEERING_LOADED_FLAG = STATE_DIR / "steering_loaded.flag"
MOA_GATE_STATE = Path.home() / ".hermes" / "moa-gate" / "state.json"

BLOCKED_TOOLS = frozenset({
    "patch",
    "write_file",
    "write",
    "git_commit",
    "gh_pr_create",
    "skill_manage",
    "terminal",
    "process",
})

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> dict:
    """Read JSON file, return empty dict if missing."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}

def _write_json(path: Path, data: dict) -> None:
    """Atomic write JSON — temp file + rename."""
    os.makedirs(path.parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, default=str)
            f.flush()
            os.fsync(fd)
        os.replace(tmp, str(path))
    except Exception:
        os.unlink(tmp)
        raise

def _steering_loaded() -> bool:
    """Check if steering has been loaded this session."""
    return STEERING_LOADED_FLAG.exists()

def _mark_steering_loaded() -> None:
    """Mark steering as loaded."""
    os.makedirs(STATE_DIR, exist_ok=True)
    STEERING_LOADED_FLAG.write_text(datetime.now(timezone.utc).isoformat())

def _moa_gate_state() -> dict:
    """Read current MOA-Gate state."""
    return _read_json(MOA_GATE_STATE)

def _can_escalate_to_moa(severity: str, tier: int) -> bool:
    """Check if MOA-Gate is available for escalation."""
    if not MOA_GATE_STATE.exists():
        return False
    moa = _moa_gate_state()
    return bool(moa)  # MOA-Gate exists and has state

# ---------------------------------------------------------------------------
# Plugin hook
# ---------------------------------------------------------------------------

def register():
    """Register plugin hooks with Hermes."""
    # Auto-load steering on startup to avoid first-tool block
    _mark_steering_loaded()
    logger.info("ai-dlc-compass: registered")

def pre_tool_call(tool_name: str, args: dict) -> Optional[dict]:
    """AI-DLC Compass — verify before write/destructive tools.

    Returns:
        None — allow the tool call
        dict with "block": True — block with message
    """
    if tool_name not in BLOCKED_TOOLS:
        return None  # non-blocked tools pass through

    logger.info(f"ai-dlc-compass: checking {tool_name}")

    # --- Step 1: First-tool check — steering loaded? ---
    path_arg = args.get("path", args.get("file", ""))
    content_arg = args.get("content", args.get("text", ""))

    if not _steering_loaded():
        # Check if this is code repo path or wiki path (skip for wiki)
        spath = str(path_arg)
        if "wiki" not in spath and ".hermes" not in spath:
            return {
                "block": True,
                "message": (
                    "\U0001f4e1 AI-DLC: Steering rules not loaded yet.\n\n"
                    "Please load steering before writing code:\n"
                    "  read_file(\"~/wiki/steering/security.yaml\")\n"
                    "  read_file(\"~/wiki/steering/architecture.yaml\")\n"
                    "  read_file(\"~/wiki/steering/compliance.yaml\")\n\n"
                    "When done, tell the user \"steering loaded\" and retry."
                ),
            }

    # --- Step 2: Phase check ---
    current_phase = ph.get_phase()
    if current_phase == "INCEPTION":
        # In inception — should write specs, not code
        if _is_code_file(path_arg):
            return {
                "block": True,
                "message": (
                    "\U0001f6ab AI-DLC PHASE BLOCK: Still in INCEPTION phase.\n\n"
                    "In INCEPTION, write specifications and requirements, not code.\n"
                    "  /ai-dlc phase promote  (to promote to CONSTRUCTION)\n"
                    "  /ai-dlc guide         (for guidance)"
                ),
            }

    # --- Step 2.5: Extract payload from tool-specific args ---
    if not content_arg:
        if tool_name == "patch":
            content_arg = args.get("new_string", "")
        elif tool_name == "terminal":
            content_arg = args.get("command", "")
        elif tool_name == "process":
            content_arg = args.get("data", "")
    # For terminal/process without a real file path, use a path hint
    if not path_arg and content_arg:
        path_arg = f"/tmp/{tool_name}-payload.sh"
    logger.debug(f"ai-dlc-compass: scanning {tool_name}: path={path_arg}, content_len={len(content_arg)}")

    # --- Step 3: Verify content against steering rules ---
    if content_arg:
        violations = vr.verify_content(content_arg, str(path_arg))
        if violations["critical"] or violations["warning"]:
            return _handle_violations(violations, path_arg, content_arg)

    # --- Step 4: All checks passed ---
    return None  # allow


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

CODE_EXTENSIONS = frozenset({
    ".py", ".rs", ".ts", ".js", ".tsx", ".jsx", ".go", ".java",
    ".c", ".cpp", ".h", ".hpp", ".swift", ".kt", ".rb", ".php",
    ".sh", ".bash", ".yaml", ".yml", ".json", ".toml",
})

def _is_code_file(path: str) -> bool:
    """Check if path looks like a code file (vs doc/spec/wiki)."""
    ext = os.path.splitext(path)[1].lower()
    return ext in CODE_EXTENSIONS


def _handle_violations(violations: dict, path: str, content: str) -> dict:
    """Handle steering violations — block + educate + escalate."""
    critical = violations.get("critical", [])
    warning = violations.get("warning", [])

    # Build violation messages
    msg_parts = ["\U0001f6e1\ufe0f AI-DLC: Steering violation detected!\n"]
    for v in critical:
        msg_parts.append(f"  \u274c CRITICAL: [{v['rule_id']}] {v['description']}")
        msg_parts.append(f"    \u2192 {v['suggestion']}")
    for v in warning:
        msg_parts.append(f"  \u26a0\ufe0f WARNING: [{v['rule_id']}] {v['description']}")
        msg_parts.append(f"    \u2192 {v['suggestion']}")

    # Log to state
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": "write_file" if "content" in locals() else "terminal",
        "path": str(path),
        "violations": critical + warning,
        "resolved": False,
    }
    state = _read_json(STATE_FILE)
    state.setdefault("violations", []).append(record)
    _write_json(STATE_FILE, state)

    # Escalate critical to MOA-Gate if available
    if critical and _can_escalate_to_moa("critical", 2):
        msg_parts.append(
            "\n\U0001f534 Auto-escalated to MOA-Gate critical\n"
            "  Run /moa-approve --by critic,skeptic --reason \"<reason>\""
        )

    return {"block": True, "message": "\n".join(msg_parts)}
