---
name: moa-multimodel
description: Multi-model MOA review runner plugin. Runs 3 real distinct models (Claude Sonnet, OpenAI Codex, Google Gemini via AGY) as adversarial voices on a PR diff. Writes verdicts to moa-gate state.json so the gate pre-commit hook auto-approves subsequent commits. Sister plugin to moa-gate.
keywords: [moa, multi-model, codex, claude, agy, pr-review, plugin, council]
---

# MOA Multi-Model Plugin

## What this is
A Hermes plugin (not just a skill) that **runs** MOA reviews via real
CLIs, not a workflow documentation file. Sister plugin to `moa-gate`
which **enforces** the gate. moa-multimodel is the *generator* side;
moa-gate is the *verifier* side.

## When the plugin activates
1. **Auto-trigger**: `pre_tool_call` hook intercepts `gh pr create`
   and runs the council on the diff (HEAD vs main) before allowing.
2. **Manual trigger**: `/moa-multimodel review <diff-file> [pr-number]`
   slash command.

## What it does on activation
1. Captures `git diff main...HEAD` to `/tmp/moa-multimodel-auto-diff.patch`
2. Writes per-voice prompt files to `/tmp/{claude,codex,agy}-cmd.sh`
3. Runs `scripts/council.sh <diff> <pr>` which:
   a. Calls `claude -p "..." --model sonnet` (Architect)
   b. Calls `codex exec "..."` (Skeptic)
   c. Calls `agy -p "..."` (Pragmatist)
   d. Each with rate-limit detection + 60s retry ONCE
4. Extracts verdict (APPROVE / REQUEST_CHANGES / ESCALATED)
5. Posts PR comments + adds `moa-{claude,codex,agy}-approved` labels
6. If 2/3 approve, writes moa-gate `state.json` via `state.approve()`
7. moa-gate's pre-commit hook sees approved state → allows next `git commit`

## Fail-back (verified 2026-06-08)
- **claude** rate limit: exit 130/124 OR stderr matches RATE_LIMIT_PATTERNS
  → wait 60s, retry ONCE, else escalate
- **codex** rate limit: same detection, same retry, same escalation
- **agy** silent fail (exit 0, 0 bytes): env/credential issue, NOT rate
  limit, do NOT retry
- 2/3 substantive voices = sufficient signal
- 1/3 or fewer = block (need manual)
- 0/3 due to all rate-limited = STOP, do not commit

## Slash commands
- `/moa-multimodel review <diff> [pr]` — manual run
- `/moa-multimodel help` — show help

## Configuration
- `MOA_MULTIMODEL_AUTOTRIGGER=0` — disable pre_tool_call auto-trigger
- `MOA_MULTIMODEL_REPO` — override target repo for `git diff main...HEAD`
  (default: `$(git rev-parse --show-toplevel)` of cwd)
- `MOA_GATE_PLUGIN_PATH` — override moa-gate plugin path
  (default: sibling dir, then `~/.hermes/plugins/moa-gate`)

## Verified signal (PR #366)
3/3 substantive verdicts from real distinct models caught and approved
the env-chain test additions for issue #349. Verified by reading
`/tmp/pr-366-{architect,skeptic,pragmatist}.md` after council ran.
