# Hermes Shell Hook MOA Gate — Full Reference

## Overview

Hermes `pre_tool_call` shell hook ที่ intercept write tools ก่อน execution
และ block ถ้า MOA ยังไม่ approve

## Shell Script

```bash
#!/usr/bin/env bash
# ~/.hermes/scripts/moa-gate.sh
# Hermes pre_tool_call hook — block write tools unless MOA approved
set -euo pipefail

STATE_FILE="$HOME/.hermes/moa-state.json"

# Read JSON from stdin (Hermes pipe)
INPUT=$(cat)

# Extract tool name
TOOL_NAME=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null || echo "")

# Allow non-write tools
case "$TOOL_NAME" in
  patch|write_file|write|git_commit|gh_pr_create) ;;
  *) echo '{}'; exit 0 ;;
esac

# Check state
if [ ! -f "$STATE_FILE" ]; then
  echo '{"decision":"block","reason":"🛑 MOA review required before write tools. Run: moa-adviser --task \"<task>\" --voices 3 --mode cli"}'
  exit 0
fi

STATUS=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('status','pending'))" 2>/dev/null || echo "pending")

if [ "$STATUS" = "approved" ]; then
  echo '{}'
  exit 0
fi

echo '{"decision":"block","reason":"🛑 MOA review required. Run: moa-adviser --task \"<task>\""}'
```

### Setup

```bash
chmod +x ~/.hermes/scripts/moa-gate.sh
mkdir -p ~/.hermes/scripts
```

### Config (`~/.hermes/config.yaml`)

```yaml
hooks:
  pre_tool_call:
    - command: ~/.hermes/scripts/moa-gate.sh
      matcher: "^(patch|write_file|write|git_commit|gh_pr_create)$"
      timeout: 5
hooks_auto_accept: true
```

### Verify

```bash
hermes hooks list
# Expected:
# pre_tool_call  moa-gate.sh  (matcher: ^(patch|write_file|write|git_commit|gh_pr_create)$)
```

## State Management

### Approve

```bash
cat > ~/.hermes/moa-state.json <<EOF
{
  "status": "approved",
  "approved_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "approved_by": ["architect","pragmatist","skeptic"],
  "reason": "Fix memory leak in vector store",
  "tool_blocked": ["patch","write_file","write","git_commit","gh_pr_create"]
}
EOF
```

### Revoke

```bash
cat > ~/.hermes/moa-state.json <<EOF
{"status":"pending","approved_at":null,"approved_by":[],"reason":"","tool_blocked":[]}
EOF
```

### Check

```bash
cat ~/.hermes/moa-state.json | python3 -m json.tool
```

## State Schema

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | `"approved"` / `"pending"` / `"rejected"` |
| `approved_at` | string (ISO 8601) | เมื่อ approve |
| `approved_by` | string[] | รายชื่อ voices |
| `reason` | string | เหตุผล task |
| `tool_blocked` | string[] | tools ที่ถูก gate |

## Tool Matchers

Regex examples สำหรับ `matcher:` field:

| Matcher | Tools Gated |
|---------|-------------|
| `^(patch\|write_file\|write)$` | Write tools only |
| `^(git_commit\|gh_pr_create)$` | Git operations |
| `^terminal$` | All terminal commands |
| `.*` | ALL tools (รวม non-write) |

## Security Notes

- State เป็น file-based — agent ที่ตั้งใจ bypass เขียน state ตรงๆ ได้
- Defense layers: (1) shell hook block, (2) moa-adviser skill auto-load, (3) user monitoring
- ไม่มี auth on `--approve` — separation of duties via user awareness
- Shell hook runs with Hermes process permissions

## Pitfalls

| Pitfall | Mitigation |
|---------|-----------|
| Script error → tool blocked unconditionally | Test script first, use `|| echo '{}'` fallback |
| State file permission mismatch | `chmod 600 ~/.hermes/moa-state.json` |
| Agent writes state bypass | Add logging to `~/.hermes/logs/agent.log` |
| ลืม revoke → task ถัดไปผ่านฟรี | Set cron: `hermes cron --at '0 * * * *' -- moa-gate --revoke` |
| matcher regex wrong → gate ไม่ทำงาน | Test with `hermes hooks test pre_tool_call --for-tool patch` |
