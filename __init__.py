"""MOA Gate plugin — pre_tool_call enforcement + slash commands.

Intercepts write/destructive tools and checks HMAC-signed state.
Blocks unless MOA council has approved.

Supports auto-approve via council majority (>=80% threshold),
weighted veto (Critic/Skeptic dissent → Tier 2 manual only),
cool-down period, shadow mode, and rate limiting.

Blocked tools (all modes):
    patch, write_file, write, git_commit, gh_pr_create,
    skill_manage, terminal, process
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure plugin directory is on sys.path for sibling module imports
# (Hermes may not always add it; needed for "import state" to work)
_PLUGIN_DIR = str(Path(__file__).resolve().parent)
_added_plugin_path = False
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)
    _added_plugin_path = True

try:
    import state as st
    import audit as au
    import tier as ti
finally:
    # Clean up to avoid namespace pollution
    if _added_plugin_path:
        sys.path.remove(_PLUGIN_DIR)
del _PLUGIN_DIR, _added_plugin_path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Tools that are ALWAYS blocked unless gate is approved
BLOCKED_TOOLS = frozenset({
    "patch",
    "write_file",
    "write",
    "git_commit",
    "gh_pr_create",
    "skill_manage",
    "terminal",
    "process",
})

# Read-only terminal commands allowed even when gate is pending
TERMINAL_READONLY_PATTERNS = re.compile(
    r"^\s*(?:"
    # git read-only subcommands
    r"git\s+(?:log|diff|status|show|branch|blame|shortlog|rev-parse|describe|ls-files|ls-tree|remote|config|tag\s+-l|tag\s+--list|stash\s+list)\s*(?!.*[|;&>])"
    # safe read-only commands
    r"|(?:ls|cat|head|tail|which|echo|env|pwd|find|grep|rg|file|wc|sort|uniq|cut|date|cal|df|du|ps|top)\s+(?!.*[|;&>])"
    r"|(?:ls|cat|head|tail|which|echo|env|pwd|df|du|ps|top|date|cal)\s*$"
    # build/test tools
    r"|(?:cargo\s+(?:check|test|build|fmt|clippy|doc)|npm\s+(?:test|run|ls)|pytest|python3?\s+-m\s+(?:pytest|unittest)|make)\s*(?!.*[|;&>])"
    # AI review (safe)
    r"|claude\s+-p\s+"
    r")",
    re.IGNORECASE,
)

# Auto-approve settings (can be overridden via env)
AUTO_THRESHOLD = float(os.environ.get("MOA_GATE_AUTO_THRESHOLD", "0.8"))  # 80%
AUTO_RATE_LIMIT = int(os.environ.get("MOA_GATE_AUTO_RATE_LIMIT", "5"))   # per hour
AUTO_RATE_WINDOW = 3600  # 1 hour in seconds
SHADOW_MODE = os.environ.get("MOA_GATE_SHADOW_MODE", "0") == "1"
COOLDOWN_SECS = int(os.environ.get("MOA_GATE_COOLDOWN_SECS", "120"))
SAFETY_ROLES = frozenset({"critic", "skeptic"})

# Rate limiter state file
RATE_FILE = Path.home() / ".hermes" / "moa-gate" / ".rate_counter.json"


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

def _check_rate_limit() -> Tuple[bool, int]:
    """Check if auto-approve is within rate limit.

    Returns (allowed: bool, remaining_count: int).
    Uses a simple JSON file with timestamps.
    """
    now = time.time()
    cutoff = now - AUTO_RATE_WINDOW

    try:
        RATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        if RATE_FILE.exists():
            raw = RATE_FILE.read_text()
            timestamps = json.loads(raw) if raw.strip() else []
        else:
            timestamps = []

        # Prune old entries
        timestamps = [ts for ts in timestamps if ts > cutoff]

        allowed = len(timestamps) < AUTO_RATE_LIMIT
        remaining = AUTO_RATE_LIMIT - len(timestamps)

        if allowed:
            timestamps.append(now)
            RATE_FILE.write_text(json.dumps(timestamps))

        return allowed, remaining
    except Exception as exc:
        logger.warning("MOA Gate rate limiter error: %s", exc)
        return True, -1  # Fail-open: allow on error


# ---------------------------------------------------------------------------
# GH Issue creation helper
# ---------------------------------------------------------------------------

def _create_dissent_issue(dissented: List[str], council_result: Dict[str, Any]) -> None:
    """Auto-create GitHub issue for dissent feedback.

    Runs `gh issue create` as a background process.
    If gh CLI is not available, logs the dissent to audit.
    """
    voices_str = ", ".join(dissented)
    task_desc = council_result.get("task_description", "Unknown")
    dissent_reason = council_result.get("dissent_reason", "")
    approved_by = ", ".join(council_result.get("approved_by", []))

    body = (
        f"## MOA Council Dissent\n\n"
        f"**Dissented voice(s):** {voices_str}\n"
        f"**Dissent reason:** {dissent_reason}\n\n"
        f"**Task:** {task_desc}\n"
        f"**Approved by:** {approved_by}\n"
        f"**Tier:** Auto (≥80% majority)\n\n"
        f"**Action required:** Review dissent feedback and resolve before merge."
    )
    title = f"MOA Dissent: {task_desc[:60]}"

    au.log("dissent_issue", reason=body, by=dissented)

    try:
        import subprocess
        subprocess.Popen(
            ["gh", "issue", "create", "--title", title, "--body", body],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        logger.debug("MOA Gate: gh CLI not available, dissent issue not created")


# ---------------------------------------------------------------------------
# Pre-tool-call hook
# ---------------------------------------------------------------------------

def _on_pre_tool_call(
    tool_name: str = "",
    args: Optional[Dict[str, Any]] = None,
    task_id: str = "",
    session_id: str = "",
    tool_call_id: str = "",
    **_: Any,
) -> Optional[Dict[str, Any]]:
    """Check gate before any blocked tool executes.

    Extended checks:
    1. Cool-down active? → block with option to override
    2. Shadow mode? → block but log
    3. Standard pending/approved/rejected check

    Returns {"action": "block", "message": "..."} if blocked.
    Returns None to allow.
    """
    if not tool_name:
        return None

    session_id = session_id or os.environ.get("HERMES_SESSION_ID", "") or f"anon-{os.getpid():d}"

    # Sync HMAC key from .env — keeps Hermes in sync if subprocess overwrote
    st.sync_key()

    # Check if tool is in blocked list
    if tool_name not in BLOCKED_TOOLS:
        return None

    # Terminal read-only whitelist
    if tool_name == "terminal" and isinstance(args, dict):
        cmd = args.get("command", "")
        if isinstance(cmd, str) and TERMINAL_READONLY_PATTERNS.match(cmd):
            return None

    # Read per-session state
    state = st.read(session_id)
    status = state.get("status", "pending")

    if status == "approved":
        # ---- Cool-down check ----
        if st.is_in_cooldown(state):
            cd = state.get("cool_down_until", "?")
            au.log("block", tool=tool_name, reason="cool_down_active",
                   session_id=session_id)
            return {
                "action": "block",
                "message": (
                    f"🛑 MOA Gate: Cool-down active until {cd}\n"
                    f"   Auto-approve is in cool-down period.\n"
                    f"   To override: `/moa-approve --override --reason \"...\"`\n"
                    f"   Or wait for cool-down to expire."
                ),
            }

        # ---- Shadow mode check ----
        if SHADOW_MODE and state.get("auto_approved"):
            au.log("shadow_block", tool=tool_name,
                   by=state.get("approved_by", []),
                   session_id=session_id)
            return {
                "action": "block",
                "message": (
                    "🛑 MOA Gate: Shadow mode active — auto-approve recorded "
                    "but not executed.\n"
                    f"   Tool: {tool_name}\n"
                    f"   Run `/moa-approve --by ... --reason \"...\"` for manual approval."
                ),
            }

        # ---- Session isolation ----
        allowed_session = state.get("session_id", "")
        if allowed_session:
            effective_session = session_id or f"anon-{os.getpid():d}"
            if effective_session != allowed_session:
                au.log("block", tool=tool_name, reason="session_mismatch",
                       session_id=session_id)
                return {
                    "action": "block",
                    "message": (
                        "🛑 MOA Gate: Approval from different session. "
                        "Run `/moa-revoke` then `/moa-approve`."
                    ),
                }

        au.log("allow", tool=tool_name, by=state.get("approved_by", []),
               session_id=session_id)
        return None  # Allow

    # Block — pending or any error
    if status == "pending":
        msg = (
            f"🛑 MOA Gate: Write tool blocked — \"{tool_name}\"\n"
            "  MOA council approval required.\n"
            "  ⏏ After approval, retry this operation immediately.\n"
            "  Run `/moa-adviser` for a multi-model review, then:\n"
            "  `/moa-approve --by <voices> --reason \"<reason>\"`"
        )
    elif status == "rejected":
        msg = f"🛑 MOA Gate: Rejected — {state.get('reason', 'No reason')}"
    else:
        msg = "🛑 MOA Gate: Error — state check failed. Try `/moa-revoke`."

    au.log("block", tool=tool_name, reason=status, session_id=session_id)
    return {"action": "block", "message": msg}


# ---------------------------------------------------------------------------
# Council-complete handler
# ---------------------------------------------------------------------------

def _handle_council_complete(raw_args: str) -> str:
    """Process MOA council results and decide auto-approve.

    Expected JSON argument::
        {
            "votes": {"architect": "approve", "critic": "dissent", ...},
            "task_description": "...",
            "dissent_reason": "...",
            "changed_paths": ["src/auth.rs", ...],
            "diff_keywords": ["refactor", ...]
        }

    Logic:
    1. Count approve/dissent
    2. Check threshold >=80%
    3. Weighted veto: Critic/Skeptic dissent → Tier 2
    4. Classify tier (keywords + vote)
    5. Shadow mode check
    6. Rate limit check
    7. Auto-approve or tell user

    Returns human-readable result.
    """
    # Parse JSON args
    try:
        council = json.loads(raw_args.strip())
    except (json.JSONDecodeError, ValueError) as exc:
        return f"❌ Invalid JSON: {exc}\n  Usage: /moa-council-complete '{{...}}'"

    votes = council.get("votes", {})
    task_desc = council.get("task_description", "")
    dissent_reason = council.get("dissent_reason", "")
    changed_paths = council.get("changed_paths", [])
    diff_keywords = council.get("diff_keywords", [])
    mode = council.get("mode", "cloud")  # moa | cli | cloud

    if not votes:
        return "❌ No votes provided."

    # Build mode warning prefix
    mode_warning = ""
    if mode == "cloud":
        mode_warning = (
            "\n⚠️  CLOUD MODE — ทุก voice ใช้ model เดียวกัน (session model)\n"
            "   diversity จาก prompt engineering เท่านั้น\n"
            "   → ควรใช้ MOA Tool mode (mixture_of_agents) หรือติดตั้ง CLI tools\n"
        )
    elif mode == "cli":
        mode_warning = "\n⚡ CLI mode — real 3 models (claude + codex + agy)\n"
    elif mode == "moa":
        mode_warning = "\n🎯 MOA Tool mode — real 5 models ต่างบริษัท\n"

    total = len(votes)
    approved_names = [v for v, s in votes.items() if s == "approve"]
    dissented_names = [v for v, s in votes.items() if s == "dissent"]
    approved_count = len(approved_names)

    pct = approved_count / total if total > 0 else 0.0

    # --- Step 1: Check threshold ---
    if pct < AUTO_THRESHOLD:
        return (
            f"❌ Cannot auto-approve: {approved_count}/{total} "
            f"({pct:.0%}) below {AUTO_THRESHOLD:.0%} threshold.\n"
            f"   Run `/moa-approve --by {','.join(approved_names)} "
            f"--reason \"<reason>\"` for manual approval."
        )

    # --- Step 2: Weighted veto ---
    safety_dissent = set(dissented_names) & SAFETY_ROLES
    if safety_dissent:
        return (
            f"🛑 Weighted veto: {', '.join(safety_dissent)} dissented.\n"
            f"   Critic/Skeptic dissent requires manual approval.\n"
            f"   Run `/moa-approve --by {','.join(approved_names)} "
            f"--reason \"<reason>\"`"
        )

    # --- Step 3: Classify tier ---
    keyword_tier = ti.classify_by_keywords(task_desc, changed_paths, diff_keywords)
    voice_tiers = council.get("voice_tiers", {})
    vote_tier = ti.classify_by_votes(voice_tiers)
    final_tier = max(keyword_tier, vote_tier)

    if final_tier == ti.TIER_2:
        return (
            f"📋 Council {approved_count}/{total} approve (Tier 2 — Manual)\n"
            f"   Tier 2 change detected — requires human approval.\n"
            f"   Run `/moa-approve --by {','.join(approved_names)} "
            f"--reason \"<reason>\"`"
        )

    # --- Step 4: Rate limit ---
    allowed, remaining = _check_rate_limit()
    if not allowed:
        au.log("rate_limited", by=approved_names, reason=f"rate_limit_hit",
               session_id=os.environ.get("HERMES_SESSION_ID", ""))
        return (
            f"⏳ Rate-limited: {AUTO_RATE_LIMIT} auto-approves/hour reached.\n"
            f"   Wait or use `/moa-approve --by ... --reason \"...\"` for manual."
        )

    # --- Step 5: Shadow mode? ---
    session_id = os.environ.get("HERMES_SESSION_ID", "") or f"anon-{os.getpid():d}"
    council_hash = hashlib.sha256(json.dumps(council, sort_keys=True).encode()).hexdigest()[:12]

    if SHADOW_MODE:
        au.log("shadow_block", by=approved_names, reason=f"shadow_mode_tier_{final_tier}",
               session_id=session_id, tier=final_tier)
        return (
            f"👁️ Shadow mode: council {approved_count}/{total} approve (Tier {final_tier})\n"
            f"   Auto-approve recorded but NOT executed.\n"
            f"   Run `/moa-approve --by {','.join(approved_names)} "
            f"--reason \"<reason>\"` to execute."
        )

    # --- Step 6: Auto-approve! ---
    try:
        st.approve_auto(
            approved_by=approved_names,
            reason=task_desc or f"Council {approved_count}/{total} approve",
            session_id=session_id,
            dissented=dissented_names or None,
            dissent_reason=dissent_reason,
            tier=final_tier,
            cool_down_seconds=COOLDOWN_SECS,
            council_config_hash=council_hash,
            ttl_seconds=st.DEFAULT_TTL_SECONDS,
        )
        au.log("auto_approve", by=approved_names,
               reason=task_desc or f"AUTO tier={final_tier}",
               session_id=session_id, trigger="auto_majority", tier=final_tier)

        result = (
            f"✅ MOA Gate: Auto-approved via council ({approved_count}/{total})\n"
            f"   Voices: {', '.join(approved_names)}\n"
            f"   Tier: {ti.format_tier(final_tier)}"
            f"{mode_warning}"
        )
        if dissented_names:
            result += f"   Dissent: {', '.join(dissented_names)} — creating issue...\n"
            _create_dissent_issue(dissented_names, council)
        if COOLDOWN_SECS > 0:
            result += (
                f"   ⏳ Cool-down: {COOLDOWN_SECS}s (auto-on expiry)\n"
                f"   Override: `/moa-approve --override --reason \"...\"`\n"
            )
        else:
            result += "\n   ⏏ Gate open — retry the blocked write operation now."
        result += f"   Rate limit: {remaining - 1}/{AUTO_RATE_LIMIT} remaining this hour"
        return result

    except Exception as exc:
        au.log("error", reason=f"auto_approve_failed: {exc}", session_id=session_id)
        return f"❌ Auto-approve failed: {exc}"


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------

_HELP_TEXT = """\
/moa-gate — MOA (Multi-Model Adviser) gate control

Subcommands:
  status                              Show current gate state
  approve --by <voices>               Manual gate approval
           --reason <text>             Reason for approval (required)
           --override                  Override cool-down period
  council-complete '<json>'            Submit council results for auto-approve
                                       JSON fields: votes (required), task_description,
                                       dissent_reason, changed_paths, diff_keywords,
                                       mode ("moa"|"cli"|"cloud", default=cloud)
  revoke                              Reset gate to pending
  emergency --reason <text>           🚨 EMERGENCY bypass — approve without council
  log [N]                             Show last N audit log entries (default 10)
  verify                              Verify audit log chain integrity
  help                                This help

Examples:
  /moa-approve --by architect,critic,pragmatist --reason "Fix prod bug #123"
  /moa-council-complete '{"votes":{"a":"approve","c":"approve"},"task_description":"fix auth"}'
  /moa-approve --override --reason "Hotfix — skip cooldown"
  /moa-emergency --reason "Production DNS outage — immediate hotfix"
  /moa-revoke
  /moa-log 20
"""


def _get_last_blocked_tool(session_id: str) -> str:
    """Find most recent blocked tool name for a session from audit log.

    Returns empty string if no block found.
    read_log() returns newest-first, so we iterate in order.
    Only returns the most recent block; if multiple tools were blocked
    in a row, only the last one is advertised.
    """
    try:
        entries = au.read_log(200)
        for entry in entries:
            if entry.get("action") == "block" and entry.get("session_id") == session_id:
                return entry.get("tool", "") or ""
    except Exception:
        pass
    return ""


def _handle_approve(raw_args: str) -> str:
    """Parse and execute approve command.

    Supports:
      /moa-approve --by voice1,voice2 --reason "..."
      /moa-approve --override --reason "..."
    """
    # Check for --override first (bypass cool-down)
    if "--override" in raw_args:
        return _handle_override(raw_args)

    # Standard approve
    by_match = re.search(r"--by\s+([\w,\\-_.]+)", raw_args)
    reason_match = re.search(r'--reason\s+"([^"]*)"|--reason\s+(\S+)', raw_args)

    if not by_match:
        return "❌ Usage: /moa-approve --by voice1,voice2 --reason \"...\"\n  Voices: comma-separated, e.g. architect,critic,pragmatist"

    voices_raw = by_match.group(1)
    voices = [v.strip() for v in voices_raw.split(",") if v.strip()]

    if not voices:
        return "❌ At least one voice required."

    reason = ""
    if reason_match:
        reason = reason_match.group(1) or reason_match.group(2) or ""

    if not reason:
        return "❌ --reason is required."

    # Get session_id
    session_id = os.environ.get("HERMES_SESSION_ID", "") or ""
    if not session_id:
        session_id = f"anon-{os.getpid():d}"

    try:
        st.approve(voices, reason, session_id)
        au.log("approve", by=voices, reason=reason, session_id=session_id)

        voices_str = ", ".join(voices)
        # Look up most recently blocked tool from audit log for retry hint
        last_tool = _get_last_blocked_tool(session_id)
        retry_hint = f"\n   ⏏ RETRY: {last_tool}" if last_tool else ""
        return (
            f"✅ MOA Gate APPROVED by {voices_str}\n"
            f"   Reason: {reason}\n"
            f"   Write tools are now allowed.{retry_hint}\n"
            f"   ⏏ Gate open — retry the blocked operation now."
        )
    except Exception as exc:
        au.log("error", reason=f"approve_failed: {exc}", session_id=session_id)
        return f"❌ Approval failed: {exc}"


def _handle_override(raw_args: str) -> str:
    """Override cool-down period."""
    reason_match = re.search(r'--reason\s+"([^"]*)"|--reason\s+(\S+)', raw_args)
    reason = ""
    if reason_match:
        reason = reason_match.group(1) or reason_match.group(2) or ""

    try:
        session_id = os.environ.get("HERMES_SESSION_ID", "") or f"anon-{os.getpid():d}"
        # Check if there's actually a cool-down to override
        before = st.read(session_id)
        had_cooldown = bool(before.get("cool_down_until"))
        state = st.override_cooldown(override_by="human", session_id=session_id)
        if not state.get("cool_down_until"):
            if had_cooldown:
                last_tool = _get_last_blocked_tool(session_id)
                retry_hint = f"\n   ⏏ RETRY: {last_tool}" if last_tool else ""
                au.log("override", reason=reason or "Cooldown overridden by human",
                       session_id=session_id)
                return (
                    f"✅ Cool-down overridden!\n"
                    f"   Write tools are now allowed immediately.{retry_hint}\n"
                )
            return "ℹ️  No active cool-down — nothing to override."
        return "❌ Cool-down override failed — state unchanged."
    except Exception as exc:
        return f"❌ Override failed: {exc}"


def _handle_emergency(raw_args: str) -> str:
    """Emergency bypass — approve immediately without council.

    Usage: /moa-emergency --reason "<emergency reason>"

    Bypasses cool-down, requires no voices, logs as 'emergency'.
    For production incidents where MOA council is too slow.
    """
    reason_match = re.search(r'--reason\s+"([^"]*)"|--reason\s+(\S+)', raw_args)
    if not reason_match:
        return (
            "❌ Usage: /moa-emergency --reason \"<reason>\"\n"
            "   Example: /moa-emergency --reason \"Production DNS outage — hotfix\""
        )
    reason = (reason_match.group(1) or reason_match.group(2) or "emergency").strip()
    if not reason or reason == "emergency":
        return (
            "❌ Usage: /moa-emergency --reason \"<meaningful reason>\"\n"
            "   Example: /moa-emergency --reason \"Production DNS outage — deploying hotfix\"\n"
            "   Empty reason is not allowed — audit requires a real explanation."
        )

    session_id = os.environ.get("HERMES_SESSION_ID", "") or f"anon-{os.getpid():d}"

    try:
        st.approve(
            approved_by=["emergency"],
            reason=reason,
            session_id=session_id,
        )
        au.log("approve", by=["emergency"], reason=f"EMERGENCY: {reason}",
               session_id=session_id, trigger="emergency")

        # Look up last blocked tool from audit log for retry hint
        last_tool = _get_last_blocked_tool(session_id)
        retry_hint = f"\n   ⏏ RETRY: {last_tool}" if last_tool else ""

        return (
            "🚨 MOA Gate: EMERGENCY BYPASS\n"
            f"   Reason: {reason}\n"
            f"   Write tools are now unblocked immediately.{retry_hint}\n"
            f"   ⏏ Gate open — retry the blocked operation now.\n"
            f"   ⚠️  Remember to revoke after emergency: `/moa-revoke`"
        )
    except Exception as exc:
        au.log("error", reason=f"emergency_failed: {exc}", session_id=session_id)
        return f"❌ Emergency bypass failed: {exc}"


def _handle_revoke(raw_args: str) -> str:
    """Revoke gate approval."""
    reason = raw_args.strip() or "Session complete"
    try:
        session_id = os.environ.get("HERMES_SESSION_ID", "") or f"anon-{os.getpid():d}"
        st.revoke(reason, session_id=session_id)
        au.log("revoke", reason=reason, session_id=session_id)
        return "🔄 MOA Gate REVOKED — reset to pending. Run `/moa-approve` when ready."
    except Exception as exc:
        return f"❌ Revoke failed: {exc}"


def _handle_status(raw_args: str) -> str:
    """Show current gate state."""
    try:
        session_id = os.environ.get("HERMES_SESSION_ID", "") or f"anon-{os.getpid():d}"
        data = st.read(session_id)
        return st.format_status(data)
    except Exception as exc:
        return f"❌ Status error: {exc}"


def _handle_log(raw_args: str) -> str:
    """Show audit log entries."""
    try:
        n = 10
        stripped = raw_args.strip()
        if stripped:
            try:
                n = int(stripped.split()[0])
            except ValueError:
                pass
        n = max(1, min(n, 200))
        entries = au.read_log(n)
        return f"📋 MOA Gate Audit Log (last {len(entries)}):\n{au.format_log(entries)}"
    except Exception as exc:
        return f"❌ Log error: {exc}"


def _handle_verify(raw_args: str) -> str:
    """Verify audit chain integrity."""
    try:
        violations = au.verify_chain()
        if not violations:
            return "✅ Audit log chain intact — no tampering detected."
        lines = ["⚠️ Audit chain violations found:"]
        for v in violations:
            lines.append(f"  Line {v.get('line', '?')}: {v.get('error', '?')}")
        return "\n".join(lines)
    except Exception as exc:
        return f"❌ Verification error: {exc}"


def _handle_slash(raw_args: str) -> Optional[str]:
    """Route slash commands."""
    argv = raw_args.strip().split()
    if not argv or argv[0] in {"help", "-h", "--help"}:
        return _HELP_TEXT

    sub = argv[0].lower()

    # Support both /moa-gate <sub> and /moa-<sub> form
    if sub == "status":
        return _handle_status(" ".join(argv[1:]))
    if sub in ("approve", "--approve"):
        return _handle_approve(" ".join(argv[1:]))
    if sub in ("council-complete", "council"):
        return _handle_council_complete(" ".join(argv[1:]))
    if sub in ("revoke", "--revoke"):
        return _handle_revoke(" ".join(argv[1:]))
    if sub in ("emergency", "bypass", "--emergency"):
        return _handle_emergency(" ".join(argv[1:]))
    if sub in ("log", "logs", "--log"):
        return _handle_log(" ".join(argv[1:]))
    if sub in ("verify", "--verify", "check"):
        return _handle_verify(" ".join(argv[1:]))

    return f"Unknown subcommand: {sub}\n\n{_HELP_TEXT}"


# ---------------------------------------------------------------------------
# Session End Hook (P2)
# ---------------------------------------------------------------------------

def _on_session_end(*, session_id: str = "", completed: bool = False,
                     interrupted: bool = False, model: str = "",
                     platform: str = "", **_: Any) -> None:
    """Auto-revoke state when session ends.

    P2 in council recommendation: auto-revoke on session end.
    This handles graceful session shutdown.
    Uninterruptible signals (kill -9, crash) require TTL-only recovery.
    """
    try:
        data = st.read(session_id)
        if data.get("status") == "approved":
            approved_session = data.get("session_id", "")
            if not session_id:
                au.log("skip_revoke", by=["system"],
                       reason="session_end_without_session_id",
                       session_id=session_id)
                logger.info("MOA Gate: skip auto-revoke — missing session_id")
                return
            if approved_session and approved_session != session_id:
                au.log("skip_revoke_session_mismatch", by=["system"],
                       reason=f"approved_session={approved_session}",
                       session_id=session_id)
                logger.info(
                    "MOA Gate: skip auto-revoke — ended session %s != approved session %s",
                    session_id,
                    approved_session,
                )
                return
            st.revoke(f"Session ended (completed={completed}, interrupted={interrupted})", session_id=session_id)
            au.log("revoke", by=["system"],
                   reason=f"session_end_completed={completed}_interrupted={interrupted}",
                   session_id=session_id)
            logger.info("MOA Gate: auto-revoked on session end (%s)", session_id)
    except Exception as exc:
        # Never crash session teardown
        logger.warning("MOA Gate: on_session_end error: %s", exc)


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

def register(ctx) -> None:
    """Register MOA Gate hooks.

    Called once when Hermes loads the plugin.
    Sets up pre_tool_call and on_session_end hooks.
    Cleans stale per-session state files on startup.
    """
    # Startup GC: clear stale per-session state files
    st.gc_stale_sessions()

    ctx.register_hook("pre_tool_call", _on_pre_tool_call)

    # P1: Startup sweep — auto-expire state if TTL passed
    # st.read(session_id) checks expires_at and returns pending if expired
    session_id = os.environ.get("HERMES_SESSION_ID", "") or f"anon-{os.getpid():d}"
    st.read(session_id)

    ctx.register_command(
        "moa-approve",
        handler=_handle_approve,
        description="Approve MOA gate for write tools (or --override for cooldown).",
    )
    ctx.register_command(
        "moa-council-complete",
        handler=_handle_council_complete,
        description="Submit MOA council results for auto-approval. Usage: /moa-council-complete '<json>'",
    )
    ctx.register_command(
        "moa-revoke",
        handler=_handle_revoke,
        description="Revoke MOA gate approval.",
    )
    ctx.register_command(
        "moa-status",
        handler=_handle_status,
        description="Show MOA gate state (including auto-approve info).",
    )
    ctx.register_command(
        "moa-log",
        handler=_handle_log,
        description="Show MOA gate audit log.",
    )
    ctx.register_command(
        "moa-verify",
        handler=_handle_verify,
        description="Verify audit log integrity.",
    )
    ctx.register_command(
        "moa-emergency",
        handler=_handle_emergency,
        description="🚨 Emergency bypass — approve immediately without council. Usage: /moa-emergency --reason \"...\"",
    )

    # P2: on_session_end — auto-revoke when session ends
    ctx.register_hook("on_session_end", _on_session_end)
