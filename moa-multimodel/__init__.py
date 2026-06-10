"""MOA Multi-Model Review plugin — runs 3 real models as adversarial voices.

This plugin is the GENERATOR side of MOA. It produces real verdicts from
3 distinct models (Claude Sonnet, OpenAI Codex, Google Gemini-via-AGY)
and writes them to moa-gate's state.json so moa-gate's pre-commit hook
auto-approves the subsequent commit.

Workflow:
1. User runs `gh pr create` (or `/moa-multimodel review` manually)
2. pre_tool_call hook intercepts, runs `scripts/council.sh` which:
   a. Captures the diff to a per-run private temp file (mkstemp)
   b. Calls claude -p, codex exec, agy -p in sequence (with retry on rate limit)
   c. Extracts verdicts (APPROVE / REQUEST_CHANGES)
   d. Writes per-voice comment to <run-dir>/pr-<N>-<voice>.md
3. After council completes, hook posts comments + adds labels to PR
4. Hook writes state.json via moa-gate's state.approve()
5. moa-gate pre-commit hook sees approved state, allows git commit

Fail-back (verified 2026-06-08):
- claude rate limit: exit 130/124 OR stderr matches RATE_LIMIT_PATTERNS
- codex rate limit: "rate limit exceeded" / 429 / RATE_LIMIT_PATTERNS
- agy: silent fail (exit 0, 0 bytes) is env/credential, NOT rate limit
- 2/3 substantive voices sufficient signal; 1/3 blocks; 0/3 blocks
- skeptic dissent (safety role, mirrors moa-gate SAFETY_ROLES) withholds
  auto-approve even at 2/3 — manual review required

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
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

# Validate PR identifiers to prevent shell injection via slash command args
_PR_NUMBER_RE = re.compile(r"^[A-Za-z0-9_-]+$")

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


def _validate_pr_number(s: str) -> str:
    """Sanitize PR identifier — only alphanumeric, dash, underscore allowed.

    Returns "manual" if input contains anything else (prevents shell injection
    when the value is interpolated into prompt files).
    """
    s = (s or "").strip()
    if not s or not _PR_NUMBER_RE.match(s):
        return "manual"
    return s


def _resolve_default_branch(repo_path: str) -> str:
    """Resolve the repo's default branch (main / master / etc.).

    Order: origin/HEAD symref > probe main > probe master > "main".
    """
    try:
        proc = subprocess.run(
            ["git", "-C", repo_path, "symbolic-ref",
             "refs/remotes/origin/HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip().rsplit("/", 1)[-1]
    except Exception:
        pass
    for branch in ("main", "master"):
        try:
            proc = subprocess.run(
                ["git", "-C", repo_path, "rev-parse", "--verify", branch],
                capture_output=True, text=True, timeout=5,
            )
            if proc.returncode == 0:
                return branch
        except Exception:
            continue
    return "main"


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
    # so we look at the most recent commit vs the repo's default branch
    default_branch = _resolve_default_branch(repo_path)
    try:
        diff_proc = subprocess.run(
            ["git", "-C", repo_path, "diff", f"{default_branch}...HEAD"],
            capture_output=True, text=True, timeout=30,
        )
        if diff_proc.returncode != 0:
            logger.warning("moa-multimodel: git diff failed: %s", diff_proc.stderr)
            return None  # Don't block — let moa-gate handle if needed
        fd, diff_path = tempfile.mkstemp(
            prefix="moa-multimodel-diff-", suffix=".patch"
        )
        with os.fdopen(fd, "w") as f:
            f.write(diff_proc.stdout)
    except Exception as exc:
        logger.warning("moa-multimodel: diff capture failed: %s", exc)
        return None

    # diff_path created; ensure it and run_dir are cleaned up on every exit path
    run_dir: Optional[str] = None
    try:
        if not Path(diff_path).exists():
            return None

        # Auto-trigger fires at gh_pr_create time — the PR does not exist yet,
        # so we pass "manual" so council.sh skips the gh-pr-comment block.
        run_dir = _setup_voice_prompts(diff_path, "manual", repo_path)

        # Run the council script
        try:
            result = subprocess.run(
                ["bash", _COUNCIL_SCRIPT, diff_path, "manual"],
                capture_output=True, text=True, timeout=900,  # 15 min
                env={**os.environ,
                     "MOA_GATE_PLUGIN_PATH": _resolve_moa_gate_path(),
                     "MOA_RUN_DIR": run_dir},
            )
            logger.info("moa-multimodel council: exit=%d\n%s",
                        result.returncode, result.stdout[-2000:])
            if result.returncode == 2:
                return {
                    "action": "block",
                    "message": (
                        "🛑 MOA Multi-Model: fewer than 2 substantive council "
                        "voices — manual review required.\n"
                        "   Run `/moa-multimodel review "
                        f"{diff_path}` to retry."
                    ),
                }
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
    finally:
        try:
            os.unlink(diff_path)
        except OSError:
            pass
        if run_dir is not None:
            shutil.rmtree(run_dir, ignore_errors=True)

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
    pr_number = _validate_pr_number(parts[1] if len(parts) > 1 else "")
    if not Path(diff_path).exists():
        return f"❌ Diff file not found: {diff_path}"

    repo_path = _resolve_repo_path() or os.getcwd()
    run_dir = _setup_voice_prompts(diff_path, pr_number, repo_path)

    try:
        result = subprocess.run(
            ["bash", _COUNCIL_SCRIPT, diff_path, pr_number],
            capture_output=True, text=True, timeout=900,
            env={**os.environ,
                 "MOA_GATE_PLUGIN_PATH": _resolve_moa_gate_path(),
                 "MOA_RUN_DIR": run_dir},
        )
        return (
            f"🛡️ MOA Multi-Model Council: exit={result.returncode}\n\n"
            f"{result.stdout[-3000:]}"
        )
    except Exception as exc:
        return f"❌ Council script failed: {exc}"
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def _setup_voice_prompts(diff_path: str, pr_number: str, repo_path: str) -> str:
    """Write per-voice prompt files into a per-run private temp directory.

    Creates a fresh directory via mkdtemp (prefix "moa-multimodel-") so each
    run is fully isolated.  Fixed /tmp paths were pre-creatable by other local
    users (symlink/TOCTOU attack); per-run dirs eliminate that risk.

    All interpolated values are shell-quoted via shlex to prevent injection
    (diff_path/repo_path may come from env or slash command args; pr_number is
    already validated by _validate_pr_number).

    Returns the path to the per-run directory so callers can pass it as
    MOA_RUN_DIR to council.sh.
    """
    pr_number = _validate_pr_number(pr_number)

    architect = (
        f"MOA Architect review. Read diff at {diff_path} and verify by reading "
        f"files at {repo_path}. PR #{pr_number}. Focus: correctness, idiomatic "
        f"code, semantics, test intent regression. Return ONLY: APPROVE or "
        f"REQUEST_CHANGES, 2-4 bullets. Be terse."
    )
    skeptic = (
        f"MOA Skeptic review. Read {diff_path} and verify by reading files at "
        f"{repo_path}. PR #{pr_number}. Focus: reasoning bugs, over-broad "
        f"allowances, missed lints, hidden assumptions. Return ONLY: APPROVE "
        f"or REQUEST_CHANGES, 2-4 bullets with file:line citations."
    )
    pragmatist = (
        f"MOA Pragmatist review. Read diff at {diff_path} and files at "
        f"{repo_path}. PR #{pr_number}. Focus: operator migration risk, "
        f"runtime cost, scope creep, breaking changes. Return ONLY: APPROVE "
        f"or REQUEST_CHANGES, 2-4 bullets. Be terse."
    )
    run_dir = Path(tempfile.mkdtemp(prefix="moa-multimodel-"))
    (run_dir / "claude-cmd.sh").write_text(
        f"#!/bin/bash\nclaude -p {shlex.quote(architect)} --model sonnet\n"
    )
    (run_dir / "codex-cmd.sh").write_text(
        f"#!/bin/bash\ncodex exec {shlex.quote(skeptic)}\n"
    )
    (run_dir / "agy-cmd.sh").write_text(
        f"#!/bin/bash\nagy -p {shlex.quote(pragmatist)}\n"
    )
    for f in ("claude-cmd.sh", "codex-cmd.sh", "agy-cmd.sh"):
        (run_dir / f).chmod(0o755)
    return str(run_dir)


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
Skeptic dissent (safety role) withholds auto-approve even at 2/3.

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
