"""Regression tests for security fixes in MOA Gate.

Covers:
  FIX 1 — terminal whitelist bypass via shell metacharacters / newlines
  FIX 2 — rate limiter fail-closed on error
  FIX 4 — _parse_ttl rejects 0
  FIX 5 — .env key quote stripping in pre-commit get_key()
  FIX 6 — pre-commit get_state_file() session-aware path
"""

import json
import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).parent
_PLUGIN_DIR = _HERE.parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

# Must set env before importing modules that read it at import time
os.environ["MOA_GATE_KEY"] = "test-key-for-unit-tests-32bytes!!"
os.environ.setdefault("HERMES_SESSION_ID", "test-session-bypass")

import state as st
import __init__ as moa

# ---------------------------------------------------------------------------
# FIX 1: TERMINAL_SHELL_META + TERMINAL_READONLY_PATTERNS combination
# ---------------------------------------------------------------------------

def _is_whitelisted(cmd: str) -> bool:
    """Mirror the exact guard in _on_pre_tool_call."""
    return (
        isinstance(cmd, str)
        and not moa.TERMINAL_SHELL_META.search(cmd)
        and bool(moa.TERMINAL_READONLY_PATTERNS.match(cmd))
    )


class TestTerminalWhitelistBypass:
    def test_clean_claude_p_allowed(self):
        assert _is_whitelisted("claude -p hello world")

    def test_claude_p_semicolon_injection_blocked(self):
        assert not _is_whitelisted("claude -p x; rm -rf /")

    def test_claude_p_pipe_injection_blocked(self):
        assert not _is_whitelisted("claude -p x | cat /etc/passwd")

    def test_claude_p_redirect_injection_blocked(self):
        assert not _is_whitelisted("claude -p x > /tmp/out")

    def test_newline_injection_git_status_blocked(self):
        assert not _is_whitelisted("git status\nrm -rf /")

    def test_newline_injection_ls_blocked(self):
        assert not _is_whitelisted("ls x\nrm -rf /tmp/x")

    def test_backtick_subcommand_blocked(self):
        assert not _is_whitelisted("cat `$(rm -rf /tmp/x)`")

    def test_dollar_paren_subcommand_blocked(self):
        assert not _is_whitelisted("git status $(rm -rf /tmp/x)")

    def test_git_status_clean_allowed(self):
        assert _is_whitelisted("git status")

    def test_ls_la_allowed(self):
        assert _is_whitelisted("ls -la")

    def test_git_log_allowed(self):
        assert _is_whitelisted("git log --oneline")

    def test_pytest_allowed(self):
        assert _is_whitelisted("pytest tests/")

    # --- $ variable expansion hardening ---

    def test_dollar_var_echo_blocked(self):
        """$HOME expansion in echo must be blocked."""
        assert not _is_whitelisted("echo $HOME")

    def test_dollar_var_cat_blocked(self):
        """$SECRET_FILE expansion must be blocked."""
        assert not _is_whitelisted("cat $SECRET_FILE")

    def test_dollar_var_git_log_author_blocked(self):
        """$USER expansion in git log must be blocked."""
        assert not _is_whitelisted("git log --author=$USER")

    def test_clean_echo_no_dollar_allowed(self):
        """echo without $ is still whitelisted."""
        assert _is_whitelisted("echo hello")

    def test_clean_git_log_no_dollar_allowed(self):
        """git log without $ is still whitelisted."""
        assert _is_whitelisted("git log --oneline")


# ---------------------------------------------------------------------------
# FIX 2: rate limiter fail-closed on I/O error
# ---------------------------------------------------------------------------

class TestRateLimiterFailClosed:
    def test_fail_closed_on_unreadable_rate_file(self, tmp_path, monkeypatch):
        """When RATE_FILE points to a directory, open() raises → must return (False, 0)."""
        bad_path = tmp_path / "is_a_dir"
        bad_path.mkdir()
        monkeypatch.setattr(moa, "RATE_FILE", bad_path)
        allowed, remaining = moa._check_rate_limit()
        assert allowed is False
        assert remaining == 0

    def test_normal_rate_limit_still_works(self, tmp_path, monkeypatch):
        """Sanity: first call on a fresh counter file is allowed."""
        rate_file = tmp_path / ".rate_counter.json"
        monkeypatch.setattr(moa, "RATE_FILE", rate_file)
        monkeypatch.setattr(moa, "AUTO_RATE_LIMIT", 5)
        allowed, remaining = moa._check_rate_limit()
        assert allowed is True
        assert remaining >= 1


# ---------------------------------------------------------------------------
# FIX 4: _parse_ttl lower clamp is 1 (not 0)
# ---------------------------------------------------------------------------

class TestParseTtl:
    def test_zero_seconds_clamped_to_one(self):
        assert st._parse_ttl("0s") >= 1

    def test_zero_minutes_clamped_to_one(self):
        assert st._parse_ttl("0m") >= 1

    def test_15m_unchanged(self):
        assert st._parse_ttl("15m") == 900

    def test_1h_unchanged(self):
        assert st._parse_ttl("1h") == 3600

    def test_plain_number_minutes(self):
        assert st._parse_ttl("5") == 300


# ---------------------------------------------------------------------------
# FIX 5: .env key quote stripping in pre-commit get_key()
# ---------------------------------------------------------------------------

class TestEnvKeyQuoteStripping:
    def test_double_quoted_key_stripped(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text('MOA_GATE_KEY="quoted-key-value-1234"\n')
        monkeypatch.delenv("MOA_GATE_KEY", raising=False)
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))

        # Import pre-commit as a module
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "pre_commit", str(_PLUGIN_DIR / "hooks" / "pre-commit.py")
        )
        pc = importlib.util.load_from_spec = None  # not used
        pc_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pc_mod)

        key = pc_mod.get_key()
        assert key == "quoted-key-value-1234", f"Expected stripped key, got {key!r}"

    def test_single_quoted_key_stripped(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("MOA_GATE_KEY='single-quoted-key-5678'\n")
        monkeypatch.delenv("MOA_GATE_KEY", raising=False)
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))

        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "pre_commit2", str(_PLUGIN_DIR / "hooks" / "pre-commit.py")
        )
        pc_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pc_mod)

        key = pc_mod.get_key()
        assert key == "single-quoted-key-5678", f"Expected stripped key, got {key!r}"


# ---------------------------------------------------------------------------
# FIX 6: pre-commit get_state_file() session-aware path
# ---------------------------------------------------------------------------

class TestGetStateFile:
    def _load_pre_commit(self, name="pre_commit_fix6"):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            name, str(_PLUGIN_DIR / "hooks" / "pre-commit.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_no_session_returns_global(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        monkeypatch.delenv("HERMES_SESSION_ID", raising=False)
        mod = self._load_pre_commit("pc_no_session")
        result = mod.get_state_file()
        assert result == tmp_path / "moa-gate" / "state.json"

    def test_session_file_exists_returns_session_path(self, tmp_path, monkeypatch):
        session_id = "my-test-session-abc123"
        # _safe_session_id keeps alphanumeric + ._-
        safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in session_id)
        sessions_dir = tmp_path / "moa-gate" / "sessions"
        sessions_dir.mkdir(parents=True)
        session_file = sessions_dir / f"{safe}.json"
        session_file.write_text("{}")  # file must exist

        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        monkeypatch.setenv("HERMES_SESSION_ID", session_id)
        mod = self._load_pre_commit("pc_with_session")
        result = mod.get_state_file()
        assert result == session_file

    def test_session_id_set_but_file_absent_returns_global(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        monkeypatch.setenv("HERMES_SESSION_ID", "nonexistent-session-xyz")
        mod = self._load_pre_commit("pc_absent_session")
        result = mod.get_state_file()
        assert result == tmp_path / "moa-gate" / "state.json"
