"""Tests for hooks/pre-commit.py — cooldown, session fallback, and approval checks.

Covers:
  (a) valid global approval                                    → pass
  (b) approved but in active cool-down (no override)          → blocked
  (c) cool-down deadline already past                         → pass
  (d) HERMES_SESSION_ID set + valid per-session file          → pass
  (e) HERMES_SESSION_ID set + expired session file + valid global approval → pass (fallback fix)
  (f) no approval anywhere                                    → blocked
"""

import importlib.util
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).parent
_PLUGIN_DIR = _HERE.parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

# ---------------------------------------------------------------------------
# Isolated temp environment — set env BEFORE importing modules so key loading
# and path helpers see the right values at call-time.
# ---------------------------------------------------------------------------
_GATE_KEY = "test-key-pre-commit-hook-32bytes!!"
os.environ["MOA_GATE_KEY"] = _GATE_KEY
_tmp = tempfile.mkdtemp(prefix="moa_precommit_test_")
os.environ["HERMES_HOME"] = _tmp

import state as st  # noqa: E402 — must come after env setup

# Patch state.py module globals so write() and state_file_for_session() use tmpdir.
# state_file_for_session("") returns STATE_FILE; non-empty uses STATE_DIR/sessions/.
st.STATE_DIR = Path(_tmp) / "moa-gate"
st.STATE_FILE = st.STATE_DIR / "state.json"
st.STATE_DIR.mkdir(parents=True, exist_ok=True)
(st.STATE_DIR / "sessions").mkdir(parents=True, exist_ok=True)

# Load hooks/pre-commit.py via importlib (the hooks/ directory name is fine;
# the module name just can't contain dashes, so we use "pre_commit_hook").
_pc_path = _PLUGIN_DIR / "hooks" / "pre-commit.py"
_spec = importlib.util.spec_from_file_location("pre_commit_hook", str(_pc_path))
pc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_signed_state(path: Path, **fields) -> None:
    """Write a fully signed state dict to *path*.

    Default fields represent a valid approved state with far-future TTL.
    Pass keyword args to override individual fields (e.g. expires_at, cool_down_until).
    The HMAC is recomputed after all fields are set so the signature is always valid.
    """
    data = {
        "status": "approved",
        "approved_at": "2026-01-01T00:00:00Z",
        "approved_by": ["test-voice"],
        "reason": "test approval",
        "session_id": "",
        "expires_at": "2099-01-01T00:00:00Z",
        "auto_approved": False,
        "dissented": [],
        "dissent_reason": "",
        "tier": 1,
        "cool_down_until": None,
        "override_by": "",
        "trigger": "manual",
        "council_config_hash": "",
    }
    data.update(fields)
    # Recompute HMAC with whatever key state.py resolved (same as pre-commit.py uses)
    data["hmac"] = st.sign(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _clean_state() -> None:
    """Remove all state files and clear HERMES_SESSION_ID between tests."""
    if st.STATE_FILE.exists():
        st.STATE_FILE.unlink()
    sessions_dir = st.STATE_DIR / "sessions"
    if sessions_dir.exists():
        for f in sessions_dir.iterdir():
            if f.is_file():
                f.unlink()
    os.environ.pop("HERMES_SESSION_ID", None)


def _session_path(sid: str) -> Path:
    """Return the expected session file path for a given session ID."""
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in sid)
    return st.STATE_DIR / "sessions" / f"{safe}.json"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_valid_global_approval_passes():
    """(a) Valid global approval with no session ID → commit allowed."""
    _clean_state()
    _write_signed_state(st.STATE_FILE)

    ok, msg = pc.verify_state()

    assert ok, f"Expected approval to pass; got: {msg}"
    assert "APPROVED" in msg


def test_cooldown_blocks_commit():
    """(b) Approved but cool-down window active and no override → blocked."""
    _clean_state()
    future = _iso(_now_utc() + timedelta(hours=1))
    _write_signed_state(st.STATE_FILE, cool_down_until=future, override_by="")

    ok, msg = pc.verify_state()

    assert not ok, "Expected commit to be blocked during active cool-down"
    assert "Cool-down" in msg
    assert future in msg


def test_cooldown_expired_passes():
    """(c) Cool-down deadline already past → commit allowed."""
    _clean_state()
    past = _iso(_now_utc() - timedelta(hours=1))
    _write_signed_state(st.STATE_FILE, cool_down_until=past)

    ok, msg = pc.verify_state()

    assert ok, f"Expected expired cooldown to allow commit; got: {msg}"
    assert "APPROVED" in msg


def test_session_file_passes():
    """(d) HERMES_SESSION_ID set + valid per-session state file → pass."""
    _clean_state()
    sid = "test-precommit-d"
    os.environ["HERMES_SESSION_ID"] = sid
    try:
        # state.py write() routes to STATE_DIR/sessions/<safe-sid>.json
        st.write("approved", ["voice-d"], "session approval", session_id=sid)

        ok, msg = pc.verify_state()

        assert ok, f"Expected session-file approval to pass; got: {msg}"
        assert "APPROVED" in msg
    finally:
        os.environ.pop("HERMES_SESSION_ID", None)


def test_expired_session_falls_back_to_global():
    """(e) Expired session file + valid global approval → pass via fallback.

    This exercises the fix for the stale-session-shadows-global bug: an expired
    (or otherwise invalid) per-session file must not block a valid global
    emergency approval.
    """
    _clean_state()
    sid = "test-precommit-e"
    os.environ["HERMES_SESSION_ID"] = sid
    try:
        # Write a session file whose TTL has already passed
        expired_path = _session_path(sid)
        _write_signed_state(
            expired_path,
            session_id=sid,
            expires_at="2024-01-01T00:15:00Z",  # clearly in the past
        )
        # Write a valid global approval (no session restriction)
        _write_signed_state(st.STATE_FILE)

        ok, msg = pc.verify_state()

        assert ok, (
            f"Expected fallback to valid global approval; got: {msg}"
        )
        assert "APPROVED" in msg
    finally:
        os.environ.pop("HERMES_SESSION_ID", None)


def test_no_approval_blocks():
    """(f) No state file at all → commit blocked."""
    _clean_state()

    ok, msg = pc.verify_state()

    assert not ok, "Expected commit to be blocked when no approval exists"
    assert "MOA Gate" in msg
