<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-10 | Updated: 2026-06-10 -->

# hooks

## Purpose
Git hook enforcement layer for MOA Gate. Contains the `pre-commit.py` script that acts as Layer 3 (authoritative) enforcement — it verifies the HMAC-signed state file before every `git commit`, blocking commits when the gate is not approved, expired, or tampered with. Installed globally via `git config --global core.hooksPath ~/.hermes/moa-gate/` so it applies to all repositories on the machine.

## Key Files
| File | Description |
|------|-------------|
| `pre-commit.py` | Standalone Python 3 pre-commit hook: loads HMAC key from `MOA_GATE_KEY` env or `~/.hermes/.env`, reads `~/.hermes/moa-gate/state.json`, verifies HMAC signature, checks `status == "approved"`, and validates TTL — exits 1 (block) or 0 (allow) |

## For AI Agents

### Working In This Directory
- `pre-commit.py` is **intentionally standalone** — it imports only Python stdlib (`json`, `hmac`, `hashlib`, `os`, `sys`, `pathlib`, `datetime`). Do not add imports from `state.py` or any plugin module; the hook runs outside the Hermes plugin context.
- The HMAC canonical form used here (`sort_keys=True, ensure_ascii=False, separators=(",", ":")`) must stay in sync with `state.py`'s `_sign()` function. If you change the canonical form in `state.py`, update it here too.
- The hook uses a fail-closed design: any unexpected error (missing key, missing file, malformed JSON, old format without `expires_at`) exits 1. Never change this to fail-open.
- `HERMES_HOME` env var overrides `~/.hermes` — used in tests to point the hook at a temp directory.
- Installed by `make install-hook` and `scripts/install.sh` (step 3/5).

### Testing Requirements
```bash
# Verify hook is installed globally
git config --global core.hooksPath

# Syntax check
python3 -m py_compile hooks/pre-commit.py && echo "OK"

# Manual smoke test (requires approved state in ~/.hermes/moa-gate/state.json)
python3 hooks/pre-commit.py
```

### Common Patterns
- Exit code contract: `sys.exit(0)` = allow, `sys.exit(1)` = block.
- Error messages are written to `stderr` so git surfaces them in the terminal.
- State format version check: if `status == "approved"` but `expires_at` is absent, the hook rejects with an "outdated format" message — this prevents old v1 state files from bypassing TTL enforcement.

## Dependencies

### Internal
- Reads `~/.hermes/moa-gate/state.json` written by `../state.py`
- Must stay in sync with the HMAC signing convention in `../state.py`

### External
- Python stdlib only: `json`, `hmac`, `hashlib`, `os`, `sys`, `pathlib`, `datetime`

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
