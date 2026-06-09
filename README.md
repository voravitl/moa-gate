# MOA Gate + AI-DLC Compass — Hermes Plugin + Skill

Multi-Model Adviser (MOA) enforcement gate + AI-Driven Development Lifecycle Compass for Hermes Agent.

รวม 2 component ใน repo เดียว:

| Component | Path | หน้าที่ |
|-----------|------|--------|
| **MOA-Gate Plugin** | `__init__.py` + `state.py` + `audit.py` + `tier.py` | 🔒 Block/unblock write tools, HMAC-signed state, audit log |
| **AI-DLC Compass Plugin** | `ai-dlc/` | 🧭 Development lifecycle phase + steering rules compliance |
| **MOA Multi-Model Plugin** | `moa-multimodel/` | 🛡️ Runs 3 real models (Claude + Codex + AGY) as adversarial voices, writes to moa-gate state |
| **Skill** `moa-adviser` | `skill/SKILL.md` | 🧠 เรียก multi-model council เพื่อตัดสินใจ |

---

## Architecture

```
User wants to write code
         │
         ▼
┌─ AI-DLC Compass (ai-dlc/) ─────────┐
│  Phase check?                       │
│  Steering compliance?               │
│  Content scan?                      │
└──────────┬─────────────────────────┘
           │ allowed
           ▼
┌─ MOA Gate (root __init__.py) ──────┐
│  Council approved?  →  approve     │
│  Pending?           →  block       │
│  Cool-down active?  →  block       │
│  Session mismatch?  →  block       │
└──────────────────┬─────────────────┘
                   │
                   ▼
         Write tool executes ✅
```

---

## Files

### MOA Gate (root `moa-gate/`)

| File | Purpose |
|------|---------|
| `__init__.py` | Plugin entry + pre_tool_call hook + slash commands |
| `state.py` | HMAC-SHA256 signed state + TTL + auto-approve + session GC |
| `audit.py` | Append-only audit log with SHA-256 hash chain |
| `tier.py` | Tier classification (T1 auto / T2 manual) |
| `plugin.yaml` | Hermes plugin manifest |
| `pyproject.toml` | Project config (Python deps) |

### AI-DLC (`ai-dlc/`)

| File | Purpose |
|------|---------|
| `ai-dlc/__init__.py` | Plugin entry + pre_tool_call hook |
| `ai-dlc/engine/phase.py` | Phase state machine (INCEPTION → CONSTRUCTION → OPERATION) |
| `ai-dlc/engine/verifier.py` | Content scanner — match/require/deny patterns |
| `ai-dlc/steering/registry.py` | Load YAML rules from `~/wiki/steering/` |
| `ai-dlc/steering/rules/security.yaml` | 8 security rules |
| `ai-dlc/steering/rules/architecture.yaml` | 5 architecture rules |
| `ai-dlc/steering/rules/compliance.yaml` | 3 compliance rules |
| `ai-dlc/plugin.yaml` | Hermes plugin manifest |

### Documentation

| File | Purpose |
|------|---------|
| `docs/USER_GUIDE.md` | คู่มือผู้ใช้ฉบับเต็ม |
| `docs/COMMANDS.md` | Slash command reference |
| `README.md` | เอกสารนี้ |
| `skill/SKILL.md` | MOA Adviser Council setup + CLI/Cloud mode |
| `skill/references/` | Technical reference docs |

### Tests

| File | Purpose |
|------|---------|
| `tests/test_ai_dlc_compass.py` | 9 AI-DLC integration tests |

---

## Installation

### One-shot (AI-friendly)

```bash
bash <(curl -sL https://raw.githubusercontent.com/voravitl/moa-gate/main/scripts/install.sh)
```

### Manual

```bash
# Clone
git clone git@github.com:voravitl/moa-gate.git ~/.hermes/plugins/moa-gate

# Skill
ln -sf ~/.hermes/plugins/moa-gate/skill ~/.hermes/skills/devops/moa-adviser

# AI-DLC plugin
ln -sf ~/.hermes/plugins/moa-gate/ai-dlc ~/.hermes/plugins/ai-dlc

# Steering rules
mkdir -p ~/wiki/steering
cp ~/.hermes/plugins/ai-dlc/steering/rules/*.yaml ~/wiki/steering/

# State directory
mkdir -p ~/.hermes/moa-gate/sessions
mkdir -p ~/.hermes/ai-dlc
```

---

## Quick Start

### 1. ตรวจสอบว่าทำงาน

```bash
cd ~/moa-gate
python3 -m pytest tests/ -v
# ควรได้ 9/9 PASS
```

### 2. Slash commands

```
/moa-gate status          → ดูสถานะ
/moa-gate council-complete  → ส่งผล council
/moa-emergency              → bypass ฉุกเฉิน (ต้องมี --reason)
/moa-revoke                 → ยกเลิกอนุมัติ
/moa-log                    → ดู audit log
/moa-verify                 → ตรวจ state
```

### 3. เริ่มเขียน code

```bash
# Step 1: รัน council
/moa-adviser --voices 5

# Step 2: ส่งผล (auto-approve ถ้า ≥80%)
/moa-council-complete '{"votes":{...}}'

# Step 3: เขียน code ได้เลย 🎯
```

ดูเพิ่มเติม: [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | [docs/COMMANDS.md](docs/COMMANDS.md)

---

## Development

```bash
# Test
python3 -m pytest tests/ -v

# Build
python3 -m py_compile __init__.py && echo "✅ OK"
```

### CI (GitHub Actions)

| Job | What it does |
|-----|-------------|
| `lint` | Python lint + type check |
| `test` | Python tests (9 AI-DLC tests) |
| `moa-gate` | MOA quorum verification |

---

## See Also

- [docs/USER_GUIDE.md](docs/USER_GUIDE.md) — คู่มือผู้ใช้ฉบับเต็ม
- [docs/COMMANDS.md](docs/COMMANDS.md) — Slash command reference
- [skill/SKILL.md](skill/SKILL.md) — MOA Adviser setup
- [ai-dlc/README.md](ai-dlc/README.md) — AI-DLC details
