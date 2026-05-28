# Ollama Cloud MOA — 5 Models, Real Diversity

## Architecture

```
┌ Question ──────────────────────────────────┐
│                                            │
├─ 🧠 Architect    → deepseek-v4-pro:cloud ──┤
├─ 📐 Strategist   → glm-5.1:cloud ──────────┤
├─ 🔍 Critic       → mistral-large-3:675b ───┤  ← 5 parallel API calls
├─ 🏃 Pragmatist   → kimi-k2.6:cloud ────────┤
├─ 🤨 Skeptic      → qwen3.5:cloud ──────────┤
│                                            │
└──────────┬──────────────────────────────────┘
           ▼
      Synthesize → Final Verdict
```

**Note:** `delegate_task` does NOT support per-voice model/provider.
Use **direct Ollama API** (python script or curl) for real model diversity.

---

## Model → Voice Mapping

| Voice | Model | Why this model |
|:------|:------|:---------------|
| 🧠 Architect | `deepseek-v4-pro:cloud` | Strongest reasoning, CoT, deep analysis |
| 📐 Strategist | `glm-5.1:cloud` | Leverages Chinese training data for structural thinking |
| 🔍 Critic | `mistral-large-3:675b-cloud` | Crisp logic, systematic risk enumeration |
| 🏃 Pragmatist | `kimi-k2.6:cloud` | Long context, practical real-world estimation |
| 🤨 Skeptic | `qwen3.5:cloud` | Nuanced edge-case reasoning, counter-factual |

**Diversity guarantee:** 5 different model families — DeepSeek, GLM, Mistral, Kimi, Qwen.
Each has unique training data, architecture, and reasoning style.

---

## 5 Role Prompts (Improved)

### 1. 🧠 Architect — deepseek-v4-pro:cloud

```
คุณคือ System Architect ผู้เชี่ยวชาญด้าน Distributed Systems และ Enterprise Architecture
จงใช้ Chain-of-Thought (CoT) วิเคราะห์ข้อเสนอนี้อย่างลึกซึ้งในระดับโครงสร้างระบบ

{question}

โฟกัสที่:
- Component Decoupling และ Scalability Bottleneck
- Data Flow และ Integration-level issues
- Architectural trade-offs ระหว่างของเดิมกับข้อเสนอใหม่
- ระบบ Dependency และจุดเปราะบาง

ตอบในรูปแบบ Markdown:
### Position
[เห็นด้วย/ไม่เห็นด้วย 1-2 ประโยค]

### Key Points
- point 1
- point 2
- point 3

### Risk / Caveat
[1 ข้อ]
```

### 2. 📐 Strategist — glm-5.1:cloud

```
คุณคือ Tech Strategist ผู้เชี่ยวชาญการวางกลยุทธ์มหภาคและ Ecosystem Synergy

{question}

วิเคราะห์โดยเชื่อมโยงกับ:
- Strategic Positioning และ Platform Business Models
- ผลกระทบระยะยาวต่อ Core Competency และ Market Expansion
- การใช้ทรัพยากรและการสร้างพันธมิตร
- โอกาสจาก Network Effects และการเจาะตลาด

ตอบในรูปแบบ Markdown:
### Position
[เห็นด้วย/ไม่เห็นด้วย 1-2 ประโยค]

### Key Points
- point 1
- point 2
- point 3

### Risk / Caveat
[1 ข้อ]
```

### 3. 🔍 Critic — mistral-large-3:675b-cloud

```
คุณคือ Senior Code & Architecture Critic ผู้มีหน้าที่จับผิดและตรวจสอบคุณภาพอย่างเข้มงวด
ใช้ First-principles Reasoning และ Logical consistency วิเคราะห์

{question}

จำแนกตาม:
- ช่องโหว่ความล้มเหลว (Single Point of Failure)
- Logic flaws และ Security/Reliability risks
- Over-engineering และ Principle violations
- การขัดกันของ Clean Code กับ Performance

ตอบในรูปแบบ Markdown:
### Position
[เห็นด้วย/ไม่เห็นด้วย 1-2 ประโยค]

### Key Points
- point 1
- point 2
- point 3

### Risk / Caveat
[1 ข้อ]
```

### 4. 🏃 Pragmatist — kimi-k2.6:cloud

```
คุณคือ Pragmatic Engineer และ Technical Project Manager ที่เน้นผลลัพธ์จับต้องได้จริง

{question}

ประเมิน:
- Resource Constraints, Time-to-market, Dev Effort
- ผลกระทบต่อ Legacy Code, Migration Cost, Technical Debt
- Rollout/Rollback feasibility
- Incremental Delivery approach — เริ่มตรงไหนได้ทันที?

ตอบในรูปแบบ Markdown:
### Position
[เห็นด้วย/ไม่เห็นด้วย 1-2 ประโยค]

### Key Points
- point 1
- point 2
- point 3

### Risk / Caveat
[1 ข้อ]
```

### 5. 🤨 Skeptic — qwen3.5:cloud

```
คุณคือ Skeptical Consultant — Devil's Advocate ที่ท้าทายทุกสมมติฐาน

{question}

มองในมุม:
- Edge Cases ที่ไม่มีใครนึกถึง
- Counter-factual: ถ้าไม่ทำ หรือเลือกทางตรงข้าม?
- Unintended Consequences และ User Behavior ที่ขัดแย้ง
- Tech Buzzwords หรือแก้ปัญหาถูกจุด?

ตอบในรูปแบบ Markdown:
### Position
[เห็นด้วย/ไม่เห็นด้วย 1-2 ประโยค]

### Key Points
- point 1
- point 2
- point 3

### Risk / Caveat
[1 ข้อ]
```

---

## Execution: 5 Models via Ollama API

Since `delegate_task` cannot set per-voice models, use direct API calls:

### Method 1: Python script (recommended)

Script: `~/.hermes/scripts/moa-ollama.py`

```python
"""Parallel 5-model MoA via Ollama Cloud API."""
import asyncio, json, sys
from openai import AsyncOpenAI

client = AsyncOpenAI(base_url="http://127.0.0.1:11434/v1", api_key="ollama")

VOICES = {
    "architect":   {"model": "deepseek-v4-pro:cloud",       "prompt": "..."},
    "strategist":  {"model": "glm-5.1:cloud",              "prompt": "..."},
    "critic":      {"model": "mistral-large-3:675b-cloud", "prompt": "..."},
    "pragmatist":  {"model": "kimi-k2.6:cloud",           "prompt": "..."},
    "skeptic":     {"model": "qwen3.5:cloud",              "prompt": "..."},
}

async def call_voice(voice: str, cfg: dict, question: str):
    messages = [{"role": "user", "content": cfg["prompt"].format(question=question)}]
    resp = await client.chat.completions.create(
        model=cfg["model"], messages=messages, max_tokens=1024, temperature=0.7
    )
    return voice, resp.choices[0].message.content

async def main():
    question = sys.argv[1]
    tasks = [call_voice(v, c, question) for v, c in VOICES.items()]
    results = await asyncio.gather(*tasks)
    for voice, text in results:
        print(f"\n### {voice.upper()}\n{text}")

asyncio.run(main())
```

### Method 2: curl (quick ad-hoc)

```bash
for voice in architect strategist critic pragmatist skeptic; do
  case $voice in
    architect)  model="deepseek-v4-pro:cloud";;
    strategist) model="glm-5.1:cloud";;
    critic)     model="mistral-large-3:675b-cloud";;
    pragmatist) model="kimi-k2.6:cloud";;
    skeptic)    model="qwen3.5:cloud";;
  esac
  echo "=== $voice ($model) ==="
  curl -s http://127.0.0.1:11434/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"$model\",\"messages\":[{\"role\":\"user\",\"content\":\"PROMPT_HERE\"}],\"max_tokens\":1024}" | \
    python3 -c "import sys,json; print(json.load(sys.stdin)['choices'][0]['message']['content'])"
  echo ""
done
```

---

## ปรับแต่งตามประเภทคำถาม

| คำถามประเภท | Architect | Strategist | Critic | Pragmatist | Skeptic |
|-------------|:--------:|:----------:|:------:|:----------:|:-------:|
| Architecture / Design | 🔥 focus | ปรกติ | ปรกติ | ปรกติ | ปรกติ |
| Security / Risk | ปรกติ | ปรกติ | 🔥 focus | ปรกติ | 🔥 focus |
| Roadmap / Plan | ปรกติ | 🔥 focus | ปรกติ | 🔥 focus | ปรกติ |
| Code Review | ปรกติ | - | 🔥 focus | ปรกติ | 🔥 focus |
| Cost / Budget | - | ปรกติ | 🔥 focus | 🔥 focus | ปรกติ |
| Migration / Upgrade | 🔥 focus | 🔥 focus | 🔥 focus | 🔥 focus | ปรกติ |

> 🔥 = เพิ่มน้ำหนัก prompt / ปรกติ = template มาตรฐาน / - = ไม่จำเป็น

---

## Pitfalls

| Pitfall | Fix |
|---------|-----|
| **delegate_task CANNOT set model/provider** | ใช้ direct API call (Python/curl) แทน |
| **Subagent ไม่มี context** | ใส่ context + data เต็มใน prompt |
| **Cold start latency** | 5 models parallel → ~30-60s แรก, เร็วกว่าถัดไป |
| **Model หาย/error** | fallback: skip voice + แจ้ง user |
| **ภาษา mismatch** | prompt ระบุ `ตอบภาษาไทย` เสมอ |
| **Output format ไม่อ่าน** | ใช้ `###` heading + bullet ที่ชัดเจน |
| **Context token burn** | 5 models → context ซ้ำกัน trim เฉพาะที่จำเป็น |
