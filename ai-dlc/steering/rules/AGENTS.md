<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-10 | Updated: 2026-06-10 -->

# rules

## Purpose
Bundled default steering rule sets used as fallback when no user override exists at `~/wiki/steering/`. Three YAML files cover security (8 rules), architecture (5 rules), and compliance (3 rules) targeting Python/Rust/TypeScript microservices in a Thai financial services context.

## Key Files
| File | Description |
|------|-------------|
| `security.yaml` | 8 rules (SEC-001 to SEC-008): hardcoded secrets (critical), input validation (critical), auth on sensitive routes (critical), `eval`/`exec` (critical), SQL string interpolation (critical), wildcard CORS (warning), missing rate limiting (warning), disabled CSRF (critical) |
| `architecture.yaml` | 5 rules (ARCH-001 to ARCH-005): missing type hints (warning), bare `.unwrap()` in Rust (warning), wildcard imports in Python (warning), missing docstrings on API functions (warning), function length >60 lines heuristic (warning, not yet evaluated by verifier) |
| `compliance.yaml` | 3 rules (COMP-001 to COMP-003): missing audit logging on API endpoints (critical), PII in log statements (critical), missing input sanitization (warning); scoped to `banking-microservices` |

## For AI Agents

### Working In This Directory
- These files are the install-time source: `scripts/install.sh` copies them to `~/wiki/steering/` on first install (skips if target already exists).
- To change a rule globally for a project, edit the copy at `~/wiki/steering/` rather than these bundled files — that keeps user customizations out of the repo.
- To change the default shipped with the plugin, edit here and re-run `make install` (which re-copies only missing files; existing user copies are not overwritten).
- `path_patterns` is a list of regex strings matched via `re.search` against the absolute file path. Omitting `path_patterns` defaults to `[".*"]`.
- `severity: critical` causes `pre_tool_call` to return `block: True` and write a `shadow_block` entry to the MOA-Gate audit log. `severity: warning` also blocks but does not escalate.
- The `heuristic` type on ARCH-005 (`max_lines: 60`) is not yet implemented in `engine/verifier.py` — the rule is present in YAML but silently skipped at runtime.

### Testing Requirements
- No direct tests for individual YAML files; rule logic is exercised through `verifier.py` tests in `tests/test_ai_dlc_compass.py`.
- After editing a YAML file, run `make verify` from `ai-dlc/` to confirm the file parses and loads correctly.
- Validate YAML syntax: `python3 -c "import yaml; yaml.safe_load(open('security.yaml'))"`.

### Common Patterns
- Rule IDs follow `{PREFIX}-{NNN}` format: `SEC-*`, `ARCH-*`, `COMP-*`.
- All `pattern` values are Python `re` compatible regex strings.
- `tags` list is metadata only — not used by the verifier at runtime.
- `scope` field in YAML header is documentation only.

## Dependencies

### Internal
- Loaded by `steering/registry.py` via `DEFAULT_RULES_DIR = Path(__file__).parent / "rules"`

### External
- `pyyaml` for parsing; no runtime imports within the YAML files themselves

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
