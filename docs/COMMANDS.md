# MOA Gate + AI-DLC — Command Reference

---

## MOA Gate Slash Commands

### `/moa-gate status` หรือ `/moa-status`

ดูสถานะ gate ปัจจุบัน

**Output:**
```
🟢 Gate Status
  Status: pending
  Session: abc123
  Pending Tools: [patch, write_file, terminal]
```

**Parameters:** (ไม่มี)

---

### `/moa-gate council-complete <JSON>` หรือ `/moa-council`

ส่งผล council vote (JSON) — รองรับ auto-approve

**Parameters:**

| Parameter | Required | คำอธิบาย |
|-----------|----------|---------|
| JSON body | ✅ | Object มี votes, task_description, changed_paths, diff_keywords |

**JSON schema:**
```json
{
    "votes": {
        "architect": "approve",
        "pragmatist": "approve",
        "skeptic": "dissent"
    },
    "task_description": "refactor auth module",
    "dissent_reason": "missing error handling",
    "changed_paths": ["src/auth.rs", "src/middleware.rs"],
    "diff_keywords": ["refactor", "error-handling"]
}
```

**Auto-approve logic:**
- ≥80% approve → Tier 1 → auto ✅
- ≥80% approve → Tier 2 → block ⛔ (ต้อง manual)
- <80% → rejected ❌
- Critic/Skeptic dissent any → force Tier 2

**ตัวอย่าง:**
```
/moa-council-complete '{"votes":{"architect":"approve","pragmatist":"approve","skeptic":"approve"},"task_description":"add tests","changed_paths":["tests/"],"diff_keywords":["test"]}'
```

---

### `/moa-gate revoke` หรือ `/moa-revoke`

ยกเลิกการอนุมัติทั้งหมด — reset state กลับเป็น pending

**Parameters:** (ไม่มี)

---

### `/moa-gate log [limit]` หรือ `/moa-log`

ดู audit log

**Parameters:**

| Parameter | Default | คำอธิบาย |
|-----------|---------|---------|
| `limit` | 10 | จำนวน log entries ที่ต้องการดู |

**ตัวอย่าง:**
```
/moa-log 20
```

---

### `/moa-gate verify` หรือ `/moa-verify`

ตรวจสอบความถูกต้องของ HMAC-signed state  
ใช้เมื่อสงสัยว่า state ถูกแก้ไขโดยตรง

**Parameters:** (ไม่มี)

---

### `/moa-gate help`

แสดง help text

**Parameters:** (ไม่มี)

---

## AI-DLC Commands

AI-DLC ไม่มี slash commands โดยตรง — ทำงานผ่าน Hermes plugin hooks อัตโนมัติ

### กระทำผ่าน file system

```bash
# ดู phase ปัจจุบัน
cat ~/.hermes/ai-dlc/phase.json

# เปลี่ยน phase
# (ดู USER_GUIDE.md หัวข้อ 8)
```

### กระทำผ่าน steering rules

```bash
# ดู rules ทั้งหมด
cat ~/wiki/steering/security.yaml
cat ~/wiki/steering/architecture.yaml
cat ~/wiki/steering/compliance.yaml

# แก้ไข rules (เพิ่ม/ลบ)
vim ~/wiki/steering/security.yaml
```

---

## Quick Reference Card

```
┌─ MOA GATE ──────────────────────────────┐
│                                         │
│  /moa-status        → ดูสถานะ          │
│  /moa-council       → ส่งผล council    │
│  /moa-revoke        → ยกเลิกอนุมัติ     │
│  /moa-log           → audit log        │
│  /moa-verify        → ตรวจ state       │
│                                         │
└─────────────────────────────────────────┘

┌─ AI-DLC ─────────────────────────────────┐
│                                         │
│  ~/.hermes/ai-dlc/phase.json → ดู phase │
│  ~/wiki/steering/*.yaml     → rules     │
│                                         │
│  INCEPTION → เขียน code ไม่ได้          │
│  CONSTRUCTION → เขียน code ได้          │
│  OPERATION → deploy/config ได้          │
│                                         │
└─────────────────────────────────────────┘
```
