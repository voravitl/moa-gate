# AI-DLC Compass — Hermes Plugin

AI-Driven Development Lifecycle steering, phase engine, and policy verification for Hermes Agent.

## Architecture

```
Session Start
    │
    ▼
┌─ AI-DLC Compass ─────────────────────────────┐
│ 1. Steering loaded? → NO → block + educate   │
│ 2. Phase check → INCEPTION? → code block     │
│ 3. Content scan → violations? → block/fix    │
│ 4. All good → write allowed                  │
└──────────────────┬───────────────────────────┘
                   │ escalated (if critical)
                   ▼
┌─ MOA-Gate ───────────────────────────────────┐
│ Council vote → weight → approve/reject        │
└──────────────────────────────────────────────┘
```

## Files

| File | Purpose |
|------|---------|
| `__init__.py` | Plugin entry + pre_tool_call hook |
| `steering/registry.py` | Load YAML rules from ~/wiki/steering/ |
| `steering/rules/security.yaml` | 8 security rules (hardcoded secrets, auth, SQL injection) |
| `steering/rules/architecture.yaml` | 5 architecture rules (types, error handling, imports) |
| `steering/rules/compliance.yaml` | 3 compliance rules (audit, PII, sanitization) |
| `engine/phase.py` | Phase state machine (INCEPTION → CONSTRUCTION → OPERATION) |
| `engine/verifier.py` | Content scanner — match/require/deny patterns |
| `scripts/install.sh` | One-shot installer |
| `Makefile` | test, verify, install, uninstall |

## Steering Rules

Located at `~/wiki/steering/` (git-tracked):

```yaml
# Example: security.yaml
rules:
  - id: SEC-001
    description: "ห้าม hardcode secret"
    type: deny_pattern
    pattern: "(?:password|secret|api_key)\\s*[:=]\\s*['\"][^'\"]+"
    severity: critical
```

### Rule Types

| Type | Behavior |
|------|----------|
| `deny_pattern` | Block if pattern matches |
| `require_pattern` | Block if pattern NOT found |
| `heuristic` | Block if metrics exceed threshold |

### Severity Levels

| Severity | Action |
|----------|--------|
| `critical` | Block + suggest fix + escalate to MOA-Gate Tier 2 |
| `warning` | Warn but allow (education only) |

## Phase Engine

```
INCEPTION → CONSTRUCTION → OPERATION
```

- **INCEPTION**: Block code writes, allow spec/requirement files only
- **CONSTRUCTION**: Allow code writes + verify steering
- **OPERATION**: Allow config/hotfix changes

Promote: `python3 -c "from engine.phase import promote_phase; print(promote_phase())"`

## Integration with MOA-Gate

| Event | Action |
|-------|--------|
| Steering critical violation | Auto-escalate to MOA-Gate Tier 2 |
| MOA-Gate approved | Phase promote check |
| Shared state | ~/.hermes/ai-dlc/ (file-based, no RPC) |

## Commands

| Command | Effect |
|---------|--------|
| `/ai-dlc steer ls` | List active steering rules |
| `/ai-dlc phase` | Check current phase |
| `/ai-dlc verify <file>` | Manual verify against steering |
| `/ai-dlc guide` | Show guidance for current phase |
