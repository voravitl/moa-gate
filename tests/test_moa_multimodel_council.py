"""Regression tests for moa-multimodel/scripts/council.sh.

Covers two bugs fixed 2026-06-10:
1. set -e killed the script when a voice CLI exited non-zero, so the
   HARD_FAIL / rate-limit handling in run_voice() was dead code.
2. exit_code=2 (fewer than 2 substantive voices) was set but the script
   always ended with `exit 0`, so failures reported success.

Each test creates its own per-run directory (tmp_path / "run") and passes
it as MOA_RUN_DIR, matching the per-run isolation introduced in council.sh.
"""
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
COUNCIL = REPO / "moa-multimodel" / "scripts" / "council.sh"

VOICE_CMD_FILES = ("claude-cmd.sh", "codex-cmd.sh", "agy-cmd.sh")


def _write_cmd(run_dir: Path, name: str, body: str) -> None:
    p = run_dir / name
    p.write_text(f"#!/bin/bash\n{body}\n")
    p.chmod(0o755)


def _run_council(tmp_path: Path, run_dir: Path) -> subprocess.CompletedProcess:
    diff = tmp_path / "diff.patch"
    diff.write_text("--- a/x\n+++ b/x\n")
    env = {
        **os.environ,
        # Point at a dir without state.py so the state-write branch is skipped
        "MOA_GATE_PLUGIN_PATH": str(tmp_path / "no-plugin"),
        "MOA_RUN_DIR": str(run_dir),
    }
    return subprocess.run(
        ["bash", str(COUNCIL), str(diff), "manual"],
        capture_output=True, text=True, timeout=60, env=env,
    )


def test_hard_fail_voice_does_not_abort_script(tmp_path):
    """A failing voice CLI must be recorded as HARD_FAIL, not kill the run."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    for f in VOICE_CMD_FILES:
        _write_cmd(run_dir, f, 'echo "tool exploded with some error"; exit 1')
    result = _run_council(tmp_path, run_dir)
    status = (run_dir / "moa-status").read_text()
    assert status.count("HARD_FAIL") == 3, status
    assert "MOA Council Summary" in result.stdout


def test_exit_2_when_fewer_than_2_substantive_voices(tmp_path):
    """0/3 substantive verdicts must propagate exit code 2 (blocking)."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    for f in VOICE_CMD_FILES:
        _write_cmd(run_dir, f, 'echo "tool exploded with some error"; exit 1')
    result = _run_council(tmp_path, run_dir)
    assert result.returncode == 2, result.stdout


def test_exit_0_when_2_of_3_approve(tmp_path):
    """2/3 APPROVE with one hard failure is sufficient signal — exit 0."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_cmd(run_dir, "claude-cmd.sh", 'echo "Looks correct and idiomatic. APPROVE"')
    _write_cmd(run_dir, "codex-cmd.sh", 'echo "No hidden assumptions found. APPROVE"')
    _write_cmd(run_dir, "agy-cmd.sh", 'echo "credential failure"; exit 1')
    result = _run_council(tmp_path, run_dir)
    assert result.returncode == 0, result.stdout
    assert "Approvals: 2" in result.stdout
    assert "Substantive verdicts: 2/3" in result.stdout


def test_status_reason_field_not_leaked_into_summary(tmp_path):
    """Failure reason (3rd |-field) must not appear in the verdict summary."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    for f in VOICE_CMD_FILES:
        _write_cmd(run_dir, f, 'echo "tool exploded with some error"; exit 1')
    result = _run_council(tmp_path, run_dir)
    assert "exit_1=" not in result.stdout
    assert "architect=ESCALATED" in result.stdout


def test_prompt_echo_does_not_override_final_verdict(tmp_path):
    """An echoed instruction line containing REQUEST_CHANGES must not beat
    the model's final standalone APPROVE (last keyword wins)."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    body = ('echo "Return ONLY: APPROVE or REQUEST_CHANGES"; '
            'echo "Code is correct and idiomatic."; echo "APPROVE"')
    for f in VOICE_CMD_FILES:
        _write_cmd(run_dir, f, body)
    result = _run_council(tmp_path, run_dir)
    assert result.returncode == 0, result.stdout
    assert "Approvals: 3" in result.stdout


def test_unclear_verdict_counted_as_escalated(tmp_path):
    """Output with no verdict keyword is UNCLEAR — must count as escalated,
    not vanish from the summary."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_cmd(run_dir, "claude-cmd.sh", 'echo "Looks correct and idiomatic. APPROVE"')
    _write_cmd(run_dir, "codex-cmd.sh", 'echo "ambiguous rambling without any keywords"')
    _write_cmd(run_dir, "agy-cmd.sh", 'echo "more rambling, still no decision made"')
    result = _run_council(tmp_path, run_dir)
    assert result.returncode == 2, result.stdout  # only 1 substantive voice
    assert "skeptic=UNCLEAR" in result.stdout
    assert "Escalated/empty: 2" in result.stdout


def test_skeptic_dissent_withholds_auto_approve(tmp_path):
    """2/3 APPROVE but skeptic dissents — safety role blocks auto-approve."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_cmd(run_dir, "claude-cmd.sh", 'echo "Correct and idiomatic. APPROVE"')
    _write_cmd(run_dir, "codex-cmd.sh",
               'echo "Hidden assumption in tier logic. REQUEST_CHANGES"')
    _write_cmd(run_dir, "agy-cmd.sh", 'echo "No migration risk found. APPROVE"')
    result = _run_council(tmp_path, run_dir)
    assert result.returncode == 0, result.stdout
    assert "Skeptic dissent" in result.stdout
    assert "Writing moa-gate state.json" not in result.stdout


def test_non_safety_dissent_still_auto_approves(tmp_path):
    """2/3 APPROVE with pragmatist (non-safety) dissent → auto-approve runs."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_cmd(run_dir, "claude-cmd.sh", 'echo "Correct and idiomatic. APPROVE"')
    _write_cmd(run_dir, "codex-cmd.sh", 'echo "No hidden assumptions. APPROVE"')
    _write_cmd(run_dir, "agy-cmd.sh", 'echo "Scope creep concern. REQUEST_CHANGES"')
    result = _run_council(tmp_path, run_dir)
    assert result.returncode == 0, result.stdout
    assert "Writing moa-gate state.json" in result.stdout
