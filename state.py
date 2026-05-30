"""MOA Gate — HMAC-signed state management with TTL.

State file: ~/.hermes/moa-gate/state.json
Format::
    {
        "status": "approved" | "pending" | "rejected",
        "approved_at": "ISO-8601" | null,
        "approved_by": ["voice1", "voice2"] | [],
        "reason": "..." | "",
        "session_id": "sess_..." | "",
        "expires_at": "ISO-8601" | null,
        "auto_approved": false,        # true = auto via council majority
        "dissented": ["critic"],       # voices that disagreed
        "dissent_reason": "...",       # reason from dissenter
        "tier": 1,                     # 1 = auto, 2 = manual only
        "cool_down_until": null,       # ISO-8601, null = no cooldown
        "override_by": "",             # human who overrode cooldown
        "trigger": "manual",           # "manual" | "auto_majority"
        "council_config_hash": "",     # hash of council config at time
        "hmac": "hex-64"
    }

HMAC = HMAC-SHA256(canonical JSON of all fields except "hmac" + key)
Key from MOA_GATE_KEY env var. Auto-generates on first run.

TTL: Default 15 minutes. Max 60 minutes.
Auto-approve: council >=80%, weighted veto for Critic/Skeptic dissent.
"""

from __future__ import annotations

import hmac
import hashlib
import json
import fcntl
import logging
import os
import secrets
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STATE_DIR = Path.home() / ".hermes" / "moa-gate"
STATE_FILE = STATE_DIR / "state.json"
ENV_KEY_NAME = "MOA_GATE_KEY"
ENV_FILE = Path.home() / ".hermes" / ".env"
HMAC_HEX_LEN = 64  # SHA-256 hex

# TTL defaults (seconds)
DEFAULT_TTL_SECONDS = 15 * 60   # 15 minutes
MAX_TTL_SECONDS = 60 * 60       # 60 minutes

# Session GC
MAX_SESSION_AGE_SECONDS = 3600  # 1 hour — stale per-session state files


def _safe_session_id(session_id: str) -> str:
    """Return a filesystem-safe session id for per-session state files."""
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in (session_id or ""))
    return safe[:160]


def state_file_for_session(session_id: str = "") -> Path:
    """Return the signed state file for a session. Empty keeps legacy global path."""
    safe = _safe_session_id(session_id)
    if not safe:
        return STATE_FILE
    return STATE_DIR / "sessions" / f"{safe}.json"


# ---------------------------------------------------------------------------
# Key management
# ---------------------------------------------------------------------------

def _load_or_generate_key() -> str:
    """Load MOA_GATE_KEY from environment or .env; generate only if absent."""
    key = os.environ.get(ENV_KEY_NAME)
    if key:
        return key

    try:
        env_path = ENV_FILE
        env_path.parent.mkdir(parents=True, exist_ok=True)
        if env_path.exists():
            existing = env_path.read_text()
            for line in existing.splitlines():
                if line.startswith(f"{ENV_KEY_NAME}="):
                    stored_key = line.split("=", 1)[1].strip()
                    if stored_key:
                        os.environ[ENV_KEY_NAME] = stored_key
                        # Ensure key file is protected
                        try:
                            env_path.chmod(0o600)
                        except OSError:
                            pass
                        logger.info("Loaded existing MOA_GATE_KEY from .env")
                        return stored_key

        key = secrets.token_hex(32)
        # Create/append with 0o600 from the start (no TOCTOU window)
        fd = os.open(str(env_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, f"\n{ENV_KEY_NAME}={key}\n".encode("utf-8"))
        finally:
            os.close(fd)
        os.environ[ENV_KEY_NAME] = key
        logger.info("Generated new MOA_GATE_KEY in .env")
    except Exception as exc:
        logger.error("Failed to persist MOA_GATE_KEY: %s", exc)
        raise RuntimeError("Cannot initialize MOA Gate — key generation failed") from exc

    return key



def sync_key() -> str:
    """Re-read MOA_GATE_KEY from .env and sync into os.environ.
    
    Called on each pre_tool_call to keep Hermes in sync with .env.
    Falls back to _load_or_generate_key() if .env is empty.
    """
    try:
        env_path = ENV_FILE
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith(f"{ENV_KEY_NAME}="):
                    stored_key = line.split("=", 1)[1].strip()
                    if stored_key:
                        os.environ[ENV_KEY_NAME] = stored_key
                        return stored_key
    except OSError:
        pass
    return _load_or_generate_key()

def get_key() -> str:
    key = os.environ.get(ENV_KEY_NAME)
    if not key:
        key = _load_or_generate_key()
    return key


# ---------------------------------------------------------------------------
# HMAC signing
# ---------------------------------------------------------------------------

def _canonical_json(data: Dict[str, Any]) -> bytes:
    """Deterministic JSON without hmac field, sorted keys."""
    clean = {k: v for k, v in data.items() if k != "hmac"}
    return json.dumps(clean, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def sign(data: Dict[str, Any]) -> str:
    """Return HMAC-SHA256 hex digest of canonical JSON."""
    key = get_key()
    payload = _canonical_json(data)
    return hmac.new(key.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def verify(data: Dict[str, Any]) -> bool:
    """Verify HMAC field matches computed signature."""
    stored = data.get("hmac", "")
    if not isinstance(stored, str) or len(stored) != HMAC_HEX_LEN:
        return False
    expected = sign(data)
    return hmac.compare_digest(stored, expected)


# ---------------------------------------------------------------------------
# TTL helpers
# ---------------------------------------------------------------------------

def _parse_ttl(ttl_str: str) -> int:
    """Parse TTL string like '15m', '1h', '60s' to seconds.
    
    Supports: 30s, 15m, 1h, or plain number (assumed minutes).
    Returns seconds. Clamps to [0, MAX_TTL_SECONDS].
    """
    ttl_str = ttl_str.strip().lower()
    if ttl_str.endswith("s"):
        seconds = int(ttl_str[:-1])
    elif ttl_str.endswith("h"):
        seconds = int(ttl_str[:-1]) * 3600
    elif ttl_str.endswith("m"):
        seconds = int(ttl_str[:-1]) * 60
    else:
        # Plain number = minutes (for backward compat with /moa-approve)
        try:
            seconds = int(ttl_str) * 60
        except ValueError:
            seconds = DEFAULT_TTL_SECONDS

    return max(0, min(seconds, MAX_TTL_SECONDS))


def _is_expired(expires_at: Optional[str]) -> bool:
    """Check if an ISO-8601 timestamp has passed (UTC)."""
    if not expires_at:
        # Fail-closed: no expires_at = expired (force re-approve)
        return True
    try:
        exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return now >= exp
    except (ValueError, TypeError):
        # Malformed timestamp = expired (fail-closed)
        logger.warning("MOA Gate: malformed expires_at: %s", expires_at)
        return True


# ---------------------------------------------------------------------------
# State read / write
# ---------------------------------------------------------------------------

def default_state() -> Dict[str, Any]:
    return {
        "status": "pending",
        "approved_at": None,
        "approved_by": [],
        "reason": "",
        "session_id": "",
        "expires_at": None,
        "auto_approved": False,
        "dissented": [],
        "dissent_reason": "",
        "tier": 1,
        "cool_down_until": None,
        "override_by": "",
        "trigger": "manual",
        "council_config_hash": "",
        "hmac": "",
    }


def read(session_id: str = "") -> Dict[str, Any]:
    """Read and verify state file. Returns default_state() if missing/invalid.

    Checks TTL expiry: if approved but expired, auto-revoke.
    Backward compat: old state without expires_at (LYN format) gets a
    computed expiry injected AFTER HMAC verification.
    """
    path = state_file_for_session(session_id)
    if not path.exists():
        return default_state()

    try:
        raw = path.read_text()
        data = json.loads(raw)
    except (json.JSONDecodeError, PermissionError, OSError) as exc:
        logger.warning("MOA Gate state read error: %s", exc)
        return default_state()

    if not isinstance(data, dict):
        return default_state()

    if not verify(data):
        logger.warning("MOA Gate state HMAC mismatch — possible tamper")
        state = default_state()
        state["reason"] = "State integrity check failed"
        return state

    # Backward compat: inject defaults for missing fields
    # (new fields added after initial state was signed)
    # Do this AFTER HMAC verify (signature was on original dict)
    defaults = {
        "auto_approved": False,
        "dissented": [],
        "dissent_reason": "",
        "tier": 1,
        "cool_down_until": None,
        "override_by": "",
        "trigger": "manual",
        "council_config_hash": "",
    }
    for key, default_val in defaults.items():
        if key not in data:
            data[key] = default_val

    # Backward compat: state without expires_at (LYN old format or direct write)
    if data.get("status") == "approved" and "expires_at" not in data:
        now = datetime.now(timezone.utc)
        if data.get("approved_at"):
            try:
                approved = datetime.fromisoformat(data["approved_at"].replace("Z", "+00:00"))
                expires = approved + timedelta(seconds=DEFAULT_TTL_SECONDS)
            except (ValueError, TypeError):
                expires = now + timedelta(seconds=DEFAULT_TTL_SECONDS)
        else:
            expires = now + timedelta(seconds=DEFAULT_TTL_SECONDS)
        data["expires_at"] = expires.strftime("%Y-%m-%dT%H:%M:%SZ")
        logger.info("MOA Gate: injected expires_at for old-format state")

    # TTL expiry check
    if data.get("status") == "approved" and _is_expired(data.get("expires_at")):
        logger.info("MOA Gate: approval expired (auto-revoke)")
        return default_state()

    return data


def write(status: str, approved_by: list, reason: str,
          session_id: str = "", ttl_seconds: int = DEFAULT_TTL_SECONDS,
          *,
          auto_approved: bool = False,
          dissented: list | None = None,
          dissent_reason: str = "",
          tier: int = 1,
          cool_down_until: str | None = None,
          override_by: str = "",
          trigger: str = "manual",
          council_config_hash: str = "") -> None:
    """Write a new signed state. Uses atomic write (temp + replace).

    For approved status, sets expires_at based on ttl_seconds.

    Uses a lock file (fcntl.flock) to serialize concurrent writes
    from different sessions/processes.
    """
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    # Acquire exclusive lock to serialize concurrent writes
    lock_path = STATE_DIR / ".state.lock"
    with open(str(lock_path), "w") as lock_f:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)

        data: Dict[str, Any] = {
            "status": status,
            "approved_at": None,
            "approved_by": approved_by or [],
            "reason": reason or "",
            "session_id": session_id or "",
            "expires_at": None,
            "auto_approved": auto_approved,
            "dissented": dissented or [],
            "dissent_reason": dissent_reason or "",
            "tier": tier,
            "cool_down_until": cool_down_until,
            "override_by": override_by or "",
            "trigger": trigger or "manual",
            "council_config_hash": council_config_hash or "",
        }

        if status == "approved":
            now = datetime.now(timezone.utc)
            data["approved_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            expires = now + timedelta(seconds=ttl_seconds)
            data["expires_at"] = expires.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Sign (includes expires_at and session_id in HMAC payload)
        data["hmac"] = sign(data)

        # Atomic write
        target = state_file_for_session(session_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=str(target.parent), prefix=".state_tmp_", suffix=".json")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, str(target))
            target.chmod(0o600)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        finally:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)


def approve(approved_by: list, reason: str, session_id: str = "",
            ttl_seconds: int = DEFAULT_TTL_SECONDS, **kwargs) -> Dict[str, Any]:
    """Approve the gate with TTL (manual approval)."""
    write("approved", approved_by, reason, session_id,
          ttl_seconds=ttl_seconds, trigger="manual", **kwargs)
    return read(session_id)


def approve_auto(approved_by: list, reason: str, session_id: str = "",
                 dissented: list | None = None, dissent_reason: str = "",
                 tier: int = 1, cool_down_seconds: int = 120,
                 council_config_hash: str = "",
                 ttl_seconds: int = DEFAULT_TTL_SECONDS) -> Dict[str, Any]:
    """Auto-approve via council majority (trigger='auto_majority').

    Sets auto_approved=True, trigger='auto_majority'.
    If cool_down_seconds > 0, sets cool_down_until for delayed execution.
    """
    now = datetime.now(timezone.utc)
    cool_down_until = None
    if cool_down_seconds > 0:
        cool_down = now + timedelta(seconds=cool_down_seconds)
        cool_down_until = cool_down.strftime("%Y-%m-%dT%H:%M:%SZ")

    write("approved", approved_by, reason, session_id,
          ttl_seconds=ttl_seconds,
          auto_approved=True,
          dissented=dissented,
          dissent_reason=dissent_reason,
          tier=tier,
          cool_down_until=cool_down_until,
          trigger="auto_majority",
          council_config_hash=council_config_hash)
    return read(session_id)


def override_cooldown(override_by: str = "human", session_id: str = "") -> Dict[str, Any]:
    """Override cool-down period — execute immediately.

    Reads current state, clears cool_down_until, sets override_by.
    Preserves original expires_at and approved_at to avoid extending TTL.
    Reuses write() for atomic write with flock.
    """
    data = read(session_id)
    if not data.get("cool_down_until"):
        return data  # No cooldown active, nothing to do

    now = datetime.now(timezone.utc)
    # Preserve original expires_at and approved_at so override doesn't extend TTL
    preserved_expires_at = data.get("expires_at")
    preserved_approved_at = data.get("approved_at")

    # Use write() with proper lock — then manually restore expires/approved
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = STATE_DIR / ".state.lock"
    with open(str(lock_path), "w") as lock_f:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
        try:
            data["cool_down_until"] = None
            data["override_by"] = override_by
            if preserved_expires_at:
                data["expires_at"] = preserved_expires_at
            if preserved_approved_at:
                data["approved_at"] = preserved_approved_at
            data["hmac"] = sign(data)

            target = state_file_for_session(session_id)
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(dir=str(target.parent), prefix=".state_tmp_", suffix=".json")
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, str(target))
                target.chmod(0o600)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        finally:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)

    return read(session_id)


def is_in_cooldown(data: Dict[str, Any]) -> bool:
    """Check if state is in cool-down period.

    Returns True if cool_down_until is set and hasn't expired.
    """
    cd = data.get("cool_down_until")
    if not cd:
        return False
    try:
        deadline = datetime.fromisoformat(cd.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return now < deadline
    except (ValueError, TypeError):
        return False


def revoke(reason: str = "", trigger: str = "manual", session_id: str = "") -> Dict[str, Any]:
    """Revoke the gate for one session. Empty session_id keeps legacy global state."""
    write("pending", [], reason or f"Revoked ({trigger})", session_id=session_id)
    return read(session_id)


# ---------------------------------------------------------------------------
# Session GC — cleanup stale per-session state files
# ---------------------------------------------------------------------------

def gc_stale_sessions(max_age: int = MAX_SESSION_AGE_SECONDS) -> int:
    """Remove session state files older than `max_age` seconds.
    
    Returns count of removed files. Skips sessions/ dir itself.
    """
    sessions_dir = STATE_DIR / "sessions"
    if not sessions_dir.is_dir():
        return 0
    
    now = datetime.now(timezone.utc).timestamp()
    removed = 0
    for f in sessions_dir.iterdir():
        if not f.is_file() or not f.name.endswith(".json"):
            continue
        try:
            age = now - f.stat().st_mtime
            if age > max_age:
                f.unlink()
                removed += 1
                logger.debug("GC: removed stale session file %s (age=%.0fs)", f.name, age)
        except OSError as exc:
            logger.warning("GC: failed to remove %s: %s", f.name, exc)
            continue
    if removed:
        logger.info("GC: removed %d stale session file(s)", removed)
    return removed


# ---------------------------------------------------------------------------
# Status display
# ---------------------------------------------------------------------------

def format_status(data: Dict[str, Any]) -> str:
    status = data.get("status", "unknown")
    if status == "approved":
        by = ", ".join(data.get("approved_by", []))
        at = data.get("approved_at", "?")
        reason = data.get("reason", "")
        expires = data.get("expires_at", "???")
        auto = data.get("auto_approved", False)
        trigger = data.get("trigger", "manual")
        tier = data.get("tier", 1)
        dissented = data.get("dissented", [])
        is_cooldown = is_in_cooldown(data)

        # Show trigger + tier
        mode = "🤖 Auto" if auto else "👤 Manual"
        tier_label = "Tier 1 (Auto)" if tier == 1 else "Tier 2 (⚠️ Manual only)"

        # Remaining TTL
        remaining = ""
        if expires:
            try:
                exp = datetime.fromisoformat(expires.replace("Z", "+00:00"))
                diff = exp - datetime.now(timezone.utc)
                mins = int(diff.total_seconds() / 60)
                if mins > 0:
                    remaining = f"\n   TTL: ~{mins}min"
                else:
                    remaining = "\n   ⚠️ EXPIRED"
            except (ValueError, TypeError):
                remaining = "\n   TTL: ???"

        lines = [
            f"✅ MOA Gate: APPROVED",
            f"   Mode: {mode} ({trigger})",
            f"   Tier: {tier_label}",
            f"   By: {by}",
            f"   At: {at}",
        ]
        if dissented:
            reason_d = data.get("dissent_reason", "")
            lines.append(f"   Dissent: {', '.join(dissented)}")
            if reason_d:
                lines.append(f"   Dissent reason: {reason_d}")
        lines.append(f"   Reason: {reason}")
        lines.append(f"{remaining}")
        if is_cooldown:
            cd = data.get("cool_down_until", "")
            lines.append(f"   ⏳ Cool-down active until: {cd}")
            lines.append(f"   (Override with: /moa-approve --override)")
        return "\n".join(lines)
    elif status == "pending":
        return "⏳ MOA Gate: PENDING — MOA review required before write tools"
    elif status == "rejected":
        return f"❌ MOA Gate: REJECTED — {data.get('reason', 'No reason')}"
    else:
        return f"❓ MOA Gate: {status}"