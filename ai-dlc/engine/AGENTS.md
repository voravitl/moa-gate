<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-10 | Updated: 2026-06-10 -->

# engine

## Purpose
Provides the two runtime components that `__init__.py` calls on every intercepted tool invocation: a phase state machine that tracks and enforces the INCEPTION → CONSTRUCTION → OPERATION lifecycle, and a content verifier that applies loaded steering rules against file content before a write is allowed.

## Key Files
| File | Description |
|------|-------------|
| `__init__.py` | Empty package marker |
| `phase.py` | Phase state machine — `get_phase()`, `set_phase()`, `promote_phase()`, `can_write_in_phase()`, `get_status()`; persists state atomically to `~/.hermes/ai-dlc/phase.json` |
| `verifier.py` | Content scanner — `verify_content(content, file_path)` applies `deny_pattern` and `require_pattern` rules from `steering.registry.get_active_rules_for_path()`; returns `{"critical": [...], "warning": [...], "passed": bool}` |

## For AI Agents

### Working In This Directory
- `phase.py` defines `VALID_PHASES = ["INCEPTION", "CONSTRUCTION", "OPERATION"]` and `TRANSITIONS` dict at module top; add new phases there if the lifecycle grows.
- `promote_phase()` follows `TRANSITIONS` strictly — it only moves to the first listed next phase; direct `set_phase()` is available for admin/migration use.
- INCEPTION blocks writes to `CODE_EXTENSIONS` (`.py .rs .ts .js .tsx .jsx .go .java .c .cpp .swift .kt .rb`); config/spec files are allowed. The check lives in `can_write_in_phase()` but the gating happens in `__init__.py:pre_tool_call`.
- `verifier.py` handles only `deny_pattern` and `require_pattern` rule types; `heuristic` (ARCH-005 max_lines) is declared in the YAML but is not yet evaluated by `verify_content` — do not add heuristic handling without a matching test.
- Both modules resolve HOME at call time via `os.path.expanduser("~")`; never cache `Path.home()` at module level.
- Atomic writes use `tempfile.mkstemp` in the same directory as the target, followed by `os.replace`.

### Testing Requirements
- Tests in `tests/test_ai_dlc_compass.py` cover phase state via `SteeringLoadedTest`, `PayloadExtractionTest`, and `DynamicHomeTest`.
- Verifier regex safety is tested in `RegexSafetyTest` — bad `deny_pattern` and bad `path_pattern` regexes must not raise; they log a warning and skip the rule.
- Run: `python3 -m pytest tests/test_ai_dlc_compass.py` from repo root.
- Syntax check: `make test` (in `ai-dlc/`) compiles `engine/phase.py` and `engine/verifier.py`.

### Common Patterns
- `verify_content` returns early with `passed=True` when `content` is empty.
- `re.search` calls are wrapped in `try/except re.error` in both `verifier.py` and `registry.py`; on error the rule is skipped (fail-open for bad regex).
- `get_status()` returns the full phase dict including `history` list and `valid_phases` — use this for display; use `get_phase()` for boolean/string checks.

## Dependencies

### Internal
- `steering.registry.get_active_rules_for_path` — verifier calls this to get filtered rules per file path

### External
- Standard library only (`json`, `os`, `re`, `tempfile`, `logging`, `datetime`)

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
