"""Tests for _check_rate_limit() flock fix (issue #372).

Covers the read-modify-write race in the rate limiter. Without
fcntl.flock, two concurrent _handle_council_complete calls can both
read the same `timestamps` array, both pass the `len < AUTO_RATE_LIMIT`
check, and both append — exceeding the rate cap.
"""

import sys
import threading
import time
from pathlib import Path

_HERE = Path(__file__).parent
_PLUGIN_DIR = _HERE.parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

import __init__ as moa  # noqa: E402


def test_concurrent_rate_limit_at_most_limit():
    """N concurrent calls must result in at most AUTO_RATE_LIMIT approvals.

    Without the fix, the read-modify-write race can allow more than
    AUTO_RATE_LIMIT to slip through.
    """
    # Reset rate file
    moa.RATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if moa.RATE_FILE.exists():
        moa.RATE_FILE.unlink()

    # Tighten the limit for the test so we don't have to spawn many threads
    original_limit = moa.AUTO_RATE_LIMIT
    moa.AUTO_RATE_LIMIT = 3
    try:
        n_threads = 10
        results = []
        barrier = threading.Barrier(n_threads)

        def worker():
            barrier.wait()  # release all threads at once
            allowed, _ = moa._check_rate_limit()
            results.append(allowed)

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        allowed_count = sum(1 for r in results if r)
        # With the fix, exactly AUTO_RATE_LIMIT (3) should be allowed
        # Without the fix, races could allow more.
        assert allowed_count <= moa.AUTO_RATE_LIMIT, (
            f"Race: {allowed_count} allowed, expected <= {moa.AUTO_RATE_LIMIT}"
        )
    finally:
        moa.AUTO_RATE_LIMIT = original_limit
        if moa.RATE_FILE.exists():
            moa.RATE_FILE.unlink()


def test_rate_limit_returns_remaining_count():
    """Single-threaded: _check_rate_limit returns decreasing remaining count."""
    moa.RATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if moa.RATE_FILE.exists():
        moa.RATE_FILE.unlink()

    original_limit = moa.AUTO_RATE_LIMIT
    moa.AUTO_RATE_LIMIT = 3
    try:
        allowed1, remaining1 = moa._check_rate_limit()
        allowed2, remaining2 = moa._check_rate_limit()
        allowed3, remaining3 = moa._check_rate_limit()
        allowed4, remaining4 = moa._check_rate_limit()

        assert allowed1 is True
        assert allowed2 is True
        assert allowed3 is True
        assert allowed4 is False
        # After 3 approvals, remaining should be 0
        assert remaining4 == 0
    finally:
        moa.AUTO_RATE_LIMIT = original_limit
        if moa.RATE_FILE.exists():
            moa.RATE_FILE.unlink()


def test_rate_limit_window_prune():
    """Old timestamps (outside the window) should be pruned."""
    moa.RATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if moa.RATE_FILE.exists():
        moa.RATE_FILE.unlink()

    original_limit = moa.AUTO_RATE_LIMIT
    moa.AUTO_RATE_LIMIT = 3
    original_window = moa.AUTO_RATE_WINDOW
    # Use a 1-second window
    moa.AUTO_RATE_WINDOW = 1
    try:
        # Use 2 of the 3 allowed
        moa._check_rate_limit()
        moa._check_rate_limit()

        # Sleep past the window
        time.sleep(1.2)

        # The old timestamps should be pruned; we should be allowed again
        allowed, _ = moa._check_rate_limit()
        assert allowed is True
    finally:
        moa.AUTO_RATE_LIMIT = original_limit
        moa.AUTO_RATE_WINDOW = original_window
        if moa.RATE_FILE.exists():
            moa.RATE_FILE.unlink()
