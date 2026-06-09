"""Tests for MOA Gate slash-command handlers and helpers.

Covers:
  - _get_last_blocked_tool (ordering, cross-session isolation)
  - /moa-emergency (reason guard, approval, audit logging)
  - /moa-revoke (no redundant logic)
  - /moa-council-complete (council_hash computed)
  - Help text contains emergency subcommand
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

_HERE = Path(__file__).parent
_PLUGIN_DIR = _HERE.parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

# ---------------------------------------------------------------------------
# Redirect file paths to a temp directory
# ---------------------------------------------------------------------------
os.environ["HERMES_SESSION_ID"] = "test-session-root"
os.environ["MOA_GATE_KEY"] = "test-key-for-unit-tests-32bytes!!"

_tmp = tempfile.mkdtemp(prefix="moa_gate_test_")

import state as st
import audit as au
import __init__ as moa

# Patch to temp dirs
st.STATE_DIR = Path(_tmp) / "state"
st.STATE_DIR.mkdir(parents=True, exist_ok=True)

# Audit uses a FILE, not a DIR
_orig_audit_file = au.AUDIT_FILE
au.AUDIT_FILE = Path(_tmp) / "audit" / "audit.log"
au.AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)

# Ensure clean HMAC so state operations don't crash
# Key is loaded via _load_or_generate_key() at import from MOA_GATE_KEY env


def test_get_last_blocked_tool_empty():
    """Returns empty string when no block entries exist."""
    assert moa._get_last_blocked_tool("no-session") == ""


def test_get_last_blocked_tool_finds_block():
    """Finds block among mixed log entries."""
    sid = "test-block-search"
    au.log("allow", tool="read_file", session_id=sid)
    au.log("block", tool="write_file", session_id=sid)
    au.log("allow", tool="status", session_id=sid)
    assert moa._get_last_blocked_tool(sid) == "write_file"


def test_get_last_blocked_tool_returns_newest():
    """Returns the newest (most recent) block."""
    sid = "test-ordering"
    au.log("block", tool="patch", session_id=sid)
    time.sleep(0.01)
    au.log("block", tool="write_file", session_id=sid)
    time.sleep(0.01)
    au.log("block", tool="terminal", session_id=sid)
    assert moa._get_last_blocked_tool(sid) == "terminal"


def test_get_last_blocked_tool_skips_other_sessions():
    """Does not return entries from other sessions."""
    s1, s2 = "test-sess-a", "test-sess-b"
    au.log("block", tool="write_file", session_id=s1)
    au.log("block", tool="terminal", session_id=s2)
    assert moa._get_last_blocked_tool(s1) == "write_file"


def test_emergency_requires_reason():
    """Empty or missing --reason returns a usage error."""
    r = moa._handle_emergency("")
    assert "Usage" in r

    r = moa._handle_emergency('--reason ""')
    assert "not allowed" in r or "Usage" in r or "Meaningful" in r


def test_emergency_approves_with_reason():
    """Full emergency bypass works and mentions revoke."""
    sid = "test-emergency"
    os.environ["HERMES_SESSION_ID"] = sid
    try:
        r = moa._handle_emergency('--reason "Production DNS outage -- hotfix"')
        assert "EMERGENCY BYPASS" in r
        assert "/moa-revoke" in r
    finally:
        os.environ["HERMES_SESSION_ID"] = "test-session-root"


def test_revoke_works():
    """Basic revoke works."""
    r = moa._handle_revoke("")
    assert "REVOKED" in r

    r = moa._handle_revoke("reason")
    assert "REVOKED" in r


def test_help_contains_emergency():
    """Help text mentions emergency."""
    assert "emergency" in moa._HELP_TEXT
    assert "EMERGENCY" in moa._HELP_TEXT


def test_council_hash_not_auto():
    """Council hash is computed, not the placeholder 'auto'."""
    sid = "test-hash"
    os.environ["HERMES_SESSION_ID"] = sid
    try:
        council_json = json.dumps({
            "votes": {"a": "approve", "c": "approve", "p": "approve"},
            "task_description": "test",
        })
        moa._handle_council_complete(council_json)
        data = st.read(sid)
        h = data.get("council_config_hash", "")
        assert h and h != "auto", f"Expected real hash, got {h!r}"
    finally:
        os.environ["HERMES_SESSION_ID"] = "test-session-root"
