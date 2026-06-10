<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-10 | Updated: 2026-06-10 -->

# tests

## Purpose
pytest suite for the MOA Gate plugin. Covers slash-command handlers, audit hash-chain fork resistance under concurrency, rate-limiter flock correctness, tier classification word-boundary fixes, and AI-DLC Compass regression tests. Tests run against the plugin modules loaded directly via `sys.path` manipulation — no installed package required.

## Key Files
| File | Description |
|------|-------------|
| `test_moa_gate_commands.py` | Tests for `_get_last_blocked_tool`, `/moa-emergency` (reason guard, approval, audit logging), `/moa-revoke`, `/moa-council-complete` (council hash computed), and help-text content |
| `test_audit_chain_fork.py` | Concurrency regression (issue #368): 20 threads write simultaneously to verify the hash chain stays linear with no shared `prev_hash` values |
| `test_rate_limit_flock.py` | Concurrency regression (issue #372): 10 threads race `_check_rate_limit()` to verify `fcntl.flock` prevents more than `AUTO_RATE_LIMIT` approvals from slipping through |
| `test_tier_wordboundaries.py` | Regression for issue #371: verifies that compound identifiers like `next_token`, `tokenizer`, `clear_cache`, `delete_temp_fixture` do not incorrectly trigger Tier 2 classification |
| `test_ai_dlc_compass.py` | 9 AI-DLC integration tests covering: `_mark_steering_loaded()` infinite-block bug, bad-regex crash in verifier/registry, payload extraction for patch/terminal/process, `install.sh` dirname-under-curl bug, critical-violation escalation evidence, hardcoded `tool='write_file'` bug, and stale `Path.home()` after HOME change |

## For AI Agents

### Working In This Directory
- Each test file inserts `str(Path(__file__).parent.parent)` into `sys.path` so it can import `state`, `audit`, `tier`, and `__init__` as bare module names — matching how Hermes loads the plugin at runtime.
- Tests redirect file paths (`au.AUDIT_FILE`, `st.STATE_DIR`) to `tempfile.mkdtemp()` directories so they never touch `~/.hermes/` state.
- `os.environ["MOA_GATE_KEY"]` must be set before any module import that transitively calls `_load_or_generate_key()`. All test files set it at the top.
- `test_audit_chain_fork.py` and `test_rate_limit_flock.py` are standalone scripts runnable with `python3 tests/test_*.py` as well as via pytest.
- `test_ai_dlc_compass.py` uses `importlib.util.spec_from_file_location` to reload the ai-dlc plugin under a transient `HOME` for each test — do not replace this with a regular import.

### Testing Requirements
```bash
# Run full suite
python3 -m pytest tests/ -v

# Run single file
python3 -m pytest tests/test_tier_wordboundaries.py -v

# Standalone concurrency tests
python3 tests/test_audit_chain_fork.py
python3 tests/test_rate_limit_flock.py

# Quick compile check (no test execution)
make test
```

### Common Patterns
- Concurrency tests use `threading.Barrier(n)` to synchronize all threads at a starting line before the race condition window.
- AI-DLC tests use a helper `load_ai_dlc(home: Path)` that sets `os.environ["HOME"]`, clears cached modules, then reloads via importlib — allows testing stale-path bugs without process isolation.
- Tier tests document the exact false-positive phrase in the docstring for traceability back to the issue.

## Dependencies

### Internal
- `../state.py`, `../audit.py`, `../tier.py`, `../__init__.py` (all loaded via sys.path)
- `../ai-dlc/__init__.py` and its submodules (loaded via importlib in `test_ai_dlc_compass.py`)

### External
- `pytest` (test runner)
- Python stdlib: `threading`, `tempfile`, `importlib`, `unittest`

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
