<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-10 | Updated: 2026-06-10 -->

# scripts

## Purpose
Contains the one-shot installer that wires ai-dlc-compass into a Hermes installation. It symlinks the plugin, copies bundled steering rule files to `~/wiki/steering/` (non-destructively), creates the state directory, and sets the initial INCEPTION phase via an inline Python call.

## Key Files
| File | Description |
|------|-------------|
| `install.sh` | 5-step installer: symlink plugin → copy steering rules → create state dir → set INCEPTION phase → verify py_compile; detects and rejects `bash <(curl ...)` execution at step 0 |

## For AI Agents

### Working In This Directory
- The script detects curl-pipe execution by checking whether `$0` resolves to a real file path; if not, it prints a clone-and-run instruction and exits non-zero. Do not remove this guard.
- `REPO_DIR` is resolved as two levels up from the script's own directory (`dirname $0/../..`), so the script must be run from a real filesystem checkout.
- Steering rule files are copied with `cp`, not symlinked, so users can edit `~/wiki/steering/*.yaml` without affecting the repo. Existing files are skipped (`[ ! -f "$target" ]`).
- The INCEPTION phase JSON is written by an inline `python3 -c` call, not by importing the plugin module, to avoid circular dependency on the install not yet being complete.
- Install target: `~/.hermes/plugins/ai-dlc` → symlink to repo `ai-dlc/` directory.
- Uninstall: `make uninstall` removes the symlink and `~/.hermes/ai-dlc/` state dir.

### Testing Requirements
- `InstallerTest.test_installer_detects_curl_pipe_and_fails_fast` in `tests/test_ai_dlc_compass.py` pipes the script content via stdin to `bash` (simulating curl-pipe) and asserts non-zero exit and the "clone the repo" message.
- Manual install test: run `bash ai-dlc/scripts/install.sh` from repo root; verify symlink at `~/.hermes/plugins/ai-dlc`, files in `~/wiki/steering/`, and `~/.hermes/ai-dlc/phase.json` with `phase: INCEPTION`.
- Syntax check: `make test` in `ai-dlc/` does not compile shell scripts; use `bash -n scripts/install.sh` for syntax validation.

### Common Patterns
- `set -euo pipefail` at top — any command failure aborts the installer.
- Steps are numbered `[1/5]` through `[5/5]` in stdout for user visibility.
- Uses `ln -sfn` (force, no-dereference) so re-running is idempotent.

## Dependencies

### Internal
- Reads `ai-dlc/steering/rules/*.yaml` to copy to `~/wiki/steering/`
- Validates `__init__.py`, `steering/registry.py`, `engine/phase.py`, `engine/verifier.py` via `python3 -m py_compile`

### External
- `bash` 4+, `python3`, standard POSIX tools (`mkdir`, `ln`, `cp`, `rm`)

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
