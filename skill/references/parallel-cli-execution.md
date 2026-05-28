# Parallel CLI Execution Pattern — MOA Adviser

This pattern spawns multiple CLI AI tools in parallel, collects their outputs, and synthesizes a verdict. Reusable for any multi-model advisory workflow.

## Architecture

```
Question → 3 parallel CLI tools → collect outputs → synthesize → verdict
```

## Tools & Commands

| CLI | Command | Model | When to use |
|-----|---------|-------|-------------|
| claude | `claude -p "..." --max-turns 1` | Claude Opus-4-7 | Deep reasoning, architecture, structure |
| codex | `echo "..." \| codex exec --sandbox read-only` | GPT-5.5 | Direct answers, practical, analytical |
| agy | `agy -p "..." --dangerously-skip-permissions` | Gemini 3.5 Flash | Fast opinions, skepticism, long context |

## Execution Pattern in Hermes

### Step 1: Spawn in parallel

Use `terminal(background=true, notify_on_complete=true)` for each tool:

```python
# Claude (no pty needed, text output)
terminal(
    command='claude -p "prompt" --max-turns 1',
    background=True,
    notify_on_complete=True,
    timeout=120
)

# Codex (stdin pipe, needs git repo)
terminal(
    command='echo "prompt" | codex exec --sandbox read-only',
    background=True,
    notify_on_complete=True,
    timeout=180,
    workdir="/path/to/git/repo"
)

# Agy (no pty needed, text output)
terminal(
    command='agy -p "prompt" --dangerously-skip-permissions',
    background=True,
    notify_on_complete=True,
    timeout=60
)
```

### Step 2: Wait for all notifications

Use `process(action="wait")` for each one. The system clamps wait timeout to 60s max — run 3 separate calls, one per process. If output is partial after wait, call `process(action="poll")` to check exit_code.

### Step 3: Collect outputs

Read output from each process. Claude and agy return clean text. Codex output may have noise (hook lines, session info) — extract the actual response line (starts after the last `hook:` line).

### Step 4: Synthesize

The session model (Hermes) reads all 3 responses and produces a structured verdict.

## Prompt Crafting per Voice

| CLI | Role | Prompt style |
|-----|------|-------------|
| claude | Architect | "You are an Architect. Focus on long-term structure, correctness, maintainability. [question] Keep response to 3-5 concise bullet points." |
| codex | Pragmatist | "You are a Pragmatist focused on what works in production. [question] Keep response to 3-5 lines." |
| agy | Skeptic | "You are a Skeptic — challenge assumptions and find flaws. [question] 3-5 lines, direct, no sugar-coating." |

Each prompt MUST be short (2-3 paragraphs max) because CLI tools have no session context. Request specific format (3-5 lines, bullet points) to get clean output.

## Save Output

After synthesis, save the full analysis to `~/wiki/lyn/moa-adviser/<YYYY-MM-DD>-<title>.md` with:
- Original question + context
- Raw responses from all 3 tools
- Synthesized verdict
- Action items
- Resume point

## Pitfalls

| Pitfall | Mitigation |
|---------|------------|
| Codex needs git repo | Run from a repo dir or use `--skip-git-repo-check` |
| Codex sandbox loop on macOS | Use `--sandbox read-only`, not `workspace-write` or deprecated `--full-auto` |
| Token waste on claude JSON mode | Use plain text mode (cheaper, clean enough) |
| Output noise from codex | Extract response after the `hook:` lines |
| Timeout on long questions | Set generous timeout (120-300s) |
| Prompt too long for CLI | Keep prompts under 2-3 paragraphs |
| Not all 3 CLIs installed | Fallback to 2 voices (any combination works) |
| **Process wait timeout clamp** | `process(wait, timeout=N)` clamps to 60s max. Don't rely on wait alone. Spawn with `notify_on_complete=true`, then call `process(wait)` once per process. Output arrives even when wait clamps — the bg process keeps running and notify fires. After wait returns, the process has usually finished. If partial output, call `process(action="poll")` to check exit_code. Pattern: 3 separate `process(wait)` calls, one per session_id, in sequence. |