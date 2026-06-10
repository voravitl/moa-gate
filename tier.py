"""MOA Gate — Tier classification for auto-approve safety levels.

Tier 1 (Auto): Non-security changes — code refactor, tests, docs, config
Tier 2 (Manual): Security/auth/billing/data-loss changes — requires human

Conservative merge: if ANY path/reason matches Tier 2 → Tier 2
"""

from __future__ import annotations

import re
from typing import Dict, Any, List

# ---------------------------------------------------------------------------
# Tier definitions
# ---------------------------------------------------------------------------

TIER_1 = 1  # Auto-approve (if council ≥80%)
TIER_2 = 2  # Manual approve only

# Paths / keywords that ALWAYS trigger Tier 2
#
# FIX (moa-gate issue #371 + MOA Adviser HIGH #4): the original regex lacked
# word boundaries around high-FP terms. "remove unused imports", "clear console
# output", "delete temp test fixture", and "next_token" / "tokenizer" all
# matched `remove|clear|delete|token` and forced Tier 2 manual approval.
#
# Strategy: TWO separate regexes, picked per input type:
#   * `TIER_2_PATH_PATTERNS` (no word boundaries): used for changed_paths.
#     Paths have natural delimiters (`/`, `.`, `-`) and the conservative match
#     is acceptable. False positives rare; false negatives dangerous.
#   * `TIER_2_FREETEXT_PATTERNS` (with word boundaries): used for task
#     descriptions and diff keywords. Free text contains compound words where
#     `remove`/`clear`/`delete`/`token` are common identifiers, so we use
#     strict boundaries to prevent FPs.
#   * High-stakes terms (auth, password, secret, credential, schema, etc.):
#     kept in BOTH patterns — false negatives are worse than false positives.
#
# Tests: tests/test_tier_wordboundaries.py
TIER_2_PATH_PATTERNS = re.compile(
    r"(?i)"
    r"(?:"
    # Security & auth
    r"auth|authenticate|authorize|rbac|permission|credential|"
    r"password|secret|token|api.?key|encrypt|decrypt|cipher|"
    r"certificate|ssl|tls|oauth|jwt|session|login|logout|"
    # Database schema
    r"migration|schema|ddl|alter\s+table|drop\s+|truncate|"
    r"create\s+table|add\s+column|remove\s+column|"
    # Billing / finance
    r"billing|payment|invoice|pricing|subscription|credit|"
    r"refund|charge|cost|wallet|balance|"
    # Production infra
    r"deploy|release|production|rollback|rollout|"
    r"kubernetes|k8s|docker|dockerfile|terraform|helm|"
    # Data loss (paths often have these as directory names)
    r"delete|remove|purge|wipe|clear|truncate|"
    r"backup|restore|recovery|disaster.?recovery|"
    # Compliance
    r"audit|compliance|gdp[rr]|pcidss|sox|hipaa|pci|"
    # Enterprise tools
    r"byok|kms|hsm|key.?management|"
    r"enterprise|tenant|multi.?tenant|"
    # Infra tools (conservative: these tool names in file paths signal infra scripts)
    r"mkfs|fdisk|iptables"
    r")"
)


# Free-text patterns: word boundaries around high-FP compound-word terms.
# Notice: `token` is now \\btoken\\b, `delete`/`remove`/`clear`/`purge`/`wipe`
# have word boundaries to prevent matches in `next_token`, `remove_unused`,
# `clear_cache`, `delete_temp_fixture` etc.
TIER_2_FREETEXT_PATTERNS = re.compile(
    r"(?i)"
    r"(?:"
    # Security & auth
    r"auth|authenticate|authorize|rbac|permission|credential|"
    r"password|secret|api.?key|encrypt|decrypt|cipher|"
    r"certificate|ssl|tls|oauth|jwt|login|logout|"
    r"\bsession\b|"  # "session" as standalone (not "sessionStorage" in JS)
    r"\btoken\b|"     # bounded: no match in "next_token", "tokenizer", "tokenize"
    # Database schema
    r"migration|schema|ddl|alter\s+table|drop\s+|truncate|"
    r"create\s+table|add\s+column|remove\s+column|"
    # Billing / finance
    r"billing|payment|invoice|pricing|subscription|credit|"
    r"refund|charge|cost|wallet|balance|"
    # Production infra
    r"deploy|release|production|rollback|rollout|"
    r"kubernetes|k8s|docker|dockerfile|terraform|helm|"
    # Data loss (bounded to prevent FPs)
    r"\bdelete\b|\bremove\b|\bclear\b|\bpurge\b|\bwipe\b|"
    r"backup|restore|recovery|disaster.?recovery|"
    # Compliance
    r"audit|compliance|gdp[rr]|pcidss|sox|hipaa|pci|"
    # Enterprise tools
    r"byok|kms|hsm|key.?management|"
    r"enterprise|tenant|multi.?tenant|"
    # Destructive shell / FS operations (word-boundary safe)
    r"\brm\s+-[rRfF]*[rR][rRfF]*|"          # rm -r/-rf/-fr/-fR etc. (recursive delete)
    r"\bsudo\s+rm\b|"                         # sudo rm (privileged removal, any flags)
    r"shutil\.rmtree|"                         # Python: shutil.rmtree(path)
    r"os\.remove\(|"                           # Python: os.remove(path)
    r"os\.unlink\(|"                           # Python: os.unlink(path)
    r"\bgit\s+push\s+--force\b|"             # git push --force (including --force-with-lease)
    r"\bgit\s+push\s+-f\b|"                  # git push -f shorthand
    r"\bforce[-\s]push\b|"                    # force-push / force push
    r"\bchmod\s+(?:[0-7]{2}[2367]|[0-7]{3}[2367])\b|"  # chmod world-writable octal
    r"\bchown\s+root\b|"                      # chown root (ownership change to root)
    r"\bdd\s+if=|"                            # dd if=<src> (raw disk copy / wipe)
    r"\bmkfs\b|"                              # mkfs (make filesystem, destructive)
    r"\bfdisk\b|"                             # fdisk (disk partition editor)
    r"\biptables\s+-F\b|"                     # iptables -F (flush firewall rules)
    r"\bsystemctl\s+(?:stop|disable)\b"       # systemctl stop/disable service
    r")"
)


# Backward-compat alias — keep the old name pointing to the path regex
# so any external code that imports TIER_2_PATTERNS still works.
TIER_2_PATTERNS = TIER_2_PATH_PATTERNS


def classify_by_keywords(
    task_description: str = "",
    changed_paths: List[str] | None = None,
    diff_keywords: List[str] | None = None,
) -> int:
    """Classify change tier by keywords in description, paths, and diff.

    Conservative: any Tier 2 match → return Tier 2 immediately.

    Args:
        task_description: Natural language task description (e.g. from council input)
        changed_paths: List of file paths affected (e.g. from git diff --name-only)
        diff_keywords: Key terms extracted from diff

    Returns:
        TIER_1 or TIER_2
    """
    # Check task description (use free-text regex with word boundaries)
    if task_description and TIER_2_FREETEXT_PATTERNS.search(task_description):
        return TIER_2

    # Check paths (use path regex without word boundaries — paths have
    # natural delimiters and conservative matching is safer here)
    if changed_paths:
        for path in changed_paths:
            if TIER_2_PATH_PATTERNS.search(path):
                return TIER_2

    # Check diff keywords (treat as free-text — word boundaries)
    if diff_keywords:
        for kw in diff_keywords:
            if TIER_2_FREETEXT_PATTERNS.search(kw):
                return TIER_2

    return TIER_1


def classify_by_votes(
    voice_tiers: Dict[str, int] | None = None,
) -> int:
    """Conservative tier merge from voice votes.

    Each voice votes Tier 1 or Tier 2.
    If ANY voice votes Tier 2 → result is Tier 2 (conservative).

    Args:
        voice_tiers: {voice_name: tier} e.g. {"architect": 1, "critic": 2}

    Returns:
        TIER_1 only if ALL voices voted TIER_1, else TIER_2
    """
    if not voice_tiers:
        return TIER_1

    if any(t == TIER_2 for t in voice_tiers.values()):
        return TIER_2

    return TIER_1


def format_tier(tier: int) -> str:
    """Human-readable tier label."""
    if tier == TIER_1:
        return "Tier 1 (Auto)"
    elif tier == TIER_2:
        return "Tier 2 (Manual)"
    return f"Tier {tier} (Unknown)"
