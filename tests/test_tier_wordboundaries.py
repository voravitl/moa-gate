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


# ---------------------------------------------------------------------------
# Destructive shell / FS operations: new Tier-2 patterns (positives)
# Each tests that the new patterns classify as TIER_2.
# ---------------------------------------------------------------------------


def test_rm_rf_tier2():
    """'rm -rf /data' must be flagged as Tier 2 (recursive forced delete)."""
    assert tier.classify_by_keywords("rm -rf /data") == tier.TIER_2


def test_rm_fr_tier2():
    """'rm -fr' flag order variant must still be flagged."""
    assert tier.classify_by_keywords("rm -fr /tmp/old") == tier.TIER_2


def test_rm_r_only_tier2():
    """`rm -r` (recursive, no force flag) must be flagged."""
    assert tier.classify_by_keywords("rm -r /var/logs") == tier.TIER_2


def test_rm_fR_variant_tier2():
    """'rm -fR' mixed-case flag must be flagged."""
    assert tier.classify_by_keywords("cleanup with rm -fR /mnt/data") == tier.TIER_2


def test_sudo_rm_tier2():
    """'sudo rm' (privileged removal, any flags) must be flagged."""
    assert tier.classify_by_keywords("sudo rm /etc/critical_config") == tier.TIER_2


def test_sudo_rm_rf_tier2():
    """'sudo rm -rf' must be flagged (both sudo rm and rm -rf match)."""
    assert tier.classify_by_keywords("sudo rm -rf /var/data") == tier.TIER_2


def test_shutil_rmtree_tier2():
    """Python shutil.rmtree call must be flagged (recursive directory removal)."""
    assert tier.classify_by_keywords("call shutil.rmtree(output_dir) before rebuild") == tier.TIER_2


def test_os_remove_tier2():
    """Python os.remove( must be flagged."""
    assert tier.classify_by_keywords("use os.remove(path) to delete the lockfile") == tier.TIER_2


def test_os_unlink_tier2():
    """Python os.unlink( must be flagged."""
    assert tier.classify_by_keywords("os.unlink(stale_pid_file) on startup") == tier.TIER_2


def test_git_push_force_tier2():
    """'git push --force' must be flagged (history rewrite)."""
    assert tier.classify_by_keywords("git push --force origin main") == tier.TIER_2


def test_git_push_force_with_lease_tier2():
    """'git push --force-with-lease' must be flagged (still a force push)."""
    assert tier.classify_by_keywords("git push --force-with-lease origin feature") == tier.TIER_2


def test_git_push_f_tier2():
    """'git push -f' shorthand must be flagged."""
    assert tier.classify_by_keywords("git push -f origin hotfix") == tier.TIER_2


def test_force_push_hyphen_tier2():
    """'force-push' (hyphenated) must be flagged."""
    assert tier.classify_by_keywords("force-push changes to shared branch") == tier.TIER_2


def test_force_push_space_tier2():
    """'force push' (with space) must be flagged."""
    assert tier.classify_by_keywords("force push to release branch") == tier.TIER_2


def test_chmod_777_tier2():
    """'chmod 777' (world-writable) must be flagged."""
    assert tier.classify_by_keywords("chmod 777 /etc/passwd") == tier.TIER_2


def test_chmod_0777_tier2():
    """'chmod 0777' (4-digit world-writable octal) must be flagged."""
    assert tier.classify_by_keywords("chmod 0777 /tmp/script.sh") == tier.TIER_2


def test_chmod_666_tier2():
    """'chmod 666' (world-writable without execute) must be flagged."""
    assert tier.classify_by_keywords("chmod 666 /etc/hosts") == tier.TIER_2


def test_chmod_0666_tier2():
    """'chmod 0666' (4-digit 666) must be flagged."""
    assert tier.classify_by_keywords("chmod 0666 sensitive.conf") == tier.TIER_2


def test_chown_root_tier2():
    """'chown root' must be flagged (root ownership change)."""
    assert tier.classify_by_keywords("chown root:root /etc/cron.d/job") == tier.TIER_2


def test_dd_if_tier2():
    """'dd if=' (raw disk copy/wipe) must be flagged."""
    assert tier.classify_by_keywords("dd if=/dev/zero of=/dev/sda bs=4M") == tier.TIER_2


def test_mkfs_tier2():
    """'mkfs' (make filesystem, destructive) must be flagged."""
    assert tier.classify_by_keywords("mkfs.ext4 /dev/sdb1") == tier.TIER_2


def test_fdisk_tier2():
    """'fdisk' (disk partition editor) must be flagged."""
    assert tier.classify_by_keywords("fdisk /dev/sda to repartition") == tier.TIER_2


def test_iptables_flush_tier2():
    """'iptables -F' (flush all firewall rules) must be flagged."""
    assert tier.classify_by_keywords("iptables -F INPUT to reset firewall") == tier.TIER_2


def test_systemctl_stop_tier2():
    """'systemctl stop' must be flagged (service disruption)."""
    assert tier.classify_by_keywords("systemctl stop nginx before deploy") == tier.TIER_2


def test_systemctl_disable_tier2():
    """'systemctl disable' must be flagged (permanent service removal)."""
    assert tier.classify_by_keywords("systemctl disable firewalld on boot") == tier.TIER_2


def test_path_mkfs_script_tier2():
    """Path containing 'mkfs' must be flagged (infra filesystem script)."""
    assert tier.classify_by_keywords("", changed_paths=["scripts/mkfs_helper.sh"]) == tier.TIER_2


def test_path_fdisk_wrapper_tier2():
    """Path containing 'fdisk' must be flagged."""
    assert tier.classify_by_keywords("", changed_paths=["utils/fdisk_wrapper.py"]) == tier.TIER_2


def test_path_iptables_conf_tier2():
    """Path containing 'iptables' must be flagged."""
    assert tier.classify_by_keywords("", changed_paths=["config/iptables_rules.conf"]) == tier.TIER_2


# ---------------------------------------------------------------------------
# Destructive operations: false-positive guards (must stay Tier 1)
# These descriptions contain surface-similar tokens but must NOT trigger.
# ---------------------------------------------------------------------------


def test_rmdir_helper_tier1():
    """'rmdir_helper cleanup' must NOT trigger rm -rf pattern.

    'rmdir_helper' starts with 'rm' but has no space+dash after it,
    so the rm flag pattern does not match.
    """
    assert tier.classify_by_keywords("rmdir_helper cleanup routine") == tier.TIER_1


def test_perform_removal_unused_imports_tier1():
    """'perform removal of unused imports' must stay Tier 1.

    'removal' is not 'rm -rf'; \\bremove\\b doesn't match 'removal'.
    No destructive operation is present.
    """
    assert tier.classify_by_keywords("perform removal of unused imports") == tier.TIER_1


def test_ddd_debugger_tier1():
    """'ddd debugger tool' must NOT trigger the dd if= pattern.

    'ddd' has no word boundary after 'dd' (followed by another 'd'),
    and there is no 'if=' substring.
    """
    assert tier.classify_by_keywords("ddd debugger tool") == tier.TIER_1


def test_remove_unused_imports_identifier_tier1():
    """'remove_unused_imports' (compound identifier) must stay Tier 1.

    \\bremove\\b does not match because '_' is a word character,
    so there is no word boundary between 'remove' and '_unused'.
    """
    assert tier.classify_by_keywords("remove_unused_imports") == tier.TIER_1


def test_format_code_tier1():
    """'format the code style' must NOT trigger mkfs or fdisk patterns."""
    assert tier.classify_by_keywords("format the code style") == tier.TIER_1


def test_chmod_644_not_world_writable_tier1():
    """'chmod 644' is NOT world-writable; must stay Tier 1."""
    assert tier.classify_by_keywords("chmod 644 config.yaml") == tier.TIER_1


def test_chmod_755_not_world_writable_tier1():
    """'chmod 755' (owner rwx, group/others rx) is NOT world-writable; Tier 1."""
    assert tier.classify_by_keywords("chmod 755 run.sh") == tier.TIER_1


def test_enforce_push_tier1():
    """'enforce push policy' must NOT match \\bforce[-\\s]push\\b.

    'enforce' has no word boundary before 'force' (preceded by 'en').
    """
    assert tier.classify_by_keywords("enforce push policy in CI") == tier.TIER_1


def test_informal_naming_tier1():
    """Generic benign phrase with no destructive keywords stays Tier 1."""
    assert tier.classify_by_keywords("informal naming convention review") == tier.TIER_1
