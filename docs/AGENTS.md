<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-10 | Updated: 2026-06-10 -->

# docs

## Purpose
Human-readable documentation for the MOA Gate + AI-DLC Compass system. Contains the full bilingual (EN/TH) user guide and a complete slash-command reference. These files are read by operators and AI agents to understand the plugin's behaviour, slash command parameters, and workflow without reading source code.

## Key Files
| File | Description |
|------|-------------|
| `COMMANDS.md` | Slash command reference for all MOA Gate commands (`/moa-status`, `/moa-council-complete`, `/moa-emergency`, `/moa-revoke`, `/moa-log`, `/moa-verify`) and AI-DLC file-system operations; includes JSON schemas and auto-approve decision table |
| `USER_GUIDE.md` | Full operator guide (15KB): architecture overview, flow diagrams, quick-start steps, steering rule configuration, and troubleshooting — bilingual EN/TH |

## For AI Agents

### Working In This Directory
- `COMMANDS.md` is the authoritative reference for slash-command parameter schemas. When modifying a command handler in `__init__.py`, update the corresponding entry in `COMMANDS.md` in the same commit.
- `USER_GUIDE.md` describes the three AI-DLC phases (INCEPTION, CONSTRUCTION, OPERATION) and their write-tool access rules — consult it before changing phase logic in `ai-dlc/engine/phase.py`.
- Both files are Markdown; keep tables aligned and code blocks fenced with matching language tags.
- AI-DLC has no slash commands of its own — its state is inspected via `cat ~/.hermes/ai-dlc/phase.json` and steering rules via `~/wiki/steering/*.yaml`.

### Testing Requirements
No automated tests for documentation. Verify manually that command examples in `COMMANDS.md` match the actual handler signatures in `__init__.py` after any command changes.

### Common Patterns
- Command aliases are documented as `"/moa-gate status" or "/moa-status"` — both forms exist in `__init__.py`.
- The auto-approve decision table in `COMMANDS.md` (≥80% + Tier 1 → auto, ≥80% + Tier 2 → block, Critic/Skeptic dissent → force Tier 2) mirrors the logic in `__init__.py`'s `_handle_council_complete`.

## Dependencies

### Internal
- Documents behaviour implemented in `../__init__.py`, `../state.py`, `../tier.py`
- References `../ai-dlc/` phase engine and steering rules

### External
None — static Markdown only.

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
