"""Tests for tier.py word boundary fix (issue #371).

Covers false positives that previously forced manual approval for
benign tasks. Each test documents the exact false-positive phrase and
the expected tier after the fix.

Design note: MOA Adviser recommended word boundaries for free-text matching
because compound identifiers like `next_token`, `tokenizer`, `tokenize`
and phrases like `clear the cache` are common in code. However, the
*verb* `remove`/`delete`/`clear` used as an instruction word (e.g.
"remove unused imports", "delete temp file") IS still a Tier 2 signal —
the conservative design treats all such verbs as data-loss intent. The
real FPs are SUBSTRING matches in compound identifiers, not verb
instructions.
"""

import sys
from pathlib import Path

_HERE = Path(__file__).parent
_PLUGIN_DIR = _HERE.parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

import tier


# ---------------------------------------------------------------------------
# Free-text task_description: substring FPs in compound identifiers
# These must now pass as Tier 1 because the word-boundary fix prevents
# `remove`/`delete`/`clear`/`token` from matching inside compound words.
# ---------------------------------------------------------------------------


def test_rename_next_token_tier1():
    """Renaming the `next_token` variable must not be flagged as Tier 2.

    Without word boundaries, `token` matches inside `next_token`.
    """
    assert tier.classify_by_keywords("rename next_token variable to page_token") == tier.TIER_1


def test_tokenizer_call_tier1():
    """Using a tokenizer must not be flagged as Tier 2.

    `tokenizer` is a compound word — `token` was a substring FP.
    """
    assert tier.classify_by_keywords("use GPT tokenizer for input preprocessing") == tier.TIER_1


def test_tokenize_string_tier1():
    """`tokenize` is a verb, but it's a compound word — not a credential."""
    assert tier.classify_by_keywords("tokenize user input before logging") == tier.TIER_1


def test_sessionstorage_property_tier1():
    """`sessionStorage` (camelCase) must not be flagged as Tier 2.

    `session` was a substring FP in JS-style identifiers.
    """
    assert tier.classify_by_keywords("read from window.sessionStorage property") == tier.TIER_1


def test_remove_unused_imports_path_tier1():
    """Path matching uses path regex (no word boundaries) — keep behavior.

    Path `src/remove_unused.py` matches path regex's `remove` and
    stays Tier 2. This is conservative-by-design.
    """
    # Note: this is path matching, not free-text
    assert tier.classify_by_keywords("", changed_paths=["src/remove_unused.py"]) == tier.TIER_2


# ---------------------------------------------------------------------------
# Free-text task_description: real Tier 2 patterns (verbs as instructions)
# These must still flag — the verb is an explicit destructive instruction.
# ---------------------------------------------------------------------------


def test_delete_users_table_tier2():
    """'delete users table' must still be flagged as Tier 2."""
    assert tier.classify_by_keywords("delete users table from production") == tier.TIER_2


def test_remove_credentials_tier2():
    """'remove credentials from config' must still be flagged as Tier 2."""
    assert tier.classify_by_keywords("remove credentials from config file") == tier.TIER_2


def test_clear_session_storage_tier2():
    """'clear session storage' must still be flagged (session = auth context)."""
    assert tier.classify_by_keywords("clear session storage for logout") == tier.TIER_2


def test_token_api_key_tier2():
    """'api_token' must still be flagged (token adjacent to api_key)."""
    assert tier.classify_by_keywords("rotate api_token for production") == tier.TIER_2


def test_purge_data_tier2():
    """'purge data' must still be flagged (data loss)."""
    assert tier.classify_by_keywords("purge data older than 90 days") == tier.TIER_2


# ---------------------------------------------------------------------------
# Path matching: stricter, no false positives expected
# ---------------------------------------------------------------------------


def test_path_remove_unused_file_tier2():
    """Path 'src/remove_unused.py' is Tier 2 by conservative design.

    Path matches `remove` (no word boundary). False negative is worse
    than false positive here — operators can override the gate.
    """
    assert tier.classify_by_keywords("", changed_paths=["src/remove_unused.py"]) == tier.TIER_2


def test_path_delete_fixture_tier2():
    """Test fixture deletion path 'tests/fixtures/delete_old.json' is Tier 2.

    Path contains 'delete' substring — matches path regex.
    """
    assert tier.classify_by_keywords("", changed_paths=["tests/fixtures/delete_old.json"]) == tier.TIER_2


def test_path_unrelated_old_data_tier1():
    """A path with no Tier 2 keywords stays Tier 1 (e.g. just 'old' not 'delete')."""
    assert tier.classify_by_keywords("", changed_paths=["tests/fixtures/old_data.json"]) == tier.TIER_1


def test_path_auth_middleware_tier2():
    """Path containing 'auth' must still flag as Tier 2."""
    assert tier.classify_by_keywords("", changed_paths=["src/auth/middleware.py"]) == tier.TIER_2


def test_path_migration_tier2():
    """Migration paths must still flag."""
    assert tier.classify_by_keywords("", changed_paths=["db/migrations/001_init.sql"]) == tier.TIER_2


# ---------------------------------------------------------------------------
# diff_keywords (similar to free-text)
# ---------------------------------------------------------------------------


def test_diff_kw_next_token_tier1():
    """Diff keyword 'next_token' is a substring FP — Tier 1."""
    assert tier.classify_by_keywords("", diff_keywords=["next_token", "page_size"]) == tier.TIER_1


def test_diff_kw_password_tier2():
    """Diff keyword 'password' must still flag."""
    assert tier.classify_by_keywords("", diff_keywords=["password", "hash"]) == tier.TIER_2
