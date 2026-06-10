<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-10 | Updated: 2026-06-10 -->

# skill

## Purpose
Contains the moa-adviser skill definition and its supporting reference knowledge base. The skill implements a Multi-Model Adviser Council that routes hard decisions through 5 real diverse models (MOA tool mode), 3 CLI tools (CLI mode), or same-model multi-prompt delegates (Cloud mode), with automatic fallback between tiers based on credit availability and data sensitivity.

## Key Files
| File | Description |
|------|-------------|
| `SKILL.md` | Main skill definition: mode decision tree, MOA/CLI/Cloud execution logic, synthesis protocol, and Thai/English bilingual prompts |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `references/` | Operational knowledge base — design docs, bug patterns, session logs, and model capability references (see `references/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- `SKILL.md` is the authoritative skill definition; edit it to change routing logic, mode thresholds, or synthesis prompts.
- Do not create new top-level `.md` files here; knowledge artifacts belong in `references/`.
- Match existing bilingual style (Thai decision labels, English technical terms) when editing `SKILL.md`.

### Testing Requirements
No automated tests for skill definitions. Validate changes by invoking the skill in a live session and confirming correct mode selection (MOA → CLI → Cloud fallback chain).

### Common Patterns
- Mode selection is purely conditional on: sensitive data flag → credits/tool availability → CLI tool availability.
- All synthesis verdicts must surface the actual model diversity level (5 models / 3 models / single model + warning).

## Dependencies

### Internal
- `references/` — referenced during skill execution for recovery procedures, model capability lookup, and execution patterns

### External
- `mixture_of_agents` MCP tool (MOA tool mode)
- `claude`, `codex`, `agy` CLI binaries (CLI mode)
- Claude Code `delegate_task` (Cloud mode)

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
