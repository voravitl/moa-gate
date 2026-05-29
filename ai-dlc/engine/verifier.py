"""Steering rule verifier — scan content against rules before write."""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional

from ..steering.registry import get_active_rules_for_path

logger = logging.getLogger(__name__)


def verify_content(content: str, file_path: str) -> dict:
    """Scan content against applicable steering rules.
    
    Args:
        content: The text content to scan
        file_path: Path of the file being written (for rule matching)
    
    Returns:
        {
            "critical": [violation, ...],
            "warning": [violation, ...],
            "passed": bool
        }
    """
    rules = get_active_rules_for_path(file_path)
    critical_violations = []
    warning_violations = []
    
    if not content:
        return {"critical": [], "warning": [], "passed": True}
    
    for cat, cat_rules in rules.items():
        for rule in cat_rules:
            rule_type = rule.get("type")
            severity = rule.get("severity", "warning")
            
            if rule_type == "deny_pattern":
                pattern = rule.get("pattern", "")
                if pattern:
                    try:
                        matched = re.search(pattern, content, re.MULTILINE)
                    except re.error:
                        logger.warning("bad regex rule %r: %s", rule.get("id", "?"), pattern[:80])
                        matched = None
                    if matched:
                        violation = {
                            "rule_id": rule["id"],
                            "category": cat,
                            "description": rule.get("description", ""),
                            "suggestion": rule.get("suggestion", ""),
                            "severity": severity,
                        }
                        if severity == "critical":
                            critical_violations.append(violation)
                        else:
                            warning_violations.append(violation)

            elif rule_type == "require_pattern":
                pattern = rule.get("pattern", "")
                if pattern:
                    try:
                        matched = re.search(pattern, content, re.MULTILINE)
                    except re.error:
                        logger.warning("bad regex rule %r: %s", rule.get("id", "?"), pattern[:80])
                        matched = False
                    if not matched:
                        violation = {
                            "rule_id": rule["id"],
                            "category": cat,
                            "description": rule.get("description", ""),
                            "suggestion": rule.get("suggestion", ""),
                            "severity": severity,
                        }
                        if severity == "critical":
                            critical_violations.append(violation)
                        else:
                            warning_violations.append(violation)

    return {
        "critical": critical_violations,
        "warning": warning_violations,
        "passed": len(critical_violations) == 0,
    }


def verify_code_block(content: str, file_path: str) -> dict:
    """Shortcut — verify that a code block passes steering rules.
    
    Returns violations summary as formatted string.
    """
    result = verify_content(content, file_path)
    
    if result["passed"]:
        return {"ok": True, "message": "\u2705 Steering check passed"}
    
    parts = ["\u26a0\ufe0f Steering violations found:"]
    for v in result.get("critical", []):
        parts.append(f"  \u274c [{v['rule_id']}] {v['description']}")
        parts.append(f"     \u2192 {v['suggestion']}")
    for v in result.get("warning", []):
        parts.append(f"  \u26a0\ufe0f [{v['rule_id']}] {v['description']}")
        parts.append(f"     \u2192 {v['suggestion']}")
    
    return {"ok": False, "message": "\n".join(parts)}
