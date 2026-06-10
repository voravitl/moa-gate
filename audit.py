"""MOA Gate — append-only audit log with hash chain.

File: ~/.hermes/moa-gate/audit.log

Format: One JSON object per line::

    {"ts":"...","action":"...","tool":"...","by":[...],"reason":"...","session_id":"...","prev_hash":"..."}

The `prev_hash` field links each entry to the prior entry using
SHA-256, making the log tamper-evident.

Actions:
    block           — a tool was blocked by the gate
    allow           — a tool was allowed through
    approve         — gate was manually approved
    auto_approve    — gate was auto-approved via council majority
    revoke          — gate was revoked
    auto_revoke     — gate was auto-revoked (TTL expiry)
    override        — human overrode cool-down
    cool_down_ok    — cool-down expired, execution allowed
    shadow_block    — shadow mode blocked execution (recording only)
    rate_limited    — auto-approve rate-limited
    dissent_issue   — GitHub issue auto-created for dissent
    error           — gate encountered an error
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

AUDIT_FILE = Path.home() / ".hermes" / "moa-gate" / "audit.log"
CHAIN_HASH_SEED = "0" * 64  # Genesis entry prev_hash (64 hex zeros)


def _read_last_hash() -> str:
    """Read the last hash from the audit file.

    Always reads from file (no in-memory cache) to prevent
    race conditions with concurrent sessions.
    """
    if not AUDIT_FILE.exists() or AUDIT_FILE.stat().st_size == 0:
        return CHAIN_HASH_SEED

    try:
        # Read last line
        with open(str(AUDIT_FILE), "rb") as f:
            try:
                f.seek(-2, os.SEEK_END)  # Skip trailing newline
                while f.read(1) != b"\n":
                    f.seek(-2, os.SEEK_CUR)
            except OSError:
                # File too small, read from start
                f.seek(0)
            last_line = f.readline().decode("utf-8").strip()

        if last_line:
            entry = json.loads(last_line)
            h = entry.get("hash", "")
            if h and isinstance(h, str) and len(h) == 64:
                return h
    except Exception as exc:
        logger.debug("MOA Gate audit: could not read last hash: %s", exc)

    return CHAIN_HASH_SEED


def _compute_hash(entry: Dict[str, Any]) -> str:
    """Compute SHA-256 hash of the canonical JSON of an entry."""
    payload = json.dumps(entry, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def log(action: str, *, tool: str = "", by: Optional[List[str]] = None,
        reason: str = "", session_id: str = "", trigger: str = "",
        tier: int = 0) -> None:
    """Append a tamper-evident entry to the audit log.

    Args:
        action: One of "block", "allow", "approve", "auto_approve",
               "override", "revoke", "shadow_block",
               "emergency_bypass",
               "rate_limited", "dissent_issue", "error"
        tool: Tool name (for block/allow)
        by: List of approving voices (for approve)
        reason: Reason string
        session_id: Current session ID
        trigger: "manual" | "auto_majority" | "emergency" | "ttl_expired" | "session_end" | ""
        tier: 1 or 2 (for auto_approve/shadow_block)
    """
    entry: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "action": action,
        "tool": tool or "",
        "by": by or [],
        "reason": reason or "",
        "session_id": session_id or "",
        "trigger": trigger or "",
        "tier": tier if tier else 0,
    }

    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Read-last-hash + append must be one critical section under the same
    # flock, otherwise concurrent writers all read the same prev_hash and
    # fork the chain (issue #368).
    try:
        with open(str(AUDIT_FILE), "a") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                entry["prev_hash"] = _read_last_hash()
                entry["hash"] = _compute_hash(entry)
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                f.flush()
                AUDIT_FILE.chmod(0o600)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except Exception as exc:
        logger.error("MOA Gate audit: append failed: %s", exc)
        return

    # No in-memory cache — next caller re-reads file directly


def verify_chain() -> List[Dict[str, Any]]:
    """Verify the integrity of the entire audit chain.

    Returns:
        List of entries with invalid hash/chain. Empty = chain intact.
    """
    if not AUDIT_FILE.exists() or AUDIT_FILE.stat().st_size == 0:
        return []

    violations: List[Dict[str, Any]] = []
    prev_hash = CHAIN_HASH_SEED
    line_num = 0

    try:
        with open(str(AUDIT_FILE)) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                line_num += 1
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    violations.append({"line": line_num, "error": "invalid JSON"})
                    continue

                # Verify prev_hash chain
                stored_prev = entry.pop("prev_hash", None)
                stored_hash = entry.pop("hash", None)

                if stored_prev != prev_hash:
                    violations.append({
                        "line": line_num,
                        "error": "broken chain",
                        "expected_prev": prev_hash,
                        "got_prev": stored_prev,
                    })

                # Compute over same fields as write-time (no hash field)
                expected_hash = _compute_hash(
                    {**entry, "prev_hash": stored_prev}
                )
                if stored_hash and stored_hash != expected_hash:
                    violations.append({
                        "line": line_num,
                        "error": "hash mismatch",
                        "expected": expected_hash,
                        "got": stored_hash,
                    })

                # Restore fields for next iteration
                entry["prev_hash"] = stored_prev
                entry["hash"] = stored_hash

                if stored_hash:
                    prev_hash = stored_hash
                elif stored_prev:
                    # Corrupted entry — estimate prev from stored_prev
                    prev_hash = stored_prev

    except Exception as exc:
        violations.append({"error": f"read error: {exc}"})

    return violations


def read_log(limit: int = 50) -> List[Dict[str, Any]]:
    """Read the last N entries from the audit log (newest first)."""
    if not AUDIT_FILE.exists() or AUDIT_FILE.stat().st_size == 0:
        return []

    entries: List[Dict[str, Any]] = []
    try:
        with open(str(AUDIT_FILE)) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception:
        return []

    return entries[-limit:][::-1]


def format_log(entries: List[Dict[str, Any]]) -> str:
    """Format audit log entries for display."""
    if not entries:
        return "(empty)"
    lines = []
    for e in entries:
        action = e.get("action", "?")
        tool = e.get("tool", "")
        ts = e.get("ts", "?")
        by = e.get("by", [])
        reason = e.get("reason", "")
        parts = [f"[{ts}] {action.upper():>8}"]
        if tool:
            parts.append(f"tool={tool}")
        if by:
            parts.append(f"by={','.join(by)}")
        if reason:
            parts.append(f"\"{reason}\"")
        lines.append("  " + " ".join(parts))
    return "\n".join(lines)
