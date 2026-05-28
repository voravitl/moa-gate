---
name: moa-adviser
description: "Multi-Model Adviser Council — hard decisions via real diverse models. Uses mixture_of_agents (5 models) when credits available, CLI mode (claude/codex/agy = 3 models) for sensitive data, Cloud delegate_task (same-model multi-prompt) as last resort."
---

# MOA Adviser Council

Multi-model decision council using **real diverse models**.

---

## ⚡ Mode Decision Tree

```
┌ คำถาม ───────────────────────────┐
│ sensitive/risk data?              │
└──────────┬───────────────────────┘
           ▼
      ┌─────────┐
      │ Yes     │──→ ใช้เฉพาะ CLI mode (claude + agy)
      │         │     ❌ ห้ามส่ง cloud/API
      └─────────┘
           │ No
           ▼
      ┌───────────────┐
      │ mixture_of_   │   real 5 models ต่างบริษัทกัน
      │ agents tool   │   (ต้องมี credits — ถ้า 402 → fallback)
      │ พร้อม?        │
      └───────┬───────┘
              ▼
         ┌─────────┐
         │ Yes     │──→ 🎯 MOA Tool Mode (PRIMARY)
         │         │     real 5 models (ต่าง API key/config)
         │         │     → success? → synthesize
         │         │     → 402/timeout? → CLI fallback
         └─────────┘
              │ No
              ▼
         ┌───────────┐
         │ CLI tools │   which claude + codex + agy
         │ พร้อม?    │
         └─────┬─────┘
              ▼
         ┌─────────┐
         │ Yes     │──→ ⚡ CLI Mode
         │         │     real 3 models (ต่างบริษัท)
         │         │     → success? → synthesize
         │         │     → timeout? → Cloud fallback
         └─────────┘
              │ No
              ▼
         ☁️ Cloud Mode — delegate_task (LAST RESORT)
           ⚠️ ทุก voice = model เดียวกัน (session model)
           diversity มาจาก prompt engineering เท่านั้น
           แสดงคำเตือนใน verdict เสมอ
```

### 🎯 MOA Tool Mode (PRIMARY)

ใช้ `mixture_of_agents` tool → real 5 models ต่าง API key/บริษัท:

```python
result = mixture_of_agents(user_prompt=question)
```

| รายการ | รายละเอียด |
|:-------|:-----------|
| **Output** | Retry จนกว่าจะได้ 5 voices → Hermes สรุป verdict |
| **Diversity** | ✅ **สูงสุด** — 5 models ต่างบริษัท |
| **Credit cost** | 5 API calls |
| **Fallback** | 402/no credits → CLI mode → Cloud mode |

**⚠️ ข้อจำกัด:** `mixture_of_agents` ให้ **single synthesized output** — ไม่ได้แยกแต่ละ voice
→ Hermes ต้องแยกบทบาทจาก context ใน output (tool เก่งพอที่จะตอบตามบทบาทที่กำหนด)
→ ถ้าต้องการแยก voice ชัดเจน (Architect vs Critic ต่างคนต่างตอบ) → ใช้ **CLI Mode**

### ⚡ CLI Mode

```
┌─ คำถาม ─┐
     │
     ├── claude -p (Architect) ──┐
     ├── codex exec (Pragmatist) ─┤
     └── agy -p (Skeptic) ───────┘
              │
              ▼
       Hermes synth → verdict
```

| รายการ | รายละเอียด |
|:-------|:-----------|
| **Models** | claude (Anthropic) + codex (OpenAI) + agy (Google) = 3 บริษัทต่างกัน |
| **Diversity** | ✅ **สูง** — 3 models ต่าง architecture กัน |
| **ข้อดี** | ได้แยกแต่ละ voice (3 terminal process ต่างกันตอบคนละ round) |
| **Fallback** | ถ้า tool ไหน timeout/crash → ตัดออก แล้วใช้ Cloud เสริม |

**Paradox:** CLI mode มี **2 models ที่มี** (claude + agy) → ได้แค่ 3-4 voices
→ ถ้าต้องการ 5 voices → ต้อง `--voices 3` หรือผสมกับ Cloud (`--voices 3+2`)

### ☁️ Cloud Mode (delegate_task) — LAST RESORT

ใช้เมื่อ:
- `mixture_of_agents` tool ไม่พร้อม (402/rate limit)
- CLI tools ไม่พร้อม

⚠️ **เข้าใจข้อจำกัด:** `delegate_task` **ไม่รองรับ `model`/`provider` parameter** — schema มีแค่ `goal`, `context`, `toolsets`, `acp_command`, `acp_args`, `role`
→ 5 voices = same model, different prompt
→ diversity จาก **prompt engineering เท่านั้น**
→ **ไม่ใช่ real model diversity**
→ verdict ต้องมี Warning เสมอว่า "same-model council"
→ แนะนำ user ให้ setup CLI tools หรือเติม credits

ใช้ `delegate_task` ยิง 5 prompts ต่างกัน (ผ่าน session model เดียว):

| # | Role | Context Prompt หลัก |
|:--|:-----|:--------------------|
| 1 | 🧠 **Architect** | โครงสร้าง, trade-offs, scalability |
| 2 | 🔍 **Critic** | ความเสี่ยง, blind spots, failure modes |
| 3 | 📐 **Strategist** | roadmap, prioritization, resource |
| 4 | 🏃 **Pragmatist** | feasibility, timeline, implementation |
| 5 | 🤨 **Skeptic** | challenge assumptions, counter-arguments |

> ⚠️ `delegate_task` ใช้ model/provider เดียวกับ session — ทุก voice ได้ model เดียวกัน
> ความต่างของแต่ละ voice = prompt engineering เท่านั้น, ไม่ใช่ model architecture ที่ต่างกัน

**Execution: Round 1 (3 parallel) → Round 2 (2 sequential)**

```python
# Round 1: 3 strongest (parallel)
delegate_task(
    tasks=[
        {"goal": "คุณคือ Architect — มองโครงสร้างระยะยาว...\nวิเคราะห์: {question}\nตอบสั้น 3-5 บรรทัด เป็นภาษาไทย"},
        {"goal": "คุณคือ Critic — หาจุดอ่อน...\nวิเคราะห์: {question}\nตอบสั้น 3-5 บรรทัด เป็นภาษาไทย"},
        {"goal": "คุณคือ Strategist — วางแผน...\nวิเคราะห์: {question}\nตอบสั้น 3-5 บรรทัด เป็นภาษาไทย"},
    ],
)

# Round 2: 2 reviewers (sequential — ใช้ผล round 1)
pragmatist = delegate_task(goal="คุณคือ Pragmatist...\nผลรอบ1: {result_round1}\n{question}")
skeptic = delegate_task(goal="คุณคือ Skeptic...\nผลรอบ1: {result_round1}\nผล Pragmatist: {pragmatist}\n{question}")
```

**ใน verdict** แสดง Warning นี้:
```
⚠️ WARNING: Cloud Mode — council ใช้ model เดียวกัน (glm-5.1:cloud)
   ความหลากหลายจาก prompt engineering เท่านั้น
   ไม่ใช่ real model diversity (Architect/OpenAI vs Critic/Google)
   → ควรติดตั้ง CLI tools หรือเติม credits เพื่อ real diversity
```

---

## 🏗️ Voice Architecture

### The 5 Voices

| # | Voice | Role | Priority |
|:--|:------|:-----|:---------|
| 1 | 🧠 **Architect** | โครงสร้าง, trade-offs, scale | Top-down vision |
| 2 | 🔍 **Critic** | failure modes, blind spots | Safety/risk |
| 3 | 📐 **Strategist** | roadmap, priority, resource | Sequencing |
| 4 | 🏃 **Pragmatist** | feasibility, timeline, cost | Ground truth |
| 5 | 🤨 **Skeptic** | challenge assumptions | Devil's advocate |

**Flow:**
```
Architect ──→ initial design
   ↓
Critic ─────→ tear it apart
   ↓
Strategist ─→ sequencing
   ↓
Pragmatist ─→ can we build this?
   ↓
Skeptic ────→ why NOT?
```

---

## 🔧 Execution

### Generic Flow

ใช้ Hermes delegation paradigm:

```
1️⃣ Hermes รับ question → ตัดสินใจเลือก mode
   ├── sensitive? → CLI mode (local only)
   ├── credits OK? → MOA Tool mode (5 models)
   ├── CLI tools ready? → CLI mode (3 models)
   └── else → Cloud mode (same-model, with warning)

2️⃣ Run voices (ตาม mode ที่เลือก)

3️⃣ Hermes synthesize (not a sixth voice — purely editorial)

4️⃣ Output verdict (console + save to wiki)
```

### ⚡ Execution Config

| Config | CLI Mode | Cloud Mode | MOA Tool Mode |
|:-------|:---------|:------------|:--------------|
| **Voices** | 3 default (มี claude+codex+agy) | 5 | 5 |
| **--voices** | `3` = claude+codex+agy only; `5` = +cloud เสริม | `5` เสมอ | 5 เสมอ |
| **--timeout** | `30s` ต่อ tool (default) | 120s รวม | N/A |
| **Models** | Real 3 บริษัทต่างกัน | Same (session model) | Real 5 models |

---

## 📋 Mode Comparison

| Mode | Real Diversity | Speed | Credit Cost | Sensitive Data |
|:-----|:--------------|:------|:-----------|:---------------|
| **🎯 MOA Tool** | ✅ 5 models ต่างบริษัท | กลาง (5 calls) | 5x | ❌ ใช้ API |
| **⚡ CLI** | ✅ 3 models ต่างบริษัท | ช้า (3 terminals) | 3x local | ✅ 100% local |
| **☁️ Cloud** | ❌ same model | เร็ว (parallel) | 5x subagent | ❌ ใช้ API |

---

## ⚙️ Workflow Steps

### Step 1: Import / Reload Skill

```bash
bash <(curl -sL https://raw.githubusercontent.com/voravitl/moa-gate/main/scripts/install.sh)
```

แล้วเรียก command นี้ใน Hermes:
- `/moa-adviser` — เปิด council 5 voice

### Step 2: Choose Mode

```python
from hermes_tools import terminal, delegate_task
import json

question = "..."

# ── 1) TRY MOA Tool mode first ────────────────────────────────────
try:
    result = mixture_of_agents(user_prompt=build_prompt(question, 5_models=True))
    print("🎯 MOA Tool mode — OK")
except:
    print("⚠️ MOA Tool fallback → CLI/Cloud")

# ── 2) CLI mode ────────────────────────────────────────────────────
def run_cli_voice(voice: str, role: str, model: str) -> str:
    """Run one CLI voice"""
    cmd = f"echo \"{build_prompt(question, voice)}\" | agy -p --dangerously-skip-permissions"
    return terminal(cmd, timeout=60)["output"]
```

### Step 3: Synthesize Verdict

```python
synthesis = f"""
## MOA Council: {topic}

### Voice 1 — {model_1} (CLI:claude -p) (Architect 🧠)
{architect_output}

### Voice 2 — {model_2} (CLI:codex exec) (Critic 🔍)
{critic_output}

...

### Verdict
- **Consensus:** {consensus}
- **Strongest dissent:** {dissent}
- **Premise check:** {premise_check}
- **Recommendation:** {recommendation}
- **Missing voices:** {missing}
"""
```

### Step 4: Save + Execute

```bash
# Save to wiki
mkdir -p ~/wiki/lyn/moa-adviser
echo "{verdict}" > ~/wiki/lyn/moa-adviser/$(date +%Y-%m-%d)-{slug}.md

# Auto-approve (ถ้าเป็น council decision)
/moa-approve --by "Architect,Strategist,Pragmatist" --reason "{topic}: {recommendation}"
```

---

## 📐 Voice Prompt Templates

| Voice | Prompt Template |
|:------|:----------------|
| 🧠 **Architect** | `"คุณคือ Principal Architect ที่มองโครงสร้างระยะยาว... วิเคราะห์: {question}"` |
| 🔍 **Critic** | `"คุณคือ Security/QA Lead ที่ต้องหา failure modes... อย่าใจดี: {question}"` |
| 📐 **Strategist** | `"คุณคือ Engineering Director ที่ต้อง prioritize... วางแผน: {question}"` |
| 🏃 **Pragmatist** | `"คุณคือ Tech Lead ที่ต้อง deliver จริง...  feasibility: {question}"` |
| 🤨 **Skeptic** | `"คุณคือ Devil's Advocate — challenge ทุก assumption... {question}"` |

---

## 🔍 File Analysis Mode

ใช้ตรวจสอบไฟล์จริง: ส่ง file path ใน prompt ให้ CLI/subagent อ่านเอง

```bash
claude -p "อ่าน /path/file... วิเคราะห์..." --max-turns 3 --allowedTools "Read"
echo "อ่าน /path/file... วิเคราะห์..." | codex exec --sandbox read-only --skip-git-repo-check
agy -p "อ่าน /path/file... วิเคราะห์..." --dangerously-skip-permissions
```

**Pitfalls:** อย่าส่ง summary แทนของจริง, claude ต้อง --max-turns 3, ถ้าไฟล์ >500 บรรทัดให้อ่านเฉพาะส่วนที่เกี่ยวข้อง

---

## 🎯 5th Voice Meta-Reviewer

Optional — หลัง council สังเคราะห์ verdict เรียบร้อย:

```python
# 5th voice reviews consolidated report
agy -p "คุณคือ Reviewer ตรวจ analysis นี้..." --dangerously-skip-permissions
# หรือ delegate_task (same model, different prompt)
delegate_task(goal="Review verdict...")
```

**Pitfall:** ต้องส่ง **synthesized report** ไม่ใช่ raw outputs

---

## Verdict Format

```
## MOA Council: [หัวข้อ]

### Voice 1 — [Model/Source] ([บทบาท])
[position + เหตุผล]

### Voice 2 — [Model/Source] ([บทบาท])
...

### Verdict
- **Consensus:** [เห็นตรงกันตรงไหน]
- **Strongest dissent:** [ความเห็นต่าง]
- **Premise check:** [คำถามถูกต้องไหม?]
- **Recommendation:** [ทางเลือกที่ดีที่สุด]
- **Missing voices:** [ถ้ามีการ fallback — แจ้ง user]
```

### Voice Label Guidelines

**Format:** `Voice N — <model> (<source>) (<role>)`

| Source | Label | Example |
|:-------|:------|:--------|
| MOA Tool mode | `MOA:<model>` | `Voice 1 — claude-sonnet-4 (MOA:mixture_of_agents) (Architect 🧠)` |
| CLI mode (claude/codex/agy) | `CLI:<tool>` | `Voice 1 — opus (CLI:claude -p) (Architect 🧠)` |
| Cloud delegate_task | `subagent:<model>` | `Voice 2 — glm-5.1:cloud (subagent:delegate_task) (Critic 🔍)` |

**Rule:** ต้องระบุ model name + source เสมอ — ห้ามตัด part model ออก

**CLI Mode Example:**
```
### Voice 1 — claude-opus-4 (CLI:claude -p --model opus) (Architect 🧠)
TTL 15 นาทีถูกแล้ว — deterministic safety net ที่ root

### Voice 2 — gpt-5.5 (CLI:codex exec) (Critic 🔍)
on_session_end เสี่ยง state leak ถ้า Hermes crash → TTL เป็น hedge
```

**Cloud Mode Example (มี Warning):**
```
⚠️ CLOUD MODE WARNING — ทุก voice ใช้ model เดียวกัน (glm-5.1:cloud)
   diversity จาก prompt engineering เท่านั้น ไม่ใช่ real model diversity
   ควรติดตั้ง CLI tools หรือเติม credits เพื่อ diversity จริง

### Voice 1 — glm-5.1:cloud (subagent:delegate_task) (Architect 🧠)
...

### Voice 2 — glm-5.1:cloud (subagent:delegate_task) (Critic 🔍)
...
```

---

## Save & Resume

- Path: `~/wiki/lyn/moa-adviser/<YYYY-MM-DD>-<title-slug>.md`
- Naming: date-first เพื่อ sort, kebab case สำหรับ title
- Content: เก็บ verdict + argument summaries + ข้อควรระวัง
- Retention: useful verdicts (non-obvious) เท่านั้น — ไม่ต้องเก็บ trivial

---

## 🔁 Rollback

กรณี council decision ผิด → rollback steps:
1. `git revert` (ถ้า code change)
2. `/moa-adviser` กับ question ที่บอก failure context
3. แก้ + commit ใหม่
