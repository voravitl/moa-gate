<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-10 | Updated: 2026-06-10 -->

# ai-dlc

## Purpose
AI-DLC Compass is a Hermes sub-plugin that enforces AI-Driven Development Lifecycle governance. It intercepts every write-class tool call (`patch`, `write_file`, `write`, `git_commit`, `gh_pr_create`, `skill_manage`, `terminal`, `process`) via the `pre_tool_call` hook, gates writes by lifecycle phase (INCEPTION blocks code files), scans content against YAML steering rules (security, architecture, compliance), and escalates critical violations as tamper-evident entries into the MOA-Gate audit chain at `~/.hermes/moa-gate/audit.log`.

## Key Files
| File | Description |
|------|-------------|
| `__init__.py` | Plugin entry point: `register()`, `pre_tool_call()`, slash-command handlers for `/ai-dlc steer ls`, `phase`, `phase promote`, `verify <file>`, `guide` |
| `plugin.yaml` | Plugin manifest — name `ai-dlc-compass`, version `0.1.0`, declares `pre_tool_call` hook |
| `Makefile` | `make install` (runs install.sh), `make test` (py_compile all modules), `make verify` (loads rules and prints count), `make uninstall` |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `engine/` | Phase state machine and content verifier (see `engine/AGENTS.md`) |
| `scripts/` | One-shot installer (see `scripts/AGENTS.md`) |
| `steering/` | Rule registry and bundled YAML rule sets (see `steering/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- `__init__.py` is the sole integration surface; it imports `engine.phase`, `engine.verifier`, and `steering.registry` as `ph`, `vr`, `sr`.
- `BLOCKED_TOOLS` and `CODE_EXTENSIONS` are frozensets defined at module top — update them here when adding new tool names or file extensions.
- State is written atomically to `~/.hermes/ai-dlc/state.json` and `phase.json`. Both use `tempfile.mkstemp` + `os.replace`; never write these files directly.
- MOA-Gate escalation appends to `~/.hermes/moa-gate/audit.log` using `fcntl.flock` for safe concurrent access.
- The steering-loaded flag at `~/.hermes/ai-dlc/steering_loaded.flag` must exist before writes to non-wiki/non-.hermes paths are permitted; `_mark_steering_loaded()` creates it.
- V4A bulk patch payloads are parsed by `_extract_patch_file_payloads()` which extracts per-file content using `*** Update/Add File:` and `*** Move to:` markers.

### Testing Requirements
- Tests live in `tests/test_ai_dlc_compass.py` (repo root `tests/`).
- Run: `python3 -m pytest tests/test_ai_dlc_compass.py` from the repo root.
- Syntax check only: `make test` (runs `python3 -m py_compile` on all four modules, no pytest needed).
- Each test class isolates HOME with `tempfile.TemporaryDirectory` and reloads the module via `importlib`; do not rely on global state between tests.
- The 7 bug classes covered: steering-loaded block, bad-regex safety, payload extraction for patch/terminal/process, installer curl-pipe detection, MOA audit evidence, tool name in violation records, dynamic HOME resolution.

### Common Patterns
- All path helpers (`_state_dir`, `_home`, `_steering_dir`) call `os.path.expanduser("~")` at call time — never at module load — to survive HOME reassignment in tests.
- Violation dicts always carry `rule_id`, `category`, `description`, `suggestion`, `severity`.
- `_handle_violations()` returns `{"block": True, "message": ...}` — the Hermes hook protocol for blocking a tool call.
- Returning `None` from `pre_tool_call` means allow.

## Dependencies

### Internal
- `engine.phase` — phase state machine
- `engine.verifier` — content scanner
- `steering.registry` — YAML rule loader

### External
- `fcntl` (stdlib) — exclusive file lock for audit log append
- `pyyaml` — YAML rule parsing (via `steering.registry`)
- Hermes plugin host — provides `pre_tool_call` hook and optional `ctx.register_command`

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
