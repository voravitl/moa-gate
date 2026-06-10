#!/usr/bin/env python3
"""Git pre-commit hook — MOA Gate authoritative enforcement.

Verifies MOA gate state before allowing any commit.
This is Layer 3 (authoritative) — catches bypasses through
terminal, computer_use, or any other Hermes tool.

Exit codes:
    0 = allow commit (state is approved)
    1 = block commit (state is pending/error/tampered)
"""

import json
import hmac
import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def _safe_session_id(session_id: str) -> str:
    """Return a filesystem-safe session id for per-session state files.

    # Mirrors state.py:state_file_for_session — keep in sync
    """
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in (session_id or ""))
    return safe[:160]


def get_state_file() -> Path:
    """Resolve state file path, respecting HERMES_HOME and HERMES_SESSION_ID.

    If HERMES_SESSION_ID is set and the per-session file exists, return it.
    Otherwise fall back to the global state.json (fail-closed default).

    NOTE: verify_state() uses its own fallback logic (session → global); this
    helper is retained for external callers and documentation purposes.

    # Mirrors state.py:state_file_for_session — keep in sync
    """
    home = os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
    global_path = Path(home) / "moa-gate" / "state.json"

    session_id = os.environ.get("HERMES_SESSION_ID", "").strip()
    safe = _safe_session_id(session_id)
    if safe:
        session_path = Path(home) / "moa-gate" / "sessions" / f"{safe}.json"
        if session_path.exists():
            return session_path

    return global_path


def get_key() -> str:
    """Load HMAC key from environment."""
    key = os.environ.get("MOA_GATE_KEY", "")
    if not key:
        # Try reading from .env
        home = os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
        env_path = Path(home) / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("MOA_GATE_KEY="):
                    key = line.split("=", 1)[1].strip().strip("'\"")
                    os.environ["MOA_GATE_KEY"] = key
                    break
    return key


def _verify_one(state_path: Path, *, require_session_match: bool = False) -> tuple:
    """Verify a single state file.

    Args:
        state_path: Path to the state file to verify.
        require_session_match: When True, enforce that the state's stored
            session_id (if any) matches HERMES_SESSION_ID. Used for the global
            state path — per-session file paths already encode the session via
            filename, so they skip this check.

    Returns:
        (ok: bool, message: str)

    # Mirrors _on_pre_tool_call checks in __init__.py — keep in sync
    """
    # Check state file exists
    if not state_path.exists():
        return False, "MOA Gate: No state file found. Run /moa-council-complete or /moa-emergency first."

    # Read state
    try:
        raw = state_path.read_text()
        data = json.loads(raw)
    except (json.JSONDecodeError, PermissionError, OSError) as exc:
        return False, f"MOA Gate: State file error — {exc}"

    if not isinstance(data, dict):
        return False, "MOA Gate: Invalid state format"

    # Fail-closed: approved but no expires_at = old format (v1), must re-approve
    # Check BEFORE HMAC verify because old format won't have expires_at in signature
    if data.get("status") == "approved" and "expires_at" not in data:
        return False, "MOA Gate: State format outdated (no TTL). Re-approve with /moa-council-complete or /moa-emergency."

    # Check HMAC
    key = get_key()
    if not key:
        return False, "MOA Gate: No HMAC key found. Set MOA_GATE_KEY in .env"

    stored_hmac = data.get("hmac", "")
    if not stored_hmac:
        return False, "MOA Gate: State file has no HMAC signature (tampered?)"

    # Compute expected HMAC
    canonical = json.dumps(
        {k: v for k, v in data.items() if k != "hmac"},
        sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")

    expected = hmac.new(key.encode("utf-8"), canonical, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(stored_hmac, expected):
        return False, "MOA Gate: HMAC signature mismatch — STATE FILE TAMPERED!"

    # Check status
    status = data.get("status", "pending")
    if status != "approved":
        return False, f"MOA Gate: Status is '{status}', not 'approved'. Run /moa-council-complete or /moa-emergency."

    # Fail-closed: no expires_at = old format, must re-approve
    expires_at = data.get("expires_at")
    if not expires_at:
        return False, "MOA Gate: State format outdated (no TTL). Re-approve with /moa-council-complete or /moa-emergency."

    # Check TTL expiry
    now = datetime.now(timezone.utc)
    try:
        exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return False, "MOA Gate: Malformed expires_at. Re-approve with /moa-council-complete or /moa-emergency."

    if now >= exp:
        mins_over = int((now - exp).total_seconds() / 60)
        return False, f"MOA Gate: Approval EXPIRED {mins_over}min ago. Re-approve with /moa-council-complete or /moa-emergency."

    # ---- Cool-down check ----
    # Keep in sync with state.py:is_in_cooldown and __init__.py:_on_pre_tool_call
    cool_down_until = data.get("cool_down_until")
    override_by = data.get("override_by", "")
    if cool_down_until and not override_by:
        try:
            deadline = datetime.fromisoformat(cool_down_until.replace("Z", "+00:00"))
            if now < deadline:
                return False, (
                    f"🛑 MOA Gate: Cool-down active until {cool_down_until}\n"
                    f"   Auto-approve is in cool-down period.\n"
                    f"   To override: `/moa-emergency --reason \"...\"`\n"
                    f"   Or wait for cool-down to expire."
                )
        except (ValueError, TypeError):
            pass  # Malformed cool_down_until — treat as inactive (fail-open for invalid value)

    # ---- Session-match guard for global state ----
    # Keep in sync with __init__.py:_on_pre_tool_call allowed_session logic
    if require_session_match:
        stored_session = data.get("session_id", "")
        if stored_session:
            current_session = os.environ.get("HERMES_SESSION_ID", "").strip()
            if current_session and current_session != stored_session:
                return False, (
                    "🛑 MOA Gate: Approval from different session. "
                    "Run `/moa-revoke` then re-submit via `/moa-council-complete` "
                    "or `/moa-emergency --reason \"...\"`."
                )

    # All checks passed — format success message
    by = data.get("approved_by", [])
    reason = data.get("reason", "")
    at = data.get("approved_at", "?")

    try:
        remaining = int((exp - now).total_seconds() / 60)
        ttl_info = f"\n   TTL: ~{remaining}min remaining (expires: {expires_at})"
    except Exception:
        ttl_info = f"\n   Expires: {expires_at}"

    msg = (
        f"✅ MOA Gate: APPROVED\n"
        f"   By: {', '.join(by)}\n"
        f"   At: {at}\n"
        f"   Reason: {reason}"
        f"{ttl_info}"
    )

    return True, msg


def verify_state() -> tuple:
    """Verify MOA gate state with session-file-first, global-fallback logic.

    Priority:
      1. If HERMES_SESSION_ID is set and per-session file exists → verify it.
      2. If session-file verification fails for ANY reason (expired, tampered,
         corrupt) → also verify the global state.json. Commit passes if EITHER
         is valid (an emergency global approval must unlock commits even when a
         stale session file is present).
      3. No session file present → verify global state.json only.

    # Mirrors _on_pre_tool_call in __init__.py — keep in sync
    """
    home = os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
    global_path = Path(home) / "moa-gate" / "state.json"

    session_id = os.environ.get("HERMES_SESSION_ID", "").strip()
    safe = _safe_session_id(session_id)

    if safe:
        session_path = Path(home) / "moa-gate" / "sessions" / f"{safe}.json"
        if session_path.exists():
            # Verify session file (no session-match check — filename already scopes to session)
            ok, msg = _verify_one(session_path, require_session_match=False)
            if ok:
                return True, msg
            # Session file failed — fall back to global emergency approval
            # A valid global approval must still unlock commits (stale-session-file fix)
            session_fail_msg = msg
            ok_global, msg_global = _verify_one(global_path, require_session_match=True)
            if ok_global:
                return True, msg_global
            return False, f"{session_fail_msg}\n   (Also checked global state: {msg_global})"

    # No per-session file — check global state only
    return _verify_one(global_path, require_session_match=True)


def main():
    ok, message = verify_state()

    if not ok:
        print(f"🛑 COMMIT BLOCKED\n{message}", file=sys.stderr)
        sys.exit(1)

    print(message, file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
