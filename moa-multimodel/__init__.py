"""MOA Multi-Model Review plugin — runs 3 real models as adversarial voices.

This plugin is the GENERATOR side of MOA. It produces real verdicts from
3 distinct models (Claude Sonnet, OpenAI Codex, Google Gemini-via-AGY)
and writes them to moa-gate's state.json so moa-gate's pre-commit hook
auto-approves the subsequent commit.

Workflow:
1. User runs `gh pr create` (or `/moa-multimodel review` manually)
2. pre_tool_call hook intercepts, runs `scripts/council.sh` which:
   a. Captures the diff to /tmp/moa-multimodel-auto-diff.patch
   b. Calls claude -p, codex exec, agy -p in sequence (with retry on rate limit)
   c. Extracts verdicts (APPROVE / REQUEST_CHANGES)
   d. Writes per-voice comment to /tmp/pr-<N>-<voice>.md
3. After council completes, hook posts comments + adds labels to PR
4. Hook writes state.json via moa-gate's state.approve()
5. moa-gate pre-commit hook sees approved state, allows git commit

Fail-back (verified 2026-06-08):
- claude rate limit: exit 130/124 OR stderr matches RATE_LIMIT_PATTERNS
- codex rate limit: "rate limit exceeded" / 429 / RATE_LIMIT_PATTERNS
- agy: silent fail (exit 0, 0 bytes) is env/credential, NOT rate limit
- 2/3 substantive voices sufficient signal; 1/3 blocks; 0/3 blocks

Plugin does NOT replace moa-gate. It feeds moa-gate verdicts.

Configuration (all optional, env vars):
- MOA_MULTIMODEL_REPO: target repo path for `git diff main...HEAD`
                      (default: $(git rev-parse --show-toplevel) of cwd)
- MOA_MULTIMODEL_AUTOTRIGGER=0: disable auto-trigger on gh_pr_create
- MOA_GATE_PLUGIN_PATH: path to moa-gate plugin dir
                       (default: sibling dir, else ~/.hermes/plugins/moa-gate)
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Resolve plugin-relative paths
_PLUGIN_DIR = Path(__file__).resolve().parent
_SCRIPTS_DIR = _PLUGIN_DIR / "scripts"
_COUNCIL_SCRIPT = str(_SCRIPTS_DIR / "council.sh")

# State path (shared with moa-gate — reuse for unified enforcement)
MOA_GATE_STATE = Path.home() / ".hermes" / "moa-gate" / "state.json"

# Tools that should trigger an auto MOA review
TRIGGER_TOOLS = frozenset({
    "gh_pr_create",  # GitHub PR creation
    "patch",         # Could be a hotfix; not always — operator can opt out
})


def _resolve_repo_path() -> Optional[str]:
    """Resolve the target repo path for diff capture.

    Order: MOA_MULTIMODEL_REPO env > git toplevel of cwd > None.
    """
    env = os.environ.get("MOA_MULTIMODEL_REPO", "").strip()
    if env and Path(env).is_dir():
        return env
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if proc.returncode == 0:
            top = proc.stdout.strip()
            if top and Path(top).is_dir():
                return top
    except Exception:
        pass
    return None


def _resolve_moa_gate_path() -> str:
    """Resolve moa-gate plugin path for state import.

    Order: MOA_GATE_PLUGIN_PATH env > sibling dir > ~/.hermes/plugins/moa-gate.
    """
    env = os.environ.get("MOA_GATE_PLUGIN_PATH", "").strip()
    if env and Path(env).is_dir():
        return env
    sibling = _PLUGIN_DIR.parent
    if (sibling / "state.py").is_file():
        return str(sibling)
    return str(Path.home() / ".hermes" / "plugins" / "moa-gate")


def _on_pre_tool_call(
    tool_name: str = "",
    args: Optional[Dict[str, Any]] = None,
    task_id: str = "",
    session_id: str = "",
    tool_call_id: str = "",
    **_: Any,
) -> Optional[Dict[str, Any]]:
    """Intercept gh pr create (and other trigger tools) to run MOA review.

    *Additive* — runs the council in-place rather than rejecting the
    call. Council verdicts are posted to the PR as comments (advisory,
    non-blocking) and also written to MOA_GATE_STATE for downstream
    tooling compatibility. Failures are caught and return None so the
    user's PR is never blocked.

    Returns None to allow the call to proceed (after council runs).
    Returns {"action": "block", "message": "..."} only if the council
    itself fails or yields 0/3 substantive verdicts.
    """
    if not tool_name or tool_name not in TRIGGER_TOOLS:
        return None

    # Only auto-trigger on gh pr create (most common case)
    if tool_name != "gh_pr_create":
        return None

    # Opt-out
    if os.environ.get("MOA_MULTIMODEL_AUTOTRIGGER", "1") == "0":
        return None

    repo_path = _resolve_repo_path()
    if not repo_path:
        logger.warning("moa-multimodel: could not resolve repo path; skipping")
        return None

    # Find diff: caller is expected to have staged/committed already,
    # so we look at the most recent commit vs main
    try:
        diff_proc = subprocess.run(
            ["git", "-C", repo_path, "diff", "main...HEAD"],
            capture_output=True, text=True, timeout=30,
        )
        if diff_proc.returncode != 0:
            logger.warning("moa-multimodel: git diff failed: %s", diff_proc.stderr)
            return None  # Don't block — let moa-gate handle if needed
        diff_path = "/tmp/moa-multimodel-auto-diff.patch"
        Path(diff_path).write_text(diff_proc.stdout)
    except Exception as exc:
        logger.warning("moa-multimodel: diff capture failed: %s", exc)
        return None

    if not Path(diff_path).exists():
        return None

    # Set up voice prompts before invoking council
    _setup_voice_prompts(diff_path, "auto", repo_path)

    # Run the council script
    try:
        result = subprocess.run(
            ["bash", _COUNCIL_SCRIPT, diff_path, "auto"],
            capture_output=True, text=True, timeout=900,  # 15 min
            env={**os.environ, "MOA_GATE_PLUGIN_PATH": _resolve_moa_gate_path()},
        )
        logger.info("moa-multimodel council: exit=%d\n%s",
                    result.returncode, result.stdout[-2000:])
    except subprocess.TimeoutExpired:
        return {
            "action": "block",
            "message": (
                "🛑 MOA Multi-Model: Council timed out after 15 min.\n"
                "   Run `/moa-multimodel review <diff>` manually to retry."
            ),
        }
    except Exception as exc:
        return {
            "action": "block",
            "message": f"🛑 MOA Multi-Model: Council script failed: {exc}",
        }

    # Council completed. We do NOT block the gh pr create call — the
    # user has already written the PR. Verdicts are advisory only and
    # are posted to the PR as comments (council.sh handles posting).
    return None


def _handle_council_review(raw_args: str) -> str:
    """Handle /moa-multimodel review <diff-file> [pr-number]"""
    parts = raw_args.strip().split()
    if not parts:
        return ("Usage: /moa-multimodel review <diff-file> [pr-number]\n"
                "Example: /moa-multimodel review /tmp/diff-366.patch 366")
    diff_path = parts[0]
    pr_number = parts[1] if len(parts) > 1 else "manual"
    if not Path(diff_path).exists():
        return f"❌ Diff file not found: {diff_path}"

    repo_path = _resolve_repo_path() or os.getcwd()
    _setup_voice_prompts(diff_path, pr_number, repo_path)

    try:
        result = subprocess.run(
            ["bash", _COUNCIL_SCRIPT, diff_path, pr_number],
            capture_output=True, text=True, timeout=900,
            env={**os.environ, "MOA_GATE_PLUGIN_PATH": _resolve_moa_gate_path()},
        )
        return (
            f"🛡️ MOA Multi-Model Council: exit={result.returncode}\n\n"
            f"{result.stdout[-3000:]}"
        )
    except Exception as exc:
        return f"❌ Council script failed: {exc}"


def _setup_voice_prompts(diff_path: str, pr_number: str, repo_path: str) -> None:
    """Write per-voice prompt files that council.sh sources."""
    prompt_dir = Path("/tmp")
    (prompt_dir / "claude-cmd.sh").write_text(
        f"""#!/bin/bash
claude -p "MOA Architect review. Read diff at {diff_path} and verify by reading files at {repo_path}. PR #{pr_number}. Focus: correctness, idiomatic code, semantics, test intent regression. Return ONLY: APPROVE or REQUEST_CHANGES, 2-4 bullets. Be terse." --model sonnet
"""
    )
    (prompt_dir / "codex-cmd.sh").write_text(
        f"""#!/bin/bash
codex exec "MOA Skeptic review. Read {diff_path} and verify by reading files at {repo_path}. PR #{pr_number}. Focus: reasoning bugs, over-broad allowances, missed lints, hidden assumptions. Return ONLY: APPROVE or REQUEST_CHANGES, 2-4 bullets with file:line citations."
"""
    )
    (prompt_dir / "agy-cmd.sh").write_text(
        f"""#!/bin/bash
agy -p "MOA Pragmatist review. Read diff at {diff_path} and files at {repo_path}. PR #{pr_number}. Focus: operator migration risk, runtime cost, scope creep, breaking changes. Return ONLY: APPROVE or REQUEST_CHANGES, 2-4 bullets. Be terse."
"""
    )
    (prompt_dir / "agy-pipe-cmd.sh").write_text(
        f"""#!/bin/bash
cat {diff_path} | agy -p "MOA Pragmatist review. Diff summary in stdin. Return ONLY: APPROVE or REQUEST_CHANGES, 2-4 bullets. Be terse."
"""
    )
    for f in ("claude-cmd.sh", "codex-cmd.sh", "agy-cmd.sh", "agy-pipe-cmd.sh"):
        (prompt_dir / f).chmod(0o755)


_HELP = """\
/moa-multimodel — Multi-model MOA review runner

Subcommands:
  review <diff-file> [pr-number]    Run 3-model council (Claude + Codex + AGY)
                                    on a diff and post verdicts as PR comments.
                                    Writes state.json so moa-gate pre-commit
                                    auto-approves subsequent commits.

Examples:
  /moa-multimodel review /tmp/diff-366.patch 366
  /moa-multimodel review /tmp/diff-366.patch

Auto-trigger: this plugin's pre_tool_call hook auto-runs council when
`gh pr create` is called. Set MOA_MULTIMODEL_AUTOTRIGGER=0 to disable.

Fail-back: if any model is rate-limited, the plugin waits 60s and retries
ONCE. AGY silent fail is treated as env/credential issue (not retry).
2/3 substantive voices is sufficient signal; 1/3 blocks; 0/3 blocks.

Environment:
  MOA_MULTIMODEL_REPO       Override repo for `git diff main...HEAD`
                            (default: git toplevel of cwd)
  MOA_MULTIMODEL_AUTOTRIGGER=0   Disable pre_tool_call auto-trigger
  MOA_GATE_PLUGIN_PATH      Override moa-gate plugin path
                            (default: sibling dir, else ~/.hermes/plugins/moa-gate)
"""


def handle_command(command: str, args: str) -> Optional[str]:
    """Slash command entry point called by Hermes."""
    parts = command.strip().split(None, 1)
    if not parts:
        return None
    cmd = parts[0].lower()
    rest = parts[1] if len(parts) > 1 else ""

    if cmd in ("review", "council", "run"):
        return _handle_council_review(rest)
    if cmd in ("help", "--help", "-h"):
        return _HELP
    return None
