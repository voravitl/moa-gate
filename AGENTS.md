<!-- Generated: 2026-06-10 | Updated: 2026-06-10 -->

# moa-gate

## Purpose
Root of the MOA Gate + AI-DLC Compass Hermes plugin suite. Contains the core enforcement gate (`__init__.py`, `state.py`, `audit.py`, `tier.py`) that intercepts write/destructive tool calls in Hermes Agent and blocks them unless an HMAC-signed council approval is present. Version 1.1.0, Python ≥3.10, MIT licence. The gate works alongside two sister sub-plugins (`ai-dlc/`, `moa-multimodel/`) and a skill (`skill/`) that together form a full multi-model code review and lifecycle governance system.

## Key Files
| File | Description |
|------|-------------|
| `__init__.py` | Plugin entry point: `pre_tool_call` hook + all slash-command handlers (`/moa-status`, `/moa-council-complete`, `/moa-emergency`, `/moa-revoke`, `/moa-log`, `/moa-verify`) |
| `state.py` | HMAC-SHA256 signed state file management — read/write with TTL (default 15 min, max 60 min), auto-approve logic, per-session state files under `~/.hermes/moa-gate/sessions/`, session GC |
| `audit.py` | Append-only audit log (`~/.hermes/moa-gate/audit.log`) with SHA-256 hash chain linking every entry to the prior one for tamper-evidence |
| `tier.py` | Two-tier classification engine: Tier 1 (auto-approve if council ≥80%) vs Tier 2 (manual only) — uses separate path/free-text regexes with word boundaries to avoid false positives on compound identifiers |
| `plugin.yaml` | Hermes plugin manifest: name `moa-gate` v1.1.0, registers `pre_tool_call` hook |
| `pyproject.toml` | Python build config; no runtime deps beyond stdlib; pytest configured with `testpaths = ["tests"]` |
| `Makefile` | `make install`, `make test` (compile check), `make install-hook`, `make test-ai-dlc`, `make verify-ai-dlc` targets |
| `README.md` | Architecture overview and quick-start guide (bilingual EN/TH) |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `docs/` | User-facing documentation — command reference and full user guide (see `docs/AGENTS.md`) |
| `hooks/` | Git hook enforcement layer — pre-commit HMAC verifier (see `hooks/AGENTS.md`) |
| `scripts/` | Installation automation (see `scripts/AGENTS.md`) |
| `skill/` | `moa-adviser` Hermes skill — orchestrates multi-model council votes via CLI/Cloud modes |
| `tests/` | pytest suite covering gate commands, audit chain, rate limiting, and tier classification (see `tests/AGENTS.md`) |
| `ai-dlc/` | Sister plugin: AI-Driven Development Lifecycle Compass — phase state machine (INCEPTION → CONSTRUCTION → OPERATION) and steering-rule compliance via YAML rules |
| `moa-multimodel/` | Sister plugin: spawns 3 real distinct models (Claude Sonnet + OpenAI Codex + Google Gemini/AGY) as adversarial PR-review voices, writes results to moa-gate state |
| `src/` | Present but empty — no AGENTS.md |

## For AI Agents

### Working In This Directory
- `__init__.py` uses relative imports (`import state as st`, `import audit as au`, `import tier as ti`) via a `sys.path` injection/cleanup pattern at the top — do not break this pattern when editing imports.
- Blocked tools are defined in the `BLOCKED_TOOLS` frozenset. Adding a tool there is the only change needed to gate a new tool; no other file requires editing.
- `TERMINAL_READONLY_PATTERNS` regex allows safe read-only commands through even when the gate is pending — extend it carefully to avoid bypasses.
- All environment overrides (`MOA_GATE_KEY`, `MOA_GATE_AUTO_THRESHOLD`, `MOA_GATE_SHADOW_MODE`, `MOA_GATE_COOLDOWN_SECS`) are read at module load time.
- `SAFETY_ROLES = frozenset({"critic", "skeptic"})` — dissent from these roles forces Tier 2 even if the vote percentage is ≥80%.

### Testing Requirements
```bash
# Syntax/compile check (fast, no side effects)
make test

# Full test suite
python3 -m pytest tests/ -v

# Single file
python3 -m pytest tests/test_tier_wordboundaries.py -v
```

### Common Patterns
- State reads always use `fcntl.flock` for concurrent read-modify-write safety (see `state.py` and the rate limiter in `__init__.py`).
- HMAC is computed over canonical JSON (`sort_keys=True, separators=(",", ":")`) of all fields except `"hmac"` itself.
- The audit log chains entries via `prev_hash` — always read the last hash from disk (never cache in memory) before appending.

## Dependencies

### Internal
- `state.py` — imported by `__init__.py` and `hooks/pre-commit.py`
- `audit.py` — imported by `__init__.py`
- `tier.py` — imported by `__init__.py`

### External
- Python stdlib only: `hmac`, `hashlib`, `json`, `fcntl`, `secrets`, `tempfile`, `re`, `pathlib`, `threading`
- No third-party packages (see `pyproject.toml`)

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
