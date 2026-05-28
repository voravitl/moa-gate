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
TIER_2_PATTERNS = re.compile(
    r"(?i)"
    # Security & auth
    r"(?:"
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
    # Data loss
    r"delete|remove|purge|wipe|clear|truncate|"
    r"backup|restore|recovery|disaster.?recovery|"
    # Compliance
    r"audit|compliance|gdp[rr]|pcidss|sox|hipaa|pci|"
    # Enterprise tools
    r"byok|kms|hsm|key.?management|"
    r"enterprise|tenant|multi.?tenant"
    r")"
)


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
    # Check task description
    if task_description and TIER_2_PATTERNS.search(task_description):
        return TIER_2

    # Check paths
    if changed_paths:
        for path in changed_paths:
            if TIER_2_PATTERNS.search(path):
                return TIER_2

    # Check diff keywords
    if diff_keywords:
        for kw in diff_keywords:
            if TIER_2_PATTERNS.search(kw):
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
