<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-10 | Updated: 2026-06-10 -->

# references

## Purpose
Operational knowledge base for the moa-adviser skill. Contains design documents, session-derived bug patterns, model capability inventories, execution patterns, and recovery procedures accumulated from real MOA Gate usage. AI agents and human contributors consult these files when implementing, debugging, or extending the MOA Gate plugin and adviser skill.

## Key Files
| File | Description |
|------|-------------|
| `agy-code-review.md` | Proven pattern for using the `agy` CLI as a code reviewer, including timeout handling and fix-push workflow |
| `cli-tool-models.md` | Model capability inventory per CLI tool (claude, codex, agy) for MOA Adviser Council, last audited 2026-05-27 |
| `gemini-tts.md` | Gemini 3.1 Flash TTS voice and emotion tag reference for audio output |
| `hermes-shell-hook-gate.md` | Full reference for the Hermes `pre_tool_call` shell hook that intercepts write tools before execution |
| `moa-gate-agent-protocol-flow.md` | Real session example (PR #299) showing the full MOA Gate agent protocol flow for a production fix |
| `moa-gate-auto-approve-agent-flow.md` | Step-by-step agent execution sequence from the 2026-05-28 auto-approve implementation session |
| `moa-gate-auto-approve-design.md` | Design spec and implementation status for MOA Gate auto-approve tier, including modified files and test results |
| `moa-gate-jq-pitfalls.md` | Critical jq filter bugs in `moa-gate.yml` GitHub Actions — specifically the `select(A) and B` boolean trap |
| `moa-gate-plugin-design.md` | Architecture design v2 with 7-voice council review, iteratively refined through MOA council sessions |
| `moa-gate-recovery.md` | Recovery procedure hierarchy for when MOA Gate blocks write tools: HMAC key issues, tool bypass, 4-cause checklist |
| `moa-gate-session-fix.md` | Root cause and fix for MOA Gate blocking writes due to empty or mismatched `session_id` in state.json |
| `moa-pr-review-cycle.md` | Spawn pattern for pre-merge PR review using all 3 MOA CLI voices as a 3-voice gate |
| `ollama-prompts.md` | Architecture and prompts for Ollama Cloud MOA with 5 models for real diversity |
| `parallel-cli-execution.md` | Reusable pattern for spawning multiple CLI AI tools in parallel, collecting outputs, and synthesizing a verdict |
| `rcsa-analysis-templates.md` | Prompt templates for RCSA cross-reference analysis with BIA/KPI/KRI data using 4 Ollama voices + 1 Agy meta-reviewer |

## For AI Agents

### Working In This Directory
- These are reference-only documents; do not modify them during normal skill execution.
- When a session reveals a new bug pattern or recovery procedure, append a new file here following the existing naming convention: `moa-gate-<topic>.md`.
- Consult `moa-gate-recovery.md` and `moa-gate-session-fix.md` first when MOA Gate blocks unexpectedly.
- Consult `cli-tool-models.md` before selecting a CLI tool in MOA mode to confirm model availability.

### Testing Requirements
No automated tests for reference documents. Accuracy is validated by cross-checking against actual CLI tool behavior or plugin source code in `__init__.py`, `state.py`, `audit.py`, `tier.py`.

### Common Patterns
- Session-log files (e.g., `moa-gate-agent-protocol-flow.md`) record date, PR number, and actual command sequences — follow this format when adding new session docs.
- Design docs include implementation status and modified file lists at the top.

## Dependencies

### Internal
- `../SKILL.md` — the skill that consumes these references at runtime

### External
- MOA Gate plugin source: `__init__.py`, `state.py`, `audit.py`, `tier.py` (in plugin package)
- GitHub Actions workflow: `moa-gate.yml`

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
