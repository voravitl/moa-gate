# MOA Gate — Hermes Plugin

Multi-Model Adviser (MOA) enforcement gate for Hermes Agent.  
Controls write/destructive tool access based on council approval.

## Architecture

```
┌─ MOA Council ─────────────────────────────────┐
│  5 voices (Architect, Critic, Strategist,      │
│  Pragmatist, Skeptic) → vote on changes         │
└──────────────────────┬────────────────────────┘
                       │ ≥80% approve
                       ▼
┌─ Auto-Approve Engine ──────────────────────────┐
│  ✓ Tier 1 (Auto) = non-security changes         │
│  ✓ Weighted veto (Critic/Skeptic dissent = T2) │
│  ✓ Cool-down period (default 120s)              │
│  ✓ Rate limit (5/hour default)                  │
│  ✓ Shadow mode (record only)                    │
└──────────────────────┬────────────────────────┘
                       │ state signed + audited
                       ▼
┌─ Enforcement Layers ───────────────────────────┐
│  Layer 1: Plugin (pre_tool_call hook)          │
│  Layer 2: Audit log (tamper-evident hash chain)│
│  Layer 3: HMAC-signed state file               │
│  (Git pre-commit hook in separate repo)         │
└────────────────────────────────────────────────┘
```

## Files

| File | Purpose |
|------|---------|
| `state.py` | HMAC-SHA256 signed state + TTL + auto-approve |
| `audit.py` | Append-only audit log with SHA-256 hash chain |
| `tier.py` | Tier classification (T1 auto / T2 manual) |
| `__init__.py` | Plugin hook + slash commands |
| `plugin.yaml` | Hermes plugin manifest |

## Installation

```bash
# Clone to plugins dir
git clone git@github.com:voravitl/moa-gate.git ~/.hermes/plugins/moa-gate

# Set HMAC key (auto-generated on first use if missing)
echo 'MOA_GATE_KEY=your-64-char-hex-key' >> ~/.hermes/.env
```

## Slash Commands

| Command | Description |
|---------|-------------|
| `/moa-status` | Show gate state (mode, tier, dissent, cool-down) |
| `/moa-approve --by voices --reason "..."` | Manual approval |
| `/moa-approve --override --reason "..."` | Bypass cool-down |
| `/moa-council-complete '<json>'` | Submit council results for auto-approve |
| `/moa-revoke` | Reset to pending |
| `/moa-log [N]` | Show audit log |
| `/moa-verify` | Verify audit chain integrity |

## Auto-Approve Flow

```
/moa-council-complete '{
  "votes": {"architect":"approve","critic":"dissent",...},
  "task_description": "fix auth",
  "changed_paths": ["src/auth.rs"]
}'

1. Check ≥80% threshold (4/5)
2. Check weighted veto (Critic/Skeptic dissent → Tier 2)
3. Classify tier (keyword + vote → conservative merge)
4. Check rate limit
5. Check shadow mode
6. Auto-approve + cool-down period
7. Create GH issue for dissent
```

## Configuration (via env)

| Variable | Default | Description |
|----------|---------|-------------|
| `MOA_GATE_AUTO_THRESHOLD` | `0.8` | Auto-approve threshold (80%) |
| `MOA_GATE_COOLDOWN_SECS` | `120` | Cool-down period in seconds |
| `MOA_GATE_AUTO_RATE_LIMIT` | `5` | Max auto-approves per hour |
| `MOA_GATE_SHADOW_MODE` | `0` | Set to `1` for record-only mode |

## Security

- **HMAC-SHA256**: State file signed with key from `~/.hermes/.env`
- **Hash chain**: Every audit log entry linked to previous via SHA-256
- **Fail-closed**: Any error → block write tools
- **Session isolation**: Cross-session approval rejected
- **Atomic writes**: `tempfile` + `os.replace` (no partial writes)
- **Weighted veto**: Critic/Skeptic dissent forces manual approval

## Requirements

- Hermes Agent (Python 3.10+)
- `fcntl` (Unix/macOS — not Windows-compatible)

## License

MIT
