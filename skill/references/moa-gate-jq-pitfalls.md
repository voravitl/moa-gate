# moa-gate.yml jq Pitfalls — Session 2026-05-26

## Critical Bug: `select(A) and B` produces boolean false, not null

In GitHub Actions workflow YAML, jq filters for MOA voice detection MUST wrap
ALL conditions in ONE `select()` call:

```bash
# ❌ WRONG — produces [false] which has length > 0
[.[] | select(.author == "voravitl")
    and (.body | test("(?i)(claude)")?)
    and (.body | test("(?i)(lgtm)")?)]
| length > 0

# ✅ CORRECT — all conditions inside select()
[.[] | select(
    (.author == "voravitl")
    and (.body | test("(?i)\\b(claude)\\b"))
    and (.body | test("(?i)\\b(lgtm|approved?)\\b|✅"))
)]
| length > 0
```

The wrong version produces boolean `false` when author matches but keyword doesn't.
Since `[false] | length` = 1 > 0 = true, ALL voravitl comments pass ALL voice checks.

## Word Boundary — False Positive Approval Keywords

| Bad keyword | Matches falsely | Fix |
|---|---|---|
| `merge` | "merge conflict" | Remove or use `\bmerge\b` (but risky) |
| `accept` | "unacceptable" | Use `\baccepted?\b` |
| `approve` | Safe | `\bapproved?\b` |
| `reviewed` | Safe | `\breviewed\b` |

Recommended approval pattern: `\b(lgtm|verdict|reviewed|approved?)\b|✅`

## Cross-Voice Contamination

A single comment containing multiple voice keywords counts toward multiple voices.
Example: "Architect reviewed the Codex approach — LGTM" matches both Claude AND Codex.

Not fully fixable in jq. Label-based fallback (`moa-claude-approved`, `moa-codex-approved`,
`moa-agy-approved`) is the reliable alternative.

## Mono-User Detection

When all 3 MOA voices post as the same GitHub user (e.g. `voravitl`), author-based
detection is useless. Use keyword + label dual strategy.

## GH API Pagination

`gh api` returns max 30 comments by default. MUST use `--paginate`:

```bash
COMMENTS_JSON=$(gh api --paginate "/repos/{owner}/{repo}/issues/{N}/comments" --jq '[...]')
```

Without `--paginate`, reviews on PRs with 30+ comments will be silently missed.