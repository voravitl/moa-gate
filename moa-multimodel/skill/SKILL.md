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
2. Creates per-run private RUN_DIR (via `mktemp -d`, `chmod 700`)
3. Writes per-voice prompt files to `$RUN_DIR/{claude,codex,agy}-cmd.sh`
4. Runs `scripts/council.sh <diff> <pr>` which:
   a. Calls `claude -p "..." --model sonnet` (Architect)
   b. Calls `codex exec "..."` (Skeptic)
   c. Calls `agy -p "..."` (Pragmatist)
   d. Each with rate-limit detection (first 5 lines) + 60s retry ONCE
5. Extracts verdict (last standalone keyword wins; APPROVED→APPROVE; else→UNCLEAR)
6. Posts PR comments + adds `moa-{claude,codex,agy}-approved` labels only on APPROVE verdicts
7. **Safety-role dissent**: skeptic REQUEST_CHANGES blocks auto-approve even at 2/3
8. If 2/3 approve AND no dissent, writes moa-gate `state.json` via `state.approve()`
9. moa-gate's pre-commit hook sees approved state → allows next `git commit`

## Fail-back (verified 2026-06-10)
- **Rate limit**: detect via first 5 lines of output matching RATE_LIMIT_PATTERNS
  → wait 60s, retry ONCE, else escalate
- **UNCLEAR verdicts**: escalated (no APPROVE/REQUEST_CHANGES keyword found)
- **Safety-role dissent**: skeptic REQUEST_CHANGES withholds auto-approve even at 2/3; non-safety dissent allows auto-approve
- **2/3 substantive voices & no dissent** → auto-write state.json
- **<2 substantive voices** → exit 2, block PR (need manual review)
- **Verdict files**: written to `$RUN_DIR/pr-<N>-<voice>.md`; labels added only when "Verdict: APPROVE" present

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
