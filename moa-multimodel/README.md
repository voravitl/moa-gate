# MOA Multi-Model — Hermes Plugin

Multi-model MOA review runner. Spawns 3 real distinct models (Claude
Sonnet + OpenAI Codex + Google Gemini via AGY) as adversarial voices
for PR review.

## Architecture

```
gh pr create (or /moa-multimodel review)
    │
    ▼
┌─ moa-multimodel ──────────────────────────────────┐
│ 1. git diff main...HEAD → /tmp/diff.patch        │
│ 2. RUN_DIR = mktemp -d (per-run private dir)    │
│ 3. Write per-voice prompts to $RUN_DIR/*-cmd.sh │
│ 4. council.sh runs claude + codex + agy         │
│ 5. Extract verdict (last keyword wins)          │
│ 6. Post PR comments + labels (APPROVE only)     │
│ 7. Safety-role dissent blocks auto-approve      │
└──────────────────┬────────────────────────────────┘
                   │ 2/3 approve & no dissent
                   ▼
┌─ moa-gate (sibling plugin) ───────────────────┐
│ state.approve() → state.json (HMAC signed)    │
│ pre-commit hook → allows next git commit      │
└───────────────────────────────────────────────┘
```

## Files

| File | Purpose |
|------|---------|
| `__init__.py` | Plugin entry + pre_tool_call hook + slash command |
| `scripts/council.sh` | Runs 3 voices, classifies verdicts, writes state |
| `skill/SKILL.md` | Skill definition for AI auto-discovery |
| `plugin.yaml` | Hermes plugin manifest |

## Activation

| Trigger | Effect |
|---------|--------|
| `gh pr create` | Auto-run council on diff (disable with `MOA_MULTIMODEL_AUTOTRIGGER=0`) |
| `/moa-multimodel review <diff> [pr]` | Manual run |
| `/moa-multimodel help` | Show help |

## Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `MOA_MULTIMODEL_REPO` | `$(git rev-parse --show-toplevel)` of cwd | Target repo for `git diff main...HEAD` |
| `MOA_MULTIMODEL_AUTOTRIGGER` | `1` | Set to `0` to disable auto-trigger |
| `MOA_GATE_PLUGIN_PATH` | sibling dir, else `~/.hermes/plugins/moa-gate` | Used for state import |

## Fail-back

- **Rate limit**: detect via first 5 lines of output, wait 60s, retry ONCE
- **UNCLEAR verdicts**: escalated with label `voice=UNCLEAR` in summary
- **Safety-role dissent**: skeptic REQUEST_CHANGES withholds auto-approve even at 2/3
- **2/3 approve & no dissent** → auto-write state.json
- **<2 substantive voices** → exit 2, block PR (needs manual review)

## Installation

```bash
ln -sf ~/path/to/moa-gate/moa-multimodel ~/.hermes/plugins/moa-multimodel
```

The plugin auto-locates `moa-gate` as a sibling plugin dir, or via
`MOA_GATE_PLUGIN_PATH` env var.
