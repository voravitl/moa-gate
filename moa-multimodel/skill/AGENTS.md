<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-10 | Updated: 2026-06-10 -->

# skill/

## Purpose
Contains `SKILL.md`, the Hermes skill definition that makes this plugin auto-discoverable by AI agents. Declares the plugin's name, description, keywords, activation triggers, and full operational specification so agents can invoke `/moa-multimodel` without reading the source.

## Key Files
| File | Description |
|------|-------------|
| `SKILL.md` | Hermes skill manifest: frontmatter with `name`, `description`, `keywords`; body documents activation, workflow steps, fail-back rules, slash commands, configuration, and a verified test signal (PR #366) |

## For AI Agents

### Working In This Directory
- `SKILL.md` is the single source of truth for AI-facing documentation of this plugin. Keep it in sync with `__init__.py` and `council.sh` whenever those files change.
- The frontmatter `keywords` list drives auto-discovery matching — add terms here when new trigger scenarios are added to the plugin.
- Do not add executable code or shell scripts to this directory. It is documentation-only.

### Testing Requirements
- After editing `SKILL.md`, verify frontmatter parses as valid YAML: `python3 -c "import yaml; yaml.safe_load(open('skill/SKILL.md').read().split('---')[1])"`.
- Confirm `name` in frontmatter matches `name` in `plugin.yaml`.

### Common Patterns
- Frontmatter block delimited by `---` at top of file (standard Hermes skill format).
- Fail-back rules in the skill body mirror the verified behavior documented in `__init__.py` module docstring — both must stay consistent.

## Dependencies

### Internal
- Documents the interface of `__init__.py` (slash commands, env vars, hook behavior) and `scripts/council.sh` (verdict semantics, rate-limit retry).

### External
None — this directory contains only a markdown file.

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
