<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-10 | Updated: 2026-06-10 -->

# steering

## Purpose
Implements the rule registry that loads and filters YAML steering rules for the verifier. Rules are sourced first from `~/wiki/steering/` (user-editable, git-tracked outside the repo) and fall back to the bundled defaults in `steering/rules/`. This separation lets users override any rule category without modifying the plugin source.

## Key Files
| File | Description |
|------|-------------|
| `__init__.py` | Empty package marker |
| `registry.py` | `load_rules(categories)` merges user wiki rules with bundled defaults; `get_active_rules_for_path(path)` filters rules by `path_patterns` regex list; `format_rules_summary(rules)` formats rules for display |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `rules/` | Bundled default YAML rule sets for security, architecture, compliance (see `rules/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- `load_rules()` loads categories `["security", "architecture", "compliance"]` by default. User files at `~/wiki/steering/{category}.yaml` take full precedence — if a user file exists for a category, the bundled file is not loaded at all (no merge within a category).
- Each loaded rule dict gets a `_source` field injected (path to the YAML file) for debugging.
- `get_active_rules_for_path()` matches each rule's `path_patterns` list (list of regex strings) against the target file path using `re.search`. Rules with no `path_patterns` key default to `[".*"]` (match all). Bad regexes are caught, logged, and treated as a match (fail-open).
- HOME is resolved at call time via `os.path.expanduser("~")` — never module-level — to support test HOME isolation.
- `DEFAULT_RULES_DIR` is a module-level `Path(__file__).parent / "rules"` — this is safe because it is relative to the source file, not HOME.

### Testing Requirements
- `RegexSafetyTest` in `tests/test_ai_dlc_compass.py` validates that bad `path_pattern` regex in a user steering file does not crash `get_active_rules_for_path`.
- `DynamicHomeTest` validates that `load_rules()` picks up rules from the new HOME after `os.environ["HOME"]` is changed.
- `make verify` (in `ai-dlc/`) runs `load_rules()` against the bundled rules and prints the total count — use this as a quick sanity check after editing YAML files.

### Common Patterns
- Rule YAML structure: `{id, description, type, pattern, severity, suggestion, path_patterns, tags}`.
- `type` values recognized by verifier: `deny_pattern`, `require_pattern`. (`heuristic` is present in ARCH-005 YAML but not yet evaluated.)
- `severity`: `critical` (block + MOA escalation) or `warning` (block with education message).
- `yaml.safe_load` is used — never `yaml.load`.

## Dependencies

### Internal
- Called by `engine.verifier.verify_content` and directly by `__init__.py` slash-command handlers

### External
- `pyyaml` — YAML parsing

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
