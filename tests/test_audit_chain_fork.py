#!/usr/bin/env python3
"""Standalone test for audit chain fork resistance (issue #368).

Run: python3 tests/test_audit_chain_fork.py
"""

import os
import sys
import tempfile
import threading
from pathlib import Path

# Add plugin dir to sys.path for state.py lazy import
_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PLUGIN_DIR)

# Must set env before audit module loads (required by _get_hmac_key fallback)
os.environ["MOA_GATE_KEY"] = "test-key-for-audit-chain-fork-32bytes!!"

# Load audit.py via spec to bypass __init__.py relative imports
from importlib import util as imp_util
_spec = imp_util.spec_from_file_location("_audit_standalone", os.path.join(_PLUGIN_DIR, "audit.py"))
au = imp_util.module_from_spec(_spec)
_spec.loader.exec_module(au)

CHAIN_HASH_SEED = "0" * 64


def test_chain_does_not_fork_under_concurrency():
    """N concurrent log() calls produce a linear chain with no shared prev_hash."""
    original_path = au.AUDIT_FILE
    with tempfile.TemporaryDirectory() as tmpdir:
        test_path = os.path.join(tmpdir, "test_audit.log")
        au.AUDIT_FILE = Path(test_path)
        os.makedirs(os.path.dirname(test_path), exist_ok=True)
        open(test_path, "w").close()

        n_threads = 20
        barrier = threading.Barrier(n_threads)
        errors = []

        def worker(i: int):
            barrier.wait()
            try:
                au.log("test_fork", tool="", reason=f"worker-{i}")
            except Exception as e:
                errors.append((i, str(e)))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Worker errors: {errors}"

        entries = au.read_log(limit=100)
        assert len(entries) == n_threads, f"Expected {n_threads}, got {len(entries)}"

        entries_rev = list(reversed(entries))
        prev_hashes = set()
        for idx, entry in enumerate(entries_rev):
            ph = entry.get("prev_hash", "?")
            if idx == 0:
                assert ph == CHAIN_HASH_SEED, f"Genesis prev_hash should be seed, got {ph!r}"
            else:
                expected = entries_rev[idx - 1].get("hash", "")
                assert ph == expected, f"Entry {idx} prev_hash {ph!r} != previous hash {expected!r}"
            assert ph not in prev_hashes, f"Duplicate prev_hash {ph!r} at entry {idx} — chain fork!"
            prev_hashes.add(ph)

        print(f"✓ Chain integrity verified: {n_threads} entries, no forks")
    au.AUDIT_FILE = Path(original_path)


def test_verify_chain_no_violations():
    """verify_chain() should return empty list for a clean chain."""
    original_path = au.AUDIT_FILE
    with tempfile.TemporaryDirectory() as tmpdir:
        test_path = os.path.join(tmpdir, "test_audit2.log")
        au.AUDIT_FILE = Path(test_path)
        open(test_path, "w").close()

        for i in range(5):
            au.log("test_verify", tool="", reason=f"entry-{i}")

        violations = au.verify_chain()
        assert not violations, f"Clean chain should have 0 violations, got: {violations}"
        print(f"✓ verify_chain() returned 0 violations for clean chain")
    au.AUDIT_FILE = Path(original_path)


if __name__ == "__main__":
    test_chain_does_not_fork_under_concurrency()
    test_verify_chain_no_violations()
    print("\n✅ All audit chain fork tests passed")
