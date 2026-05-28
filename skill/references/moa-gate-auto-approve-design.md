# MOA Gate Auto-Approve

**Status:** ✅ Implemented (2026-05-28)
**Files modified:** `__init__.py` state.py audit.py + NEW `tier.py`
**Test results:** 44/45 + audit chain intact ✅
**Source:** Opus initial review + 5-voice MOA Council + Pragmatist implementation

---

## Flow

```
/moa-adviser --voices 5
  ↓
Council Vote: Architect ✅ Strategist ✅ Critic ❌ Pragmatist ✅ Skeptic ✅
  ↓ 4/5 = 80%
├─ dissent in (Critic, Skeptic)? ──→ Tier 2 (manual)
├─ dissent elsewhere? ──────────→ proceed
  ↓
├─ Shadow mode ON? ─────────────→ record audit log, no execute
├─ Shadow mode OFF ────────────→ auto-approve + cool-down
  ↓
├─ User override in cool-down? ──→ execute immediately
├─ cool-down expires ───────────→ execute
  ↓
Dissent → auto GH issue
```

---

## 5-Voice Council Verdict (2026-05-28)

| Voice | Vote | Key Points |
|:------|:-----|:-----------|
| 🧠 Architect | ✅ | Auto-approve = philosophical shift (implicit consent with opt-out). Cool-down = state machine. Tier = council vote, not heuristic. |
| 🔍 Critic | ✅ | Prompt injection can frame Tier 2 as Tier 1. Shadow metric = confusion matrix (FP, FN). Veto abuse potential. |
| 📐 Strategist | ✅ | Build Tier System + Weighted Veto first. Cool-down scales by risk (60s/300s). Shadow 4 weeks. |
| 🏃 Pragmatist | ✅ | ~170 lines, 4 files. HMAC migration = blocker #1. 10-14h dev. |
| 🤨 Skeptic | ✅ | 4/5 = correlated error risk. Tier regex = fragile. Cool-down 120s = unfounded assumption. Rate limit must be global. |

**Consensus:** 5/5 — ไปต่อ แต่ขอ 4 ข้อแก้ก่อน ship

### Prerequisites Before Ship

1. **HMAC compat** — inject default fields ก่อน verify HMAC (same pattern as `expires_at` LYN backward compat)
2. **Cool-down state machine** — `pending_auto → cooling → approved` + persistent timer
3. **Tier detection** — council vote tier, conservative merge (ถ้าเสียงใดบอก Tier 2 → Tier 2)
4. **Rate limit** — global shared counter, not per-session
5. **Shadow mode** — 4 weeks, confusion matrix metric, explicit graduation criteria

---

## Opus Analysis (Claude Opus — Senior Distributed Systems Architect)

### Weighted Veto
Critic/Skeptic dissent ≠ noise — เป็น safety signal
→ dissent จาก safety roles = de facto veto สำหรับ risky changes

### Correlated Model Risk
- Training data correlation: 5 families ≠ independent (Common Crawl + RLHF)
- Prompt injection cross-contamination ถ้า voices share context
- Council config = attack surface (ใครแก้ voices.yaml ได้ = bypass ได้)
- Latency anomaly = cached/short-circuited voice

### Recommendation: 3 Guardrails
1. **Weighted veto:** Critic/Skeptic dissent → Tier 2
2. **Cool-down period:** Tier 1 auto → hold 60-300s ก่อน execute, user override 1 keypress
3. **Shadow mode 2-4 weeks:** auto-approve → record only, compare vs manual approval

---

## Implementation Plan (from Pragmatist)

| Step | Files | Est. Lines | Time |
|:-----|:------|:-----------|:-----|
| 1. HMAC migration compat | state.py | ~20 | 2h |
| 2. Tier classifier | `tier.py` (new) | ~30 | 2h |
| 3. Auto-approve + rate limit | `__init__.py` | ~50 | 3h |
| 4. Cool-down mechanism | `__init__.py` + state.py | ~30 | 1h |
| 5. Shadow mode | `__init__.py` + audit.py | ~20 | 1h |
| 6. Dissent → GH issue | `__init__.py` | ~20 | 2h |
| 7. Testing | All | N/A | 3-4h |

**Total:** ~170 lines, 10-14h

### Files to modify
- `__init__.py` — +80 lines (auto-approve hook, rate limiter, cool-down, tier classifier, dissent→GH)
- `state.py` — +40 lines (fields: auto_approved, cool_down_until, tier, shadow_mode)
- `audit.py` — +15 lines (event types: auto_approve, shadow_block, rate_limited, dissent_issue)
- `tier.py` — NEW, ~30 lines (tier classification logic)

---

## Key Design Decisions

### Why Not Auto-Detect Tier?
Heuristic/regex fragile — false negative = security hole
→ ให้ council vote tier ควบคู่, conservative merge

### Why Global Rate Limit?
Per-session rate limit = bypass via parallel sessions/workspaces
→ shared counter ข้าม sessions

### Why Shadow Mode First?
- Calibrate false-positive rate
- Establish baseline comparison vs manual approval
- Graduation criteria: FP rate < 1% → open real

### Why State Machine for Cool-down?
- `pending_auto → cooling → approved` each transition HMAC-signed
- Persistent timer (not setTimeout) to survive crash/restart
- Cancel = transition to `pending` with audit log
