# Agy CLI as Code Reviewer — Proven Pattern

**Origin:** LYN PR review workflow (session 2025-05-25)
**Updated:** 2025-05-25 — added timeout handling, fix-push pattern, comment template

## When to Use
After creating a PR, send to agy for review before merging. Agy finds real bugs that the authoring agent missed.

## Proven Command Pattern

```bash
agy -p "คุณเป็น **Code Reviewer** — review PR #<N>

Review: https://github.com/<owner>/<repo>/pull/<N>

ให้ review:
1. ความถูกต้องของ logic / HTTP client / error handling
2. Security (API key handling, secrets leak)
3. Test coverage
4. Rust idioms + clippy compliance
5. Edge case: what happens when external service is down?

ตอบสั้น 5-10 บรรทัด — specific issues หรือ LGTM" --dangerously-skip-permissions
```

## Key Traits

| Aspect | Behavior |
|---|---|
| **Accuracy** | Finds real bugs (type mismatches, panic! in lib code) |
| **Speed** | ~2-5 min (clones repo, builds, runs tests) |
| **Output** | Structured file-by-file with line references |
| **False positives** | Rare — findings are usually valid |
| **False negatives** | May miss subtle semantic issues |

## Pitfalls

1. **Agy clones the repo** into `~/.gemini/antigravity-cli/scratch/` — first run is slow (2-5 min).
2. **Timeout clamping** — Hermes `wait()` clamps to 60s. Agy takes 2-5 min. Poll with `process(action="poll")` instead of one `wait()`.
3. **One-shot only** — agy can't ask clarifying questions. Make the prompt complete.
4. **Be specific in prompt** — list exact review categories. Generic "review this" gives shallow output.
5. **Fresh context** — agy starts with zero session memory. Include all context in the prompt.

## Real Issues Agy Found

| Issue | Example | How Found |
|---|---|---|
| Wrong SQL column type | `row.get::<_, Vec<u8>>(1)?` for TEXT column | Read schema in `gh pr diff` |
| panic! in library code | `unwrap_or_else(\|_\| panic!(...))` in vector search | Code review catch |
| Auth locked to single domain | `base_url.contains("ollama.com")` blocking proxies | Security lens |
| IPv6 incompatibility | Manual `url.split(':')` for TCP connect | Edge case analysis |

## Fix → Push → Comment Workflow

After receiving agy review:

1. Fix all issues reported
2. Verify: `cargo clippy --workspace -- -D warnings && cargo test --workspace`
3. Push fixes:
   ```
   cargo fmt --all
   git add -A
   git commit --amend --no-edit
   git push --force-with-lease
   ```
4. Post comment with Issues Fixed table:
   ```
   gh pr comment <N> --body "## Agy Review - Issues Fixed

   | Issue | Before | After |
   |---|---|---|
   | panic! in lib | unwrap_or_else() | map_err()? ✅ |

   **Reviewed by:** agy/gemini-3.5-flash via Hermes Agent"
   ```
5. Merge: `gh pr merge <N> --squash --delete-branch`

## Comment Template: Issues Fixed

```
## Agy Review - Issues Fixed

@voravitl — agy/gemini-3.5-flash reviewed:

| Issue | Before | After |
|---|---|---|
| [description] | [old code] | [new code] ✅ |

### Still Acceptable for Now
- [tradeoff 1] — [rationale]

### LGTM ✅
- [item]

**Reviewed by:** agy/gemini-3.5-flash via Hermes Agent
```

## Cost

Free (Google Gemini 3.5 Flash) — zero token cost.

## See Also

- `moa-adviser` — full CLI mode documentation
- `review-pr-gh` — multi-reviewer PR audit