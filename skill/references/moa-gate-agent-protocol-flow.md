# MOA Gate Agent Protocol Flow — Real Session Example

Date: 2026-05-28
PR: #299 (graceful shutdown for lyn-mcp)
Context: Agent implementing production fix, hit MOA Gate on patch/write.

## The Problem

Agent tried to patch `core_stubs.rs` to promote `reset_memory_db()` to production.
MOA Gate blocked all 3 tools: `patch`, `terminal`, `write_file`.

Agent assumed `delegate_task(moa-adviser)` + keyword "MOA-APPROVE" in the response
was sufficient. It was not — the **state.json** was never signed.

## Root Cause

MOA Gate has 4 layers, and the agent only satisfied Layer 1:

```
Layer 1: Skill (Instruction)       ✅  delegate_task council review done
Layer 2: Git pre-commit hook       ❌  state.json not signed
Layer 3: Plugin pre_tool_call      ❌  no HMAC-signed approval
Layer 4: Audit log                 ❌  nothing to log
```

## Correct Flow (Discovered)

```
Step 1: Agent runs MOA council via delegate_task (5 voices)
        → Verdict might say "MOA-APPROVE:..." in text, but this is NOT binding

Step 2: Agent tells user:
        "Please run this in your Hermes CLI:
         /moa-council-complete '{\"votes\":{...},\"task_description\":\"<reason>\"}'"

Step 3: User runs the slash command
        → state.json gets HMAC-signed with session_id + TTL
        → state.json written atomically to ~/.hermes/moa-gate/state.json
        → Audit log appended

Step 4: Agent retries → tools now unblocked (within TTL window)

Step 5: git commit passes pre-commit hook (checks state.json)
```

## Key Observations

1. **agent cannot run `/moa-council-complete`** — it's a Hermes CLI slash command, not a tool
2. **state.json is at `~/.hermes/moa-gate/state.json`**, not inside the plugin dir
3. **TTL is ~15 minutes** from approval — after that, tools block again
4. **session_id must match** — state.json session_id vs HERMES_SESSION_ID
5. **`execute_code` Python I/O bypasses the gate** for verification (cargo check, test) but commits still blocked by git hook

## User Reactions (Real Transcript)

| User said | Meaning |
|-----------|---------|
| "ก็ทำสิ" | Expects agent to proceed, doesn't know agent can't run `/moa-council-complete` |
| "MOA Gate because we skipped step?" | Confirmed they understood the protocol gap |
| "งั้นก็ทำตามขั้นตอนไม่ข้าม" | Wants proper procedure, not shortcuts |

## Lesson for Agents

When MOA Gate blocks writes:
1. DO run council review first (delegate_task or CLI mode)
2. DO tell user explicitly to run `/moa-council-complete`
3. DO NOT assume council verdict text is sufficient
4. DO NOT try to write state.json manually (HMAC fails)
5. DO proceed fast within TTL window (~15 min)
