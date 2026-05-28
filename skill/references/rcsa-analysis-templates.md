# RCSA Cross-Reference Analysis — Prompt Templates

Reusable prompt templates for analyzing RCSA with BIA + KPI + KRI cross-reference data.
Designed for 4 Ollama voices + 1 Agy meta-reviewer.

## Context Template (injected into every voice)

```
## COMBINED DATA

### RCSA 2026 (17 risks)
[Department, 17 risks with ratings, control effectiveness]
[Key items: rating compression 15/17 Medium, regression risks, pending items]

### BIA (Business Impact Analysis)
[Criticality: CS=RTO 4h, CBF=RTO 8-24h, NC=Non-critical]
[Services: Vault, GitLab, Kafka, Kong (CS); Jenkins, ELK, Harbor, ArgoCD, Checkmarx (CBF)]
[Support mode: Working Hours Only (KEY blind spot)]

### KRI Actual Data
[Vuln backlog 52.63% RED, Pipeline failure 29.82%→0.23%, Data leakage 0]
[KRI RED refutes L=1 rating]

### KPI Team Ownership
[8 members, platforms, SPOF: Sunun 5 platforms, Puwanut Portal solo]
```

## Voice 1 — Architect (GLM 5.1)

Prompt goal:
```
คุณคือ Architect ที่เชี่ยวชาญ Risk Management Framework วิเคราะห์ RCSA DevOps แบบองค์รวม

ตอบ 5 ข้อ:
1. RCSA rating vs BIA criticality — service ที่เป็น CS/CBF ได้รับ Impact/Likelihood ที่สมเหตุสมผลไหม?
2. RCSA rating vs KRI actual — KRI ที่แดงสอดคล้องกับ RCSA rating หรือไม่?
3. Control Owner vs KPI ownership — control ทุกตัวมี owner ตาม KPI หรือไม่? มี gap อะไร?
4. Risk universe completeness — BIA มี services ไหนที่ RCSA ไม่ได้ cover?
5. Recommendation — 3 actions ที่ควรทำโดยใช้ข้อมูล BIA+KPI+KRI สนับสนุน

สั้น กระชับ ตรงประเด็น
```

## Voice 2 — Critic (DeepSeek V4 Pro)

Prompt goal:
```
คุณคือ Critic ที่มองหา failure mode, edge case, worst case

ตอบ 5 ข้อ:
1. Worst case scenario 3 อันดับ — ใช้ BIA CS + KRI red data สนับสนุน
2. Edge case ที่ RCSA ไม่ cover — เช่น key person ลาออก
3. Control failure cascade — risk ไหนที่ถ้าพังแล้วทำให้ risk อื่นพังตาม?
4. KRI red flag vs RCSA — vuln backlog 52.63% RED แต่ rating Medium — gap?
5. External threat — regulatory audit, vendor collapse

สั้น กระชับ ตรงประเด็น
```

## Voice 3 — Pragmatist (Kimi K2.6)

Prompt goal:
```
คุณคือ Pragmatist ที่เน้นของจริง ปฏิบัติได้

ตอบ 5 ข้อ:
1. Priority actions เรียง 1-5 — พร้อม time estimate + ใครรับผิดชอบ (จาก KPI)
2. Quick wins ที่ BIA CS services — ทำอะไรให้ CS services ก่อน
3. Vuln backlog 52.63% RED → action — เชื่อม KRI กับ RCSA เป็น action plan
4. SPOF mitigation — จาก KPI SPOF (Portal/Sunun) ควรทำอะไร
5. Budget ask — ถ้าต้องขอเงิน management ควรขออะไร

สั้น กระชับ ตรงประเด็น
```

## Voice 4 — Skeptic (Qwen 3.5)

Prompt goal:
```
คุณคือ Skeptic ที่ชอบท้าทายสมมติฐาน

ตอบ 5 ข้อ:
1. 17 risks ครอบคลุม 9 services? — service ไหนที่ BIA บอกว่าสำคัญแต่ไม่มีใน RCSA?
2. "Working Hours Only" — real risk? — ถ้าเกิด incident 20:00 จะทำยังไง?
3. Rating integrity — A9 L1/I5 → KRI RED → L=1 จริงหรือ? หรือแค่ protect?
4. 2025→2026 +55% risks — visibility หรือ noise?
5. Culture question — 14 Moderate + 0 High บอกอะไรเกี่ยวกับ risk culture?

สั้น กระชับ ตรงประเด็น
```

## Voice 5 — Reviewer (Agy — Meta-Review)

Prompt goal (after synthesizing 4 voices into a consolidated report):
```
คุณคือ Reviewer ที่กำลัง review ผล MOA Council Analysis

## Analysis ที่ได้จาก 4 เสียง
[Insert consolidated analysis: 5 blind spots found, 7 priority actions, budget ask, worst case]

ตอบ 5 ข้อ:
1. Analysis นี้มีจุดอ่อนหรือ assumption ที่ผิดอะไร?
2. มี blind spot ที่ 4 เสียงนี้พลาดหรือไม่?
3. 7 actions นี้ feasibility จริงแค่ไหน?
4. Budget สมเหตุสมผลไหม? หรือขาดอะไร?
5. ถ้าต้องเพิ่ม 1 ข้อให้ analysis — จะเพิ่มอะไร?

ตอบสั้น กระชับ ตรงประเด็น
```

## Quick Reference

| Role | Model | Focus | Key Question |
|------|-------|-------|-------------|
| Architect | GLM 5.1 | Risk Universe, Structure | BIA vs RCSA gap? |
| Critic | DeepSeek V4 Pro | Failure Mode, Cascade | Worst case scenario? |
| Pragmatist | Kimi K2.6 | Action Plan, Budget | What to do first? |
| Skeptic | Qwen 3.5 | Challenge Assumptions | Rating integrity? |
| Reviewer | Agy Gemini 3.5 Flash | Meta-Review | What did they miss? |

## Proven Blind Spots (from actual session — Thai Credit Bank DevOps RCSA)

These were caught across rounds:
1. **BIA-RCSA gap** — 4+ CS/CBF services missing from risk register
2. **Working Hours ≠ RTO 4h** — after-hours incident = guaranteed RTO breach
3. **Rating protected** — KRI RED but likelihood rated Low (not genuine)
4. **Key person SPOF** — not modeled in RCSA at all
5. **Harbor recovery** — everyone focused on GitLab HA, forgot container registry
6. **Secret root key mgmt** — DevOps tools credentials not discussed
7. **DR Drill missing** — HA exists but no actual recovery test
8. **Feasibility assumptions wrong** — clone engineer in 3 weeks is too fast for bank; auto-rollback requires CAB approval

## Pitfalls

- **Context too long for some models** — 35K input tokens may exceed model limit. Keep combined data to 25-30K max
- **Don't send RCSA + BIA + KPI + KRI raw** — extract key points into a structured format first
- **Verification required** — subagents self-report "done" but may not have actually created files. Verify action outcomes with `ls` or `read_file`
- **OpenRouter MOA fails with 402** — always fall back to Ollama mode for multi-voice analysis
- **Excel merged cells** — when writing back findings to .xlsx, check `ws.merged_cells.ranges` first or rows may be MergedCell read-only errors
