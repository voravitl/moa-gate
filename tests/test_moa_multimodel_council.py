"""Regression tests for moa-multimodel/scripts/council.sh.

Covers two bugs fixed 2026-06-10:
1. set -e killed the script when a voice CLI exited non-zero, so the
   HARD_FAIL / rate-limit handling in run_voice() was dead code.
2. exit_code=2 (fewer than 2 substantive voices) was set but the script
   always ended with `exit 0`, so failures reported success.
"""
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
COUNCIL = REPO / "moa-multimodel" / "scripts" / "council.sh"

VOICE_CMD_FILES = ("claude-cmd.sh", "codex-cmd.sh", "agy-cmd.sh")


def _write_cmd(name: str, body: str) -> None:
    p = Path("/tmp") / name
    p.write_text(f"#!/bin/bash\n{body}\n")
    p.chmod(0o755)


def _run_council(tmp_path: Path) -> subprocess.CompletedProcess:
    diff = tmp_path / "diff.patch"
    diff.write_text("--- a/x\n+++ b/x\n")
    env = {
        **os.environ,
        # Point at a dir without state.py so the state-write branch is skipped
        "MOA_GATE_PLUGIN_PATH": str(tmp_path / "no-plugin"),
    }
    return subprocess.run(
        ["bash", str(COUNCIL), str(diff), "manual"],
        capture_output=True, text=True, timeout=60, env=env,
    )


@pytest.fixture(autouse=True)
def _clean_status():
    Path("/tmp/moa-status").unlink(missing_ok=True)
    yield


def test_hard_fail_voice_does_not_abort_script(tmp_path):
    """A failing voice CLI must be recorded as HARD_FAIL, not kill the run."""
    for f in VOICE_CMD_FILES:
        _write_cmd(f, 'echo "tool exploded with some error"; exit 1')
    result = _run_council(tmp_path)
    status = Path("/tmp/moa-status").read_text()
    assert status.count("HARD_FAIL") == 3, status
    assert "MOA Council Summary" in result.stdout


def test_exit_2_when_fewer_than_2_substantive_voices(tmp_path):
    """0/3 substantive verdicts must propagate exit code 2 (blocking)."""
    for f in VOICE_CMD_FILES:
        _write_cmd(f, 'echo "tool exploded with some error"; exit 1')
    result = _run_council(tmp_path)
    assert result.returncode == 2, result.stdout


def test_exit_0_when_2_of_3_approve(tmp_path):
    """2/3 APPROVE with one hard failure is sufficient signal — exit 0."""
    _write_cmd("claude-cmd.sh", 'echo "Looks correct and idiomatic. APPROVE"')
    _write_cmd("codex-cmd.sh", 'echo "No hidden assumptions found. APPROVE"')
    _write_cmd("agy-cmd.sh", 'echo "credential failure"; exit 1')
    result = _run_council(tmp_path)
    assert result.returncode == 0, result.stdout
    assert "Approvals: 2" in result.stdout
    assert "Substantive verdicts: 2/3" in result.stdout


def test_status_reason_field_not_leaked_into_summary(tmp_path):
    """Failure reason (3rd |-field) must not appear in the verdict summary."""
    for f in VOICE_CMD_FILES:
        _write_cmd(f, 'echo "tool exploded with some error"; exit 1')
    result = _run_council(tmp_path)
    assert "exit_1=" not in result.stdout
    assert "architect=ESCALATED" in result.stdout
