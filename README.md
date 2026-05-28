# MOA Gate — Hermes Plugin + Skill

Multi-Model Adviser (MOA) enforcement gate for Hermes Agent.  
Controls write/destructive tool access based on council approval.

รวม 2 component ใน repo เดียว:

| Component | Path | หน้าที่ |
|-----------|------|--------|
| **Plugin** `moa-gate` | `plugin/` | 🔒 Block/unblock tools, signed state, audit log |
| **Skill** `moa-adviser` | `skill/` | 🧠 เรียก 5-voice council เพื่อตัดสินใจ |

## Architecture

```
User wants to make changes
        │
        ▼
┌─ moa-adviser (skill) ───────────────────────┐
│  /moa-adviser --voices 5                     │
│  → 5 models (claude, codex, agy, ollama...)  │
│  → approve / dissent / reason                │
└──────────────────────┬──────────────────────┘
                       │ council result
                       ▼
┌─ moa-council-complete ───────────────────────┐
│  /moa-council-complete '{"votes":...}'        │
│  → Auto-approve if ≥80% + Tier 1             │
│  → Weighted veto (Critic/Skeptic = T2)       │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─ moa-gate (plugin) ──────────────────────────┐
│  1. State: HMAC-SHA256 signed                │
│  2. Audit: hash-chain log                    │
│  3. Cool-down / shadow / rate limit          │
│  4. pre_tool_call → allow block              │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
              Write tools ผ่าน ✅ / ถูกบล็อก 🛑
```

## Files

### Plugin (`plugin/`)

| File | Purpose |
|------|---------|
| `state.py` | HMAC-SHA256 signed state + TTL + auto-approve |
| `audit.py` | Append-only audit log with SHA-256 hash chain |
| `tier.py` | Tier classification (T1 auto / T2 manual) |
| `__init__.py` | Plugin hook + slash commands |
| `plugin.yaml` | Hermes plugin manifest |

### Skill (`skill/`)

| File | Purpose |
|------|---------|
| `SKILL.md` | MOA Adviser Council setup + CLI/Cloud mode |
| `references/` | Docs for plugin integration, recovery, design |

## Installation

### AI-friendly (one-shot)

AI agent ใช้คำสั่งนี้ได้เลย — clone, skill, hook, key ทำทั้งหมด:

```bash
bash <(curl -sL https://raw.githubusercontent.com/voravitl/moa-gate/main/scripts/install.sh)
```

### Manual (clone)

```bash
# One-liner:
git clone git@github.com:voravitl/moa-gate.git ~/.hermes/plugins/moa-gate && \
  ln -sf ~/.hermes/plugins/moa-gate/skill ~/.hermes/skills/devops/moa-adviser

# Or with Makefile:
git clone git@github.com:voravitl/moa-gate.git && cd moa-gate && make install
```

### Pre-commit hook (optional)

```bash
make install-hook
# หรือ: git config --global core.hooksPath ~/.hermes/moa-gate/
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
- **TTL expiry**: Default 15 min — state auto-expires
- **P1 — Startup sweep**: Plugin checks & expires stale state on load
- **P2 — Session end**: Auto-revoke when Hermes session ends
- **P0 — Git pre-commit hook**: Worldwide git hook enforcing gate at OS level

## Requirements

- Hermes Agent (Python 3.10+)
- `fcntl` (Unix/macOS — not Windows-compatible)

## License

MIT
