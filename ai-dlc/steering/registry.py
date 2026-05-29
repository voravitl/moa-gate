"""Steering rules registry — load YAML rules from ~/wiki/steering/."""

from __future__ import annotations

import logging
import os
import re
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

STEERING_DIR = Path.home() / "wiki" / "steering"
DEFAULT_RULES_DIR = Path(__file__).parent / "rules"


def load_rules(categories: List[str] | None = None) -> dict:
    """Load steering rules from ~/wiki/steering/ and bundled defaults.
    
    Args:
        categories: Optional list of categories to load (security, architecture, compliance).
                    Loads all if None.
    
    Returns:
        {"security": [rule1, rule2, ...], "architecture": [...], ...}
    """
    rules = {}
    if categories is None:
        categories = ["security", "architecture", "compliance"]
    
    for cat in categories:
        cat_rules = []
        
        # Try user wiki steering first
        user_file = STEERING_DIR / f"{cat}.yaml"
        if user_file.exists():
            try:
                with open(user_file) as f:
                    data = yaml.safe_load(f)
                if data and "rules" in data:
                    for r in data["rules"]:
                        r["_source"] = str(user_file)
                        cat_rules.append(r)
            except Exception as e:
                logger.warning(f"Failed to load {user_file}: {e}")
        
        # Fallback to bundled defaults
        if not cat_rules:
            bundled = DEFAULT_RULES_DIR / f"{cat}.yaml"
            if bundled.exists():
                try:
                    with open(bundled) as f:
                        data = yaml.safe_load(f)
                    if data and "rules" in data:
                        for r in data["rules"]:
                            r["_source"] = str(bundled)
                            cat_rules.append(r)
                except Exception as e:
                    logger.warning(f"Failed to load {bundled}: {e}")
        
        rules[cat] = cat_rules
    
    return rules


def get_active_rules_for_path(path: str) -> dict:
    """Get rules applicable to a specific file path.
    
    Filters rules by their path patterns.
    """
    all_rules = load_rules()
    active = {}
    
    for cat, cat_rules in all_rules.items():
        applicable = []
        for rule in cat_rules:
            patterns = rule.get("path_patterns", [".*"])
            if any(re.search(p, path) for p in patterns):
                applicable.append(rule)
        if applicable:
            active[cat] = applicable
    
    return active


def format_rules_summary(rules: dict) -> str:
    """Format rules as a readable summary for AI context injection."""
    parts = []
    for cat, cat_rules in rules.items():
        parts.append(f"[{cat.upper()}]")
        for r in cat_rules:
            parts.append(f"  {r['id']}: {r['description']} ({r['severity']})")
    return "\n".join(parts)
