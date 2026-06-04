"""AI-DLC Compass — Steering verification, phase engine, and policy enforcement.

Intercepts pre_tool_call to:
1. Verify content against steering rules (security, architecture, compliance)
2. Check phase state (Inception/Construction/Operation)
3. Block steering violations with education messages
4. Record critical violations into the MOA-Gate audit trail for review

Slash commands (via /ai-dlc):
  steer ls       — List active steering rules
  phase          — Show current AI-DLC phase
  phase promote  — Promote to next phase
  verify <file>  — Verify a file against steering rules
  guide          — Show guidance for current phase
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import re
import tempfile
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .engine import phase as ph
from .engine import verifier as vr
from .steering import registry as sr

# Slash-command definitions
COMMANDS = {
    "steer ls": "List active steering rules",
    "phase": "Show current AI-DLC phase",
    "phase promote": "Promote to next phase",
    "verify <file>": "Verify a file against steering rules",
    "guide": "Show guidance for current phase",
}
_HELP_TEXT = "\n".join(f"  /ai-dlc {cmd}  — {desc}" for cmd, desc in COMMANDS.items())

logger = logging.getLogger(__name__)

BLOCKED_TOOLS = frozenset({
    "patch", "write_file", "write", "git_commit",
    "gh_pr_create", "skill_manage", "terminal", "process",
})

CODE_EXTENSIONS = frozenset({
    ".py", ".rs", ".ts", ".js", ".tsx", ".jsx", ".go", ".java",
    ".c", ".cpp", ".h", ".hpp", ".swift", ".kt", ".rb", ".php",
    ".sh", ".bash", ".yaml", ".yml", ".json", ".toml",
})


def _home() -> Path:
    """Resolve HOME at call time so tests/session changes do not leave stale paths."""
    return Path(os.path.expanduser("~"))


def _state_dir() -> Path:
    return _home() / ".hermes" / "ai-dlc"


def _state_file() -> Path:
    return _state_dir() / "state.json"


def _steering_loaded_flag() -> Path:
    return _state_dir() / "steering_loaded.flag"


def _moa_gate_dir() -> Path:
    return _home() / ".hermes" / "moa-gate"


def _moa_gate_state_file() -> Path:
    return _moa_gate_dir() / "state.json"


def _moa_gate_audit_file() -> Path:
    return _moa_gate_dir() / "audit.log"


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _write_json(path: Path, data: dict) -> None:
    os.makedirs(path.parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, default=str)
            f.flush()
            os.fsync(fd)
        os.replace(tmp, str(path))
    except Exception:
        os.unlink(tmp)
        raise


def _steering_loaded() -> bool:
    return _steering_loaded_flag().exists()


def _mark_steering_loaded() -> None:
    os.makedirs(_state_dir(), exist_ok=True)
    _steering_loaded_flag().write_text(datetime.now(timezone.utc).isoformat())


def _moa_gate_state() -> dict:
    return _read_json(_moa_gate_state_file())


def _last_moa_audit_hash_from_locked_file(f) -> str:
    """Read the last MOA audit hash while caller holds an exclusive flock."""
    try:
        f.seek(0, os.SEEK_END)
        if f.tell() == 0:
            return "0" * 64
        f.seek(0)
        last_line = ""
        for line in f:
            if line.strip():
                last_line = line.strip()
        if last_line:
            last_hash = json.loads(last_line).get("hash", "")
            if isinstance(last_hash, str) and len(last_hash) == 64:
                return last_hash
    except Exception as exc:
        logger.debug("ai-dlc: could not read MOA audit hash: %s", exc)
    return "0" * 64


def _record_moa_escalation(tool_name: str, path: str, violations: list[dict]) -> bool:
    """Record a critical AI-DLC block into the MOA-Gate audit chain.

    This is an escalation record, not an approval. It creates a tamper-evident
    MOA audit entry so a later MOA review can inspect what was blocked.
    """
    audit_file = _moa_gate_audit_file()
    try:
        audit_file.parent.mkdir(parents=True, exist_ok=True)
        rule_ids = [str(v.get("rule_id", "unknown")) for v in violations]
        entry = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "action": "shadow_block",
            "tool": tool_name or "",
            "by": ["ai-dlc"],
            "reason": f"AI-DLC critical steering violation(s): {', '.join(rule_ids)} at {path}",
            "session_id": os.environ.get("HERMES_SESSION_ID", ""),
            "trigger": "ai_dlc",
            "tier": 2,
            "prev_hash": "0" * 64,
        }
        with open(str(audit_file), "a+") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            entry["prev_hash"] = _last_moa_audit_hash_from_locked_file(f)
            entry["hash"] = hashlib.sha256(
                json.dumps(entry, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest()
            f.seek(0, os.SEEK_END)
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            f.flush()
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        audit_file.chmod(0o600)
        return True
    except Exception as exc:
        logger.warning("ai-dlc: failed to record MOA escalation: %s", exc)
        return False


def register(ctx=None) -> None:
    """Register AI-DLC slash commands when Hermes provides a plugin context."""
    _mark_steering_loaded()
    if ctx is not None and hasattr(ctx, "register_command"):
        ctx.register_command(
            "ai-dlc",
            handler=_handle_ai_dlc,
            description="AI-DLC commands: steer ls, phase, phase promote, verify <file>, guide",
        )
        logger.info("ai-dlc-compass: registered with slash commands")
    else:
        logger.info("ai-dlc-compass: registered")


def pre_tool_call(tool_name: str, args: dict) -> Optional[dict]:
    """Block write/destructive tools when phase or steering rules are violated."""
    if tool_name not in BLOCKED_TOOLS:
        return None
    logger.info("ai-dlc-compass: checking %s", tool_name)

    path_arg = args.get("path", args.get("file", ""))
    content_arg = args.get("content", args.get("text", ""))
    patch_payloads = _extract_patch_file_payloads(str(args.get("patch", ""))) if tool_name == "patch" and args.get("patch") else []

    if not _steering_loaded():
        spath = str(path_arg)
        if "wiki" not in spath and ".hermes" not in spath:
            return {"block": True, "message": "📡 AI-DLC: Steering rules not loaded yet.\nPlease load steering first."}

    if not content_arg:
        if tool_name == "patch":
            content_arg = "\n".join(
                part for part in (args.get("new_string", ""), args.get("patch", "")) if part
            )
        elif tool_name == "terminal":
            content_arg = args.get("command", "")
        elif tool_name == "process":
            content_arg = args.get("data", "")

    current_phase = ph.get_phase()
    patch_paths = [patch_path for patch_path, _ in patch_payloads]
    if current_phase == "INCEPTION" and (
        _is_code_file(str(path_arg)) or any(_is_code_file(patch_path) for patch_path in patch_paths)
    ):
        return {"block": True, "message": "🚫 AI-DLC PHASE BLOCK: Still in INCEPTION.\nUse /ai-dlc phase promote"}

    if not path_arg and content_arg:
        path_arg = f"/tmp/{tool_name}-payload.sh"

    for patch_path, patch_payload in patch_payloads:
        violations = vr.verify_content(patch_payload, patch_path)
        if violations["critical"] or violations["warning"]:
            return _handle_violations(tool_name, violations, patch_path)

    if content_arg:
        violations = vr.verify_content(content_arg, str(path_arg))
        if violations["critical"] or violations["warning"]:
            return _handle_violations(tool_name, violations, str(path_arg))
    return None


def _is_code_file(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in CODE_EXTENSIONS


def _extract_patch_file_payloads(patch_text: str) -> list[tuple[str, str]]:
    """Extract per-file payloads from V4A patches using real target paths."""
    payloads: list[tuple[str, list[str]]] = []
    current_path = ""
    current_lines: list[str] = []

    for line in patch_text.splitlines():
        file_match = re.match(r"^\*\*\*\s+(?:Update|Add) File:\s+(.+)$", line)
        if file_match:
            if current_path:
                payloads.append((current_path, current_lines))
            current_path = file_match.group(1).strip()
            current_lines = []
            continue

        move_match = re.match(r"^\*\*\*\s+Move to:\s+(.+)$", line)
        if move_match and current_path:
            current_path = move_match.group(1).strip()
            continue

        if current_path:
            current_lines.append(line)

    if current_path:
        payloads.append((current_path, current_lines))

    return [(path, "\n".join(lines)) for path, lines in payloads if path and lines]


def _handle_violations(tool_name: str, violations: dict, path: str) -> dict:
    critical = violations.get("critical", [])
    warning = violations.get("warning", [])
    msg_parts = ["🛡️ AI-DLC: Steering violation detected!\n"]

    for v in critical:
        msg_parts.append(f"  ❌ CRITICAL: [{v['rule_id']}] {v['description']}")
        msg_parts.append(f"    → {v['suggestion']}")
    for v in warning:
        msg_parts.append(f"  ⚠️ WARNING: [{v['rule_id']}] {v['description']}")
        msg_parts.append(f"    → {v['suggestion']}")

    escalated = False
    if critical:
        escalated = _record_moa_escalation(tool_name, path, critical)

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": tool_name,
        "path": str(path),
        "violations": critical + warning,
        "resolved": False,
        "moa_escalated": escalated,
    }
    state = _read_json(_state_file())
    state.setdefault("violations", []).append(record)
    _write_json(_state_file(), state)

    if critical:
        if escalated:
            msg_parts.append("\n🔴 Recorded MOA-Gate Tier 2 escalation in audit log")
        else:
            msg_parts.append("\n⚠️ MOA-Gate escalation record failed; AI-DLC block remains active")
    return {"block": True, "message": "\n".join(msg_parts)}


def _handle_ai_dlc(raw_args: str) -> str:
    parts = raw_args.strip().split()
    if not parts:
        return _ai_dlc_help()
    cmd = parts[0]
    if cmd == "steer":
        if len(parts) > 1 and parts[1] == "ls":
            return _cmd_steer_ls()
        return "Usage: /ai-dlc steer ls"
    if cmd == "phase":
        if len(parts) > 1 and parts[1] == "promote":
            return _cmd_phase_promote()
        return _cmd_phase()
    if cmd == "verify":
        filepath = " ".join(parts[1:]) if len(parts) > 1 else ""
        return _cmd_verify(filepath)
    if cmd == "guide":
        return _cmd_guide()
    return _ai_dlc_help()


def _ai_dlc_help() -> str:
    status = ph.get_phase() or "Not set"
    loaded = "✅ yes" if _steering_loaded() else "❌ no"
    return f"""🤖 AI-DLC Compass — Commands:
{_HELP_TEXT}

Current phase: {status}
Steering loaded: {loaded}
"""


def _cmd_steer_ls() -> str:
    try:
        rules = sr.load_rules()
        if not rules or all(len(v) == 0 for v in rules.values()):
            return "📭 No steering rules found."
        total = sum(len(v) for v in rules.values())
        parts = [f"📋 Steering Rules ({total} total):\n"]
        for cat, cat_rules in rules.items():
            parts.append(f"\n[{cat.upper()}]")
            for r in cat_rules:
                parts.append(f"  {r['id']}: {r.get('description')} [{r.get('severity', 'warning')}]")
                if r.get('suggestion'):
                    parts.append(f"    → {r['suggestion']}")
        return "\n".join(parts)
    except Exception as e:
        return f"❌ Error: {e}"


def _cmd_phase() -> str:
    status = ph.get_status()
    phase = status.get("phase") or "Not set"
    valid = status.get("valid_phases", [])
    parts = [f"🎯 AI-DLC Phase: {phase}\n"]
    parts.append(f"Valid: {' → '.join(valid)}")
    if phase in valid:
        remaining = valid[valid.index(phase)+1:]
        if remaining:
            parts.append(f"Next: {' → '.join(remaining)}")
        else:
            parts.append("✅ Final phase")
    return "\n".join(parts)


def _cmd_phase_promote() -> str:
    result = ph.promote_phase()
    if result.get("ok"):
        return f"✅ Phase: {result.get('old')} → {result.get('phase')}"
    return f"❌ {result.get('error')}"


def _cmd_verify(filepath: str) -> str:
    if not filepath:
        return "Usage: /ai-dlc verify <filepath>"
    expanded = os.path.expanduser(filepath)
    if not os.path.exists(expanded):
        return f"❌ File not found: {filepath}"
    try:
        with open(expanded) as f:
            content = f.read()
        result = vr.verify_content(content, expanded)
        if result["passed"]:
            return f"✅ Steering PASSED for {filepath}"
        parts = [f"⚠️ Violations in {filepath}:\n"]
        for v in result.get("critical", []):
            parts.append(f"  ❌ [{v['rule_id']}] {v['description']} → {v['suggestion']}")
        for v in result.get("warning", []):
            parts.append(f"  ⚠️ [{v['rule_id']}] {v['description']} → {v['suggestion']}")
        return "\n".join(parts)
    except Exception as e:
        return f"❌ {e}"


def _cmd_guide() -> str:
    phase = ph.get_phase()
    guides = {
        "INCEPTION": ("📘 INCEPTION\n\nFocus: specs, requirements, design docs.\nCode is BLOCKED.\nReady? → /ai-dlc phase promote"),
        "CONSTRUCTION": ("🛠️ CONSTRUCTION\n\nFocus: writing code with steering rules.\nCheck: /ai-dlc steer ls"),
        "OPERATION": ("⚙️ OPERATION\n\nFocus: config, hotfixes, monitoring.\nMajor changes → CI/CD"),
    }
    if phase in guides:
        return guides[phase]
    return "🤖 Start with: /ai-dlc phase, /ai-dlc steer ls, /ai-dlc phase promote"
