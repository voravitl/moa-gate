# MOA PR Review Cycle — 3-Voice Gate

Spawn pattern for pre-merge PR review using all 3 MOA CLI voices.

## Pattern

```
PR → MOA Review (3 voices) → Fix → MOA Re-review → Merge
```

## Spawn Commands (parallel)

```bash
# Claude (Architect) — structure, correctness, maintainability
claude -p "Review PR #N..." --max-turns 1

# Codex (Pragmatist) — practicality, impact, effort
echo "Review PR #N..." | codex exec --sandbox read-only --skip-git-repo-check

# Agy (Skeptic) — edge cases, security, waste detection
agy -p "Review PR #N..." --dangerously-skip-permissions
```

## Pitfalls

| Pitfall | Why |
|---------|-----|
| Claude `--max-turns 1` fails on file reads | Use `--max-turns 3 --allowedTools "Read"` for file review; 1 is fine for quick opinion |
| Codex CLI times out in background | `process(action="wait")` clamps at 60s. Use foreground `timeout=180` or fallback to delegate_task subagent |
| Agy is slow (1-3 min) | Set timeout=300 or use 2-voice verdict if only 2 respond |
| CLI sees stale code after force-push | Review must restart after any push; old review = invalid |
| 2/3 is acceptable | If one voice consistently times out, 2-voice verdict is sufficient |
| Author spoof risk | Any commenter can trigger voice match by writing keywords. Mitigate via author check in CI gate |

## When to Re-review

After fixing issues found by any voice, **always re-send to that specific voice** for confirmation. A comment "fix applied" from the agent is not a review — the MOA voice must explicitly re-approve.

## Related CI

`.github/workflows/moa-gate.yml` — automated quorum check that fails when any voice is missing. Set as required status check in branch protection.
