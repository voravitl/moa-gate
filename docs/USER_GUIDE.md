# MOA Gate + AI-DLC Compass — User Guide

คู่มือการใช้งานสำหรับผู้ใช้ Hermes Agent

---

## สารบัญ

1. [ภาพรวม](#1-ภาพรวม)
2. [MOA Gate คืออะไร](#2-moa-gate-คืออะไร)
3. [AI-DLC Compass คืออะไร](#3-ai-dlc-compass-คืออะไร)
4. [Flow การทำงาน](#4-flow-การทำงาน)
5. [การเริ่มต้นใช้งาน](#5-การเริ่มต้นใช้งาน)
6. [Slash Commands](#6-slash-commands)
7. [Steering Rules](#7-steering-rules)
8. [Phase Management](#8-phase-management)
9. [Tier System](#9-tier-system)
10. [Troubleshooting](#10-troubleshooting)
11. [FAQ](#11-faq)

---

## 1. ภาพรวม

Repo นี้มี 2 component ที่ทำงานร่วมกัน:

```
┌─ MOA Gate (plugin) ─────────────────────┐
│  🔒 Block/allow write tools             │
│  📝 HMAC-signed state + audit log       │
│  🗳️ Auto-approve via council (≥80%)     │
│  ⚖️ Tier 1 (auto) / Tier 2 (manual)    │
│  🕒 Cool-down, Shadow mode, Rate limit  │
│  📋 /moa-status, /moa-log, /moa-verify  │
└──────────────────────────────────────────┘

┌─ AI-DLC Compass (plugin) ───────────────┐
│  🧭 Development lifecycle phases         │
│  📜 Steering rules (security/arch/comp)  │
│  🚫 Block code in INCEPTION phase        │
│  🔍 Scan content for violations          │
│  ⏫ Escalate critical to MOA Gate        │
└──────────────────────────────────────────┘
```

### ช่องทางติดต่อ

- Repo: `https://github.com/voravitl/moa-gate`
- Plugin: `~/.hermes/plugins/moa-gate/`
- Wiki: `~/wiki/moa-gate/`

## 2. MOA Gate คืออะไร

MOA (Multi-Model Adviser) Gate เป็น **pre_tool_call hook** สำหรับ Hermes Agent ที่:

- **Block** write/destructive tools (`patch`, `write_file`, `terminal`, `git_commit`, ฯลฯ) จนกว่าจะได้รับอนุมัติจาก council
- **Verify** ผ่าน HMAC-SHA256 signed state ป้องกันการ bypass
- **Auto-approve** ถ้า council ≥80% และเป็น Tier 1 (non-security)
- **Weighted veto** — ถ้า Critic/Skeptic dissent → Tier 2 ต้อง manual approve ทันที
- **Audit trail** — append-only log พร้อม hash chain

### Blocked Tools

| Tool | เหตุผล |
|------|--------|
| `patch` | แก้ไขไฟล์ |
| `write_file` | เขียนหรือเขียนทับไฟล์ |
| `write` | เขียนไฟล์ |
| `git_commit` | commit การเปลี่ยนแปลง |
| `gh_pr_create` | สร้าง Pull Request |
| `skill_manage` | จัดการ Hermes skills |
| `terminal` | รัน command (ยกเว้น read-only เช่น `cat`, `ls`, `grep`) |
| `process` | จัดการ background process |

## 3. AI-DLC Compass คืออะไร

AI-DLC (AI-Driven Development Lifecycle) Compass เป็น plugin ที่ควบคุม **development lifecycle phase** และ **steering rules**:

- **Phase management**: INCEPTION → CONSTRUCTION → OPERATION
- **Steering rules**: Security (8), Architecture (5), Compliance (3)
- **Content scanning**: ตรวจ code ที่จะเขียนก่อนอนุญาต
- **Escalation**: ส่ง critical violation ไป MOA Gate

### Blocked Tools (AI-DLC)

| Tool | เหตุผล |
|------|--------|
| `patch` | แก้ไขไฟล์ |
| `write_file` | เขียนไฟล์ |
| `terminal` | รัน command |

### Phase รายละเอียด

| Phase | อนุญาตให้ทำ | Blocked |
|-------|------------|---------|
| **INCEPTION** | เขียน spec, docs, wiki, design | เขียน code ทั้งหมด |
| **CONSTRUCTION** | เขียน code, test, docs | — |
| **OPERATION** | config, deploy, monitoring | — |

## 4. Flow การทำงาน

```
[User สั่ง write/patch/terminal]
         │
         ▼
┌─ AI-DLC Compass ───────────────────┐
│ 1. Steering loaded?                 │
│    NO  → block + แจ้งให้ /ai-dlc    │
│    YES → ไปข้อ 2                    │
│                                     │
│ 2. Phase check                      │
│    INCEPTION + code? → block 🛑    │
│    CONSTRUCTION/OPERATION → go      │
│                                     │
│ 3. Content scan (steering rules)    │
│    Violation found?                 │
│      warning → warn + allow         │
│      critical → block + escalate    │
│    No violation → allow             │
└──────────┬─────────────────────────┘
           │ (allowed)
           ▼
┌─ MOA Gate ──────────────────────────┐
│ 1. Tool blocked? (check list)       │
│    NO  → allow ✅                   │
│    YES → ไปข้อ 2                    │
│                                     │
│ 2. Check state                      │
│    approved  → cool-down/shadow?    │
│    pending   → block 🛑             │
│    rejected  → block 🛑             │
│                                     │
│ 3. Session isolation                │
│    session ตรง? → allow             │
│    ไม่ตรง    → block 🛑             │
└─────────────────────────────────────┘
```

### วิธีการทำงานที่ถูกต้อง

1. **MOA Tool Mode** (primary): `/moa-adviser`
   - ใช้ `mixture_of_agents` → real 5 models (Claude, Codex, Agy, ฯลฯ)
   - ต้องมี credits API ครบ
   - Fallback: CLI mode → Cloud mode

2. **รับผล council** → ส่ง `/moa-approve --by <voices>` หรือ `/moa-council-complete`

3. เขียน code ได้ ✅

## 5. การเริ่มต้นใช้งาน

### 5.1 ติดตั้ง (ครั้งแรก)

```bash
# Clone
git clone git@github.com:voravitl/moa-gate.git ~/.hermes/plugins/moa-gate

# Symlink skill
ln -sf ~/.hermes/plugins/moa-gate/skill ~/.hermes/skills/devops/moa-adviser

# Symlink AI-DLC
ln -sf ~/.hermes/plugins/moa-gate/ai-dlc ~/.hermes/plugins/ai-dlc

# Setup state
mkdir -p ~/.hermes/moa-gate/sessions

# Setup AI-DLC
mkdir -p ~/.hermes/ai-dlc
```

### 5.2 ตั้งค่า steering rules

```bash
# Steering rules อยู่ที่ ~/wiki/steering/
# ถ้ายังไม่มี — copy จาก plugin
cp ~/.hermes/plugins/ai-dlc/steering/rules/*.yaml ~/wiki/steering/
```

### 5.3 ตั้งค่า phase

```bash
# INCEPTION = default
python3 -c "
import json
from datetime import datetime, timezone
data = {
    'phase': 'INCEPTION',
    'history': [{'from': None, 'to': 'INCEPTION', 'timestamp': datetime.now(timezone.utc).isoformat(), 'reason': 'Initial'}],
    'current_phase_start': datetime.now(timezone.utc).isoformat()
}
with open('$HOME/.hermes/ai-dlc/phase.json', 'w') as f:
    json.dump(data, f, indent=2)
"
```

## 6. Slash Commands

### MOA Gate Commands

| Command | คำอธิบาย | ตัวอย่าง |
|---------|---------|---------|
| `/moa-gate status` | ดูสถานะ gate ปัจจุบัน | `/moa-gate status` |
| `/moa-gate approve --by claude,codex --reason "refactor"` | อนุมัติ write tool ด้วยตนเอง | หลัง council เห็นชอบ |
| `/moa-gate council-complete '{"votes":{...}}'` | ส่งผล council (JSON) | รองรับ auto-approve |
| `/moa-gate revoke` | ยกเลิกอนุมัติทั้งหมด | เมื่อเปลี่ยนใจ |
| `/moa-gate log [limit]` | ดู audit log | `/moa-gate log 10` |
| `/moa-gate verify` | ตรวจสอบความถูกต้องของ state | `/moa-gate verify` |
| `/moa-gate help` | ดู help | `/moa-gate help` |

**Short form:** ใช้ `/moa-status`, `/moa-approve`, `/moa-revoke`, `/moa-log`, `/moa-verify` ได้ด้วย

### AI-DLC Commands

AI-DLC **ไม่มี** slash commands โดยตรง — ทำงานผ่าน Hermes plugin hooks อัตโนมัติ  
แต่พี่สามารถใช้ `/ai-dlc help` ถ้ามีการ register (อนาคต)

การปรับแต่งทำผ่าน:

```bash
# ดู steering rules
cat ~/wiki/steering/*.yaml

# เปลี่ยน phase
python3 -c "
from pathlib import Path
import json
p = Path.home() / '.hermes' / 'ai-dlc' / 'phase.json'
data = json.loads(p.read_text())
data['phase'] = 'CONSTRUCTION'
data['history'].append({'from': data['phase'], 'to': 'CONSTRUCTION', 'timestamp': '...', 'reason': 'Ready to code'})
p.write_text(json.dumps(data, indent=2))
"
```

## 7. Steering Rules

### Security Rules (8 rules)

| ID | คำอธิบาย | Severity |
|----|---------|----------|
| SEC-001 | ห้าม hardcode secret/password/API key | Critical |
| SEC-002 | ต้องมี input validation ทุก public endpoint | Critical |
| SEC-003 | ต้องมี authentication ทุก API endpoint (sensitive) | Critical |
| SEC-004 | ห้ามใช้ eval()/exec() | Critical |
| SEC-005 | ห้าม SQL injection | Critical |
| SEC-006 | ต้องใช้ parameterized query | Critical |
| SEC-007 | ต้องมี rate limiting | Warning |
| SEC-008 | ห้าม hardcode internal path/URL | Warning |

### Architecture Rules (5 rules)

| ID | คำอธิบาย | Severity |
|----|---------|----------|
| ARCH-001 | ต้องมี type hints / strong types | Warning |
| ARCH-002 | ห้าม circular imports | Critical |
| ARCH-003 | ต้องมี error handling (try/except/Result) | Warning |
| ARCH-004 | ห้าม magic number — ใช้ constant แทน | Warning |
| ARCH-005 | ห้าม god function (>100 lines) | Warning |

### Compliance Rules (3 rules)

| ID | คำอธิบาย | Severity |
|----|---------|----------|
| COMP-001 | ต้องมี audit log สำหรับ write operations | Warning |
| COMP-002 | ห้าม hardcode PII mock data | Critical |
| COMP-003 | ต้อง sanitize output ก่อน return | Warning |

## 8. Phase Management

### การทำงาน

AI-DLC ใช้ phase state machine: `INCEPTION` → `CONSTRUCTION` → `OPERATION`

- **INCEPTION:** ใช้ตอนเริ่ม project — เขียน spec, design, requirements เท่านั้น  
  เขียน code = blocked
- **CONSTRUCTION:** เขียน code, test, refactor ได้ตามปกติ
- **OPERATION:** deploy, config, monitoring

### การเลื่อน phase

```bash
python3 -c "
from pathlib import Path
import json
from datetime import datetime, timezone

p = Path.home() / '.hermes' / 'ai-dlc' / 'phase.json'
data = json.loads(p.read_text())

new_phase = 'CONSTRUCTION'  # หรือ 'OPERATION'
data['phase'] = new_phase
data['history'].append({
    'from': data.get('phase'),
    'to': new_phase,
    'timestamp': datetime.now(timezone.utc).isoformat(),
    'reason': 'พร้อมเขียน code'
})
data['current_phase_start'] = datetime.now(timezone.utc).isoformat()
p.write_text(json.dumps(data, indent=2))
print(f'✅ Phase changed to {new_phase}')
"
```

## 9. Tier System

MOA Gate ใช้ 2-tier classification สำหรับ council approval:

### Tier 1 (Auto-approve)

- **เงื่อนไข:** council ≥80% approve + **ไม่ใช่** security/auth/schema
- **กระทำ:** approve อัตโนมัติ ไม่ต้องรอ human
- **Cool-down:** 5 นาที (ป้องกัน abuse)

### Tier 2 (Manual only)

- **เงื่อนไข:** มี Critic/Skeptic dissent หรือ path/reason ตรง Tier 2 patterns
- **กระทำ:** ต้องรอ `/moa-approve --by human` เท่านั้น
- **Tier 2 patterns:** auth, credential, password, secret, migration, schema, billing, payment, RBAC, user data, compliance, encryption

### Auto-approve Logic

```
1. Count votes: approve vs dissent
2. ≥80% approve? → ไป check Tier
3. Tier 1 → auto-approve ✅ + cool-down 5 นาที
4. Tier 2 → block ⛔ รอ manual
5. <80% → rejected ❌
6. Critic/Skeptic dissent any? → force Tier 2
```

## 10. Troubleshooting

### "MOA Gate: Write tool blocked — MOA council approval required"

**สาเหตุ:** ยังไม่ได้รับอนุมัติจาก council  

**วิธีแก้:**
```bash
# 1. รัน council
/moa-adviser --voices 5

# 2. ส่งผล council
/moa-council-complete '{"votes": {"results": {...}}}'
```

---

### "MOA Gate: Cool-down active"

**สาเหตุ:** เพิ่ง auto-approve ไป ต้องรอ cool-down 5 นาที  

**วิธีแก้:**
```bash
# รอ cool-down หมด หรือ override
/moa-approve --override --reason "ต้องแก้ด่วน"
```

---

### "AI-DLC PHASE BLOCK: Still in INCEPTION phase"

**สาเหตุ:** กำลังเขียน code ใน INCEPTION phase  

**วิธีแก้:**
```bash
# 1. เลื่อน phase ไป CONSTRUCTION (ดูหัวข้อ 8)
# 2. หรือเขียน spec/design ก่อน (ไม่ถูก block)
```

---

### "Session mismatch" / State จาก session อื่น

**สาเหตุ:** การอนุมัติถูกสร้างจาก session อื่น  

**วิธีแก้:**
```bash
/moa-revoke
# แล้ว approve ใหม่ใน session ปัจจุบัน
```

---

### Test ไม่ผ่าน

```bash
cd ~/moa-gate
python3 -m pytest tests/ -v
```

ถ้ายังไม่ผ่าน — ลบ `.pytest_cache` และ `__pycache__`:
```bash
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null
```

## 11. FAQ

**Q: MOA Gate กับ AI-DLC ต่างกันยังไง?**  
A: MOA Gate = อนุมัติ write tools (allow/block)  
   AI-DLC = ควบคุม lifecycle phase + steering compliance  
   ทำงานร่วมกัน: AI-DLC ตรวจก่อน → MOA Gate ตรวจทีหลัง

**Q: เขียน docs และ wiki ต้องขออนุมัติไหม?**  
A: ต้อง — `write_file` อยู่ใน blocked list ทุกกรณี  
   แต่ `patch` เฉพาะ MOA Gate ที่ตรวจ ส่วน AI-DLC ตรวจ content ด้วย

**Q: ปิด MOA Gate ได้ไหม**  
A: ถ้าเป็น production environment ไม่แนะนำ  
   แต่สามารถ `/moa-revoke` เพื่อ reset state แล้ว approve ใหม่ได้

**Q: เพิ่ม steering rules ได้ไหม**  
A: ได้ — แก้ไขไฟล์ YAML ที่ `~/wiki/steering/*.yaml`  
   AI-DLC จะโหลดใหม่ทุกครั้งที่ตรวจ

**Q: เปลี่ยน phase กลับไป INCEPTION ได้ไหม**  
A: ได้ — แก้ `phase.json` โดยตรง
