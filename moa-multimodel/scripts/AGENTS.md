<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-10 | Updated: 2026-06-10 | Behavior: per-run RUN_DIR, last-keyword verdict extraction, safety-role dissent, exit code 2, labels only on APPROVE -->

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

- **Per-run private RUN_DIR**: env `MOA_RUN_DIR` (or secure `mktemp -d`), `chmod 700`. Prevents concurrent-run collision and symlinking attacks. Voice cmd files and verdict files (`$RUN_DIR/pr-${PR}-${voice}.md`, `$RUN_DIR/moa-status`) live here, not fixed `/tmp`.
- `PR` (the second positional arg) is passed in from Python after `_validate_pr_number()` validation. Inside the script it is used bare in filenames (`$RUN_DIR/pr-${PR}-${voice}.md`) and as a string in the Python heredoc. Never interpolate `$PR` into a shell command word without quoting.
- **Verdict extraction**: `grep -woiE 'REQUEST_CHANGES|APPROVED?' | tail -1` extracts last standalone keyword only. This prevents echoed prompt text ("Return ONLY: APPROVE") from forcing a false verdict. `-w` prevents substring hits (DISAPPROVE → no match).
- Rate-limit detection (`is_rate_limit()`) inspects only `head -5` of output against `RATE_LIMIT_PATTERNS` to avoid false positives from the word "throttle" appearing in reviewed code. Do not broaden the grep scope.
- `run_voice()` captures stdout+stderr together (`2>&1`) and does NOT use `eval` or unquoted expansions. Keep cmd files executed as `bash "$cmd_file"` — never `source` or interpolate the path unquoted.
- The `moa-gate` state update is done via an inline Python heredoc that imports `state.py` by path, avoiding any `exec`/`eval` of shell-constructed strings.
- **Safety-role dissent**: skeptic voice REQUEST_CHANGES witholds auto-approve even at 2/3 approvals (mirrors moa-gate SAFETY_ROLES); non-safety dissent (pragmatist/architect) still auto-approves at 2/3.
- **GitHub labels**: added only when verdict file contains "Verdict: APPROVE"; REQUEST_CHANGES/UNCLEAR verdicts do not get `-approved` labels.
- `gh pr comment "$PR"` and `gh pr edit "$PR"` are only reached when `PR != "manual"`, preventing spurious API calls during manual runs.
- The script uses `set -e` at the top; functions that handle expected failures (`run_voice`) capture exit codes locally and always return 0 to avoid aborting the whole council run on a single model failure.

### Testing Requirements
- Smoke test with a real diff file: `bash scripts/council.sh /tmp/some.patch manual`
- Verify `$RUN_DIR/moa-status` is created and contains `|`-delimited lines.
- Verify no verdict file is written when cmd file is absent (SKIPPED path).
- To test rate-limit retry path: mock `claude-cmd.sh` to exit non-zero with `error: rate limit exceeded` on the first call and succeed on the second.
- Verify `$RUN_DIR/pr-<N>-<voice>.md` verdicts are extracted correctly (last keyword, case-insensitive, `-w` word-boundary).
- Verify safety-role dissent (skeptic REQUEST_CHANGES) blocks auto-approve even at 2/3.
- Verify exit 2 when fewer than 2 substantive voices.

### Common Patterns
- All verdict state flows through `$RUN_DIR/moa-status` (`VERDICT|voice[|reason]` lines) — read with `while IFS='|' read -r verdict voice`.
- Verdict files written to `$RUN_DIR/pr-${PR}-${voice}.md` contain the full model output (last 50 lines) plus a `**Verdict: X**` footer.
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
