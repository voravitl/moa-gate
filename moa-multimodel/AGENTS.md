<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-10 | Updated: 2026-06-10 -->

# moa-multimodel

## Purpose
Generator side of the MOA review pipeline. Spawns three real CLI models — Claude Sonnet (Architect), OpenAI Codex (Skeptic), and Google Gemini via AGY (Pragmatist) — as adversarial voices on a PR diff. Extracts APPROVE/REQUEST_CHANGES verdicts, posts them as PR comments, and writes `moa-gate/state.json` via `state.approve()` when 2/3 voices approve, allowing moa-gate's pre-commit hook to unblock the next commit.

## Key Files
| File | Description |
|------|-------------|
| `__init__.py` | Plugin entry point: `pre_tool_call` hook intercepts `gh pr create`, resolves repo/branch, captures diff, calls `_setup_voice_prompts()`, then runs `council.sh` |
| `plugin.yaml` | Hermes plugin manifest declaring `name: moa-multimodel`, `version: 0.1.0`, and the `pre_tool_call` hook |
| `scripts/council.sh` | Orchestrates the three model CLIs, classifies verdicts, writes state.json, posts PR comments and labels |
| `skill/SKILL.md` | Skill definition for AI auto-discovery of this plugin |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `scripts/` | Shell scripts for council execution (see `scripts/AGENTS.md`) |
| `skill/` | Hermes skill definition (see `skill/AGENTS.md`) |

## For AI Agents

### Working In This Directory

- **Shell injection prevention**: `_validate_pr_number()` in `__init__.py` rejects any PR identifier that does not match `^[A-Za-z0-9_-]+$`, substituting `"manual"`. All paths written into `/tmp/*-cmd.sh` prompt files are wrapped with `shlex.quote()` before interpolation.
- **Voice prompt files** are written to `/tmp/{claude,codex,agy,agy-pipe}-cmd.sh` by `_setup_voice_prompts()`. These are executable bash wrappers that pass a single fully-quoted string argument to the respective CLI. Never pass raw user input or unsanitized paths into these templates.
- **Default branch resolution**: `_resolve_default_branch()` probes `origin/HEAD` symref first, then falls back to `main`/`master` probe. Do not hardcode `main` in new diff-capture logic.
- **Never block the PR**: the `pre_tool_call` hook returns `None` (allow) after council runs; only a council timeout or 0/3 substantive verdicts returns `{"action": "block", ...}`.
- **Auto-trigger can be disabled**: set `MOA_MULTIMODEL_AUTOTRIGGER=0` in env before testing to avoid unintended council runs.

### Testing Requirements
- Run `python3 -c "import moa_multimodel"` (or `import __init__`) to check for import errors.
- Integration test: capture a real diff, call `_setup_voice_prompts()`, verify `/tmp/claude-cmd.sh` contains a `shlex.quote`-wrapped prompt with no raw special characters.
- For `council.sh` changes, see `scripts/AGENTS.md`.

### Common Patterns
- Path resolution follows a three-step priority: env var > filesystem probe > hardcoded default. Apply this pattern to any new path lookups.
- All subprocess calls use list-form args (not shell=True) with explicit `timeout=`.
- Failures are logged with `logger.warning()` and return `None` rather than raising, to avoid blocking the user's workflow.

## Dependencies

### Internal
- `moa-gate` sibling plugin — `state.py` must be importable from `MOA_GATE_PLUGIN_PATH` at runtime; the path is resolved by `_resolve_moa_gate_path()`.

### External
| Tool | Used by | Purpose |
|------|---------|---------|
| `git` | `__init__.py` | `rev-parse --show-toplevel`, `symbolic-ref`, `diff main...HEAD` |
| `bash` | `__init__.py` | Runs `council.sh` and the per-voice cmd files |
| `claude` CLI | `council.sh` / `/tmp/claude-cmd.sh` | Architect voice (model: sonnet) |
| `codex` CLI | `council.sh` / `/tmp/codex-cmd.sh` | Skeptic voice |
| `agy` CLI | `council.sh` / `/tmp/agy-cmd.sh` | Pragmatist voice |
| `gh` CLI | `council.sh` | Posts PR comments and labels |
| `python3` | `council.sh` | Inline heredoc that calls `state.approve()` |

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
