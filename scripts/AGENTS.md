<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-10 | Updated: 2026-06-10 -->

# scripts

## Purpose
Installation automation for the MOA Gate plugin. Contains the one-shot Bash installer that clones or updates the plugin repo, symlinks the `moa-adviser` skill, installs the global pre-commit hook, auto-generates the HMAC key, and verifies the installation — all in five labeled steps.

## Key Files
| File | Description |
|------|-------------|
| `install.sh` | One-shot installer (5 steps): clone/pull to `~/.hermes/plugins/moa-gate`, symlink skill to `~/.hermes/skills/devops/moa-adviser`, copy pre-commit hook to `~/.hermes/moa-gate/` and set global `core.hooksPath`, generate `MOA_GATE_KEY` via `openssl rand -hex 32` (fallback: `python3 secrets`), verify by importing `state.py` |

## For AI Agents

### Working In This Directory
- The script is designed to be piped from `curl` (`bash <(curl -sL ...)`). Do not use `dirname $0` or `$(cd "$(dirname ...)")` patterns — they break under process substitution. Path resolution must use the fixed `PLUGIN_DIR` variable set at the top.
- `set -euo pipefail` is active — every command must succeed or the script aborts.
- Step 4 appends to `~/.hermes/.env` only if `MOA_GATE_KEY` is not already present (idempotent re-runs).
- The verify step (step 5) calls `import state as st` from the cloned plugin to confirm the key is loadable — this is a live smoke test, not just a compile check.
- `make install` invokes this script; `make uninstall` reverses it by removing the symlinks.

### Testing Requirements
```bash
# Syntax check only (safe — no network, no side effects)
bash -n scripts/install.sh && echo "OK"

# AI-DLC installer syntax (from Makefile)
make lint-ai-dlc
```

### Common Patterns
- All paths are derived from `PLUGIN_DIR="$HOME/.hermes/plugins/moa-gate"` — a single variable at the top controls everything.
- Symlinks use `ln -sfn` (force + no-dereference) to safely replace existing symlinks on reinstall.
- Key generation falls back from `openssl` to `python3 secrets.token_hex(32)` for portability.

## Dependencies

### Internal
- Installs `../hooks/pre-commit.py` to `~/.hermes/moa-gate/`
- Imports `../state.py` at verify step to confirm HMAC key loads

### External
- `git`, `bash`, `openssl` (optional, Python stdlib fallback), `python3`

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
