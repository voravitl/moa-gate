# CLI Tool Model Capabilities

Knowledge bank: models available per CLI tool for MOA Adviser Council.
Last updated: 2026-05-27 (by MOA Council audit session)

## claude (Anthropic Claude Code CLI)

**Version:** 2.1.141
**Model selection flag:** `--model <alias|name>`

```
claude -p "prompt" --max-turns 1 --model opus
```

| Flag value | Actual model | Notes |
|------------|-------------|-------|
| `opus` | Claude Opus (latest) | Strongest reasoning — use for Architect |
| `sonnet` | Claude Sonnet (latest) | Balanced speed/quality |
| `claude-sonnet-4-6` | Claude Sonnet 4.6 | Explicit version pin |

**Architect role = opus** — highest reasoning budget for structural analysis.

## codex (OpenAI Codex CLI)

**Version:** 0.134.0
**Default model:** `gpt-5.5` (from `~/.codex/config.toml`)
**Model selection flag:** `-m <model_slug>`

```bash
codex exec --sandbox read-only --skip-git-repo-check -m gpt-5.4
```

**Available models** (from `~/.codex/models_cache.json`):

| Model slug | Display name | Notes |
|-----------|-------------|-------|
| `gpt-5.5` | GPT-5.5 | Default — frontier model, complex coding |
| `gpt-5.4` | gpt-5.4 | Strong alternative |
| `gpt-5.4-mini` | GPT-5.4-Mini | Faster, cheaper |
| `gpt-5.3-codex` | gpt-5.3-codex | Codex-specialized |
| `gpt-5.2` | gpt-5.2 | Previous gen |
| `codex-auto-review` | Codex Auto Review | PR review automation |

**NOTE:** Codex does NOT support Claude/Anthropic models. Using `-m claude-sonnet-4-6` would error or silently fallback.

**Pragmatist role = gpt-5.5** — default, best overall.

## agy (Antigravity/Gemini CLI)

**Version:** 1.0.2
**Config:** `~/.gemini/antigravity-cli/settings.json`

**Model selection:**
- **Print mode (`-p`):** No `--model` CLI flag — uses default from settings.json always.
- **Interactive mode (`-i`):** Can change via `/model` slash command.

**Available models** (from official docs):
- Gemini 3.5 Flash (default)
- Gemini 3.1 Pro (high/low)
- Gemini 3 Flash
- Claude Sonnet 4.6 (thinking) — via Antigravity bridge
- Claude Opus 4.6 (thinking) — via Antigravity bridge
- GPT-OSS-120b

**Skeptic role** — agy print mode uses whatever is set in settings.json. Cannot be overridden per-call.

## Summary for MOA Council

| CLI | Best model | Flag | Role | Real diversity? |
|:---:|:----------:|:----:|:----:|:--------------:|
| claude | opus | `--model opus` | Architect | ✅ Anthropic |
| codex | gpt-5.5 | default (or `-m gpt-5.5`) | Pragmatist | ✅ OpenAI |
| agy | settings.json default | none in print mode | Skeptic | ✅ Google/Gemini |

3 models from 3 different companies = **true architectural diversity**.
