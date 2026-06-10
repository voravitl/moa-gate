<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-10 | Updated: 2026-06-10 -->

# scripts/

## Purpose
Contains `council.sh`, the bash orchestrator that runs all three model CLIs sequentially, classifies each verdict, composes a summary, conditionally writes moa-gate `state.json`, and posts per-voice comments and labels to the GitHub PR.

## Key Files
| File | Description |
|------|-------------|
| `council.sh` | Runs architect/skeptic/pragmatist voices via pre-written cmd files, classifies APPROVE/REQUEST_CHANGES/ESCALATED verdicts, writes state.json when 2/3 approve, posts PR comments via `gh pr comment` |

## For AI Agents

### Working In This Directory

**Shell safety rules enforced in this script — do not weaken them:**

- `PR` (the second positional arg) is passed in from Python after `_validate_pr_number()` validation. Inside the script it is used bare in filenames (`/tmp/pr-${PR}-${voice}.md`) and as a string in the Python heredoc. Never interpolate `$PR` into a shell command word without quoting.
- Rate-limit detection (`is_rate_limit()`) inspects only `head -5` of output against `RATE_LIMIT_PATTERNS` to avoid false positives from the word "throttle" appearing in reviewed code. Do not broaden the grep scope.
- `run_voice()` captures stdout+stderr together (`2>&1`) and does NOT use `eval` or unquoted expansions. Keep cmd files executed as `bash "$cmd_file"` — never `source` or interpolate the path unquoted.
- The `moa-gate` state update is done via an inline Python heredoc that imports `state.py` by path, avoiding any `exec`/`eval` of shell-constructed strings.
- `gh pr comment "$PR"` and `gh pr edit "$PR"` are only reached when `PR != "manual"` (line 184 guard), preventing spurious API calls during auto-trigger runs.
- The script uses `set -e` at the top; functions that handle expected failures (`run_voice`) capture exit codes locally and always return 0 to avoid aborting the whole council run on a single model failure.

### Testing Requirements
- Smoke test with a real diff file: `bash scripts/council.sh /tmp/some.patch manual`
- Verify `/tmp/moa-status` is created and contains `|`-delimited lines.
- Verify no verdict file is written when cmd file is absent (SKIPPED path).
- To test rate-limit retry path: mock `claude-cmd.sh` to exit non-zero with `error: rate limit exceeded` on the first call and succeed on the second.

### Common Patterns
- All verdict state flows through `/tmp/moa-status` (KEY=VALUE lines, `|`-delimited) — read with `while IFS='|' read -r verdict voice`.
- Verdict files written to `/tmp/pr-${PR}-${voice}.md` contain the full model output (last 50 lines) plus a `**Verdict: X**` footer.
- Exit code 0 on success and advisory-only failures; exit code 2 only when `total_substantive < 2` (hard block).

## Dependencies

### Internal
- Reads `/tmp/{claude,codex,agy,agy-pipe}-cmd.sh` written by `__init__.py:_setup_voice_prompts()` before this script is called.
- Imports `$MOA_GATE_PLUGIN_PATH/state.py` via inline Python to call `state.approve()`.

### External
| Tool | Purpose |
|------|---------|
| `bash` | Runs the per-voice cmd wrapper files |
| `claude` CLI | Architect voice (`--model sonnet`) |
| `codex` CLI | Skeptic voice |
| `agy` CLI | Pragmatist voice |
| `python3` | Inline heredoc for `state.approve()` call |
| `gh` CLI | `gh pr comment` and `gh pr edit --add-label` |
| `grep`, `awk`, `sed`, `head`, `wc` | Verdict classification and string manipulation |

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
