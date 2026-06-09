# MOA Gate Plugin — Design v2 + 7-Voice Council Review

> Architecture designed through iterative MOA council review.
> Opus (claude-sonnet-4) served as final reviewer with hardest critique.

## Design Evolution

```
v1: Plugin only, plain JSON state, no terminal block, no audit
    → Opus review: "sound but leaky, needs HMAC, terminal block, audit log"
v2: HMAC state, terminal block, audit log, git pre-commit hook
    → Critic found: computer_use bypass, cronjob bypass, browser/MCP bypass
    → Skeptic challenged fundamental assumption: "plugin ≠ security boundary"
v3 (FINAL): Invert architecture — security at OS+server, plugin = UX layer
```

## v3 Architecture (4 Layers, Opus Final)

```
Layer 0 — OS-level (Authoritative, NOT in Hermes)
├── Agent runs in restricted macOS user
├── No access to Keychain, signing keys, prod credentials
├── computer_use DISABLED at config level (not plugin block)
└── Seatbelt/sandbox-exec limits filesystem write

Layer 1 — Server-level (Authoritative, NOT in Hermes)
├── GitHub branch protection on main
├── Required signed commits (GPG on human's machine)
├── Required PR review from 2 humans
└── Server-side pre-receive hook validates MOA token

Layer 2 — Defense-in-depth (Hermes plugin + git hooks)
├── Git pre-commit hook: verify HMAC state before commit
├── Audit log with hash chain → ship to SIEM real-time
└── HMAC state in macOS Keychain (intent signal)

Layer 3 — UX (Hermes plugin, weakest but most visible)
├── pre_tool_call hook: block write tools
├── Skill auto-load: teach AI workflow
├── Slash commands: /moa-council-complete, /moa-emergency, /moa-revoke
└── Block list: catches honest mistakes
```

## 7-Voice Council Results

### Round 1 (3 voices parallel)

| Voice | Model | Key Finding |
|:-----:|:-----:|:------------|
| 🧠 Architect | GPT-5.5 | v2 แก้ TOCTOU ได้ แต่ต้อง server-side hook, session-scoped state, TTL auto-revoke. Readiness 7/10 |
| 📐 Strategist | GLM-5.1 | Timeline 5-7 วัน, audit log ต้อง hash chain, shadow mode rollout recommended |
| 🔍 Critic | DeepSeek V4 Pro | **computer_use bypass = agent เปิด Terminal.app ตรง**, cronjob no_agent bypass, HMAC key ใน .env ไม่พอ |

### Round 2 (2 voices)

| Voice | Model | Key Finding |
|:-----:|:-----:|:------------|
| 🏃 Pragmatist | Kimi K2.6 | Block new tools feasible +1 day, Keychain +0.5 day, total 5-6 days. Cost/benefit stop: control what Hermes can, accept OS-level determined agent can escape |
| 🤨 Skeptic | Qwen 3.5 | **Fundamental assumption wrong**: plugin can't prevent agent with desktop access. computer_use = existential bypass. Accept plugin = deterrent, not security boundary. **Asks: why not put all enforcement at OS level?** |

### Opus Final Review

| Topic | Opus Verdict |
|:------|:-------------|
| Threat model | Confused between "buggy agent" vs "adversarial agent" — need different defenses |
| v2 security boundary | ❌ **Not pass** against "cannot bypass by any means" criterion |
| Plugin value | ✅ Makes accidents impossible, forces explicit intent, creates audit trail |
| Architecture shift | **Invert**: OS+server = security, plugin = UX |
| For ธปท. audit | "AI ไม่มี privilege ที่จะ bypass ได้ตั้งแต่ต้น เพราะมัน run ใน sandbox" — defendable |
| What to ship | HMAC + Keychain, audit + hash chain, server-side hook, shadow mode, block list |
| What to drop | Block computer_use/cronjob at plugin (disable at config instead), terminal whitelist regex, TTL auto-revoke |
| v2 readiness | **6/10 as security boundary, 9/10 as UX + audit layer** |
| Timeline | 3-4 days + 1 week DevSecOps for branch protection |

## Bypass Paths Identified

| Bypass Path | Severity | Mitigation |
|:-----------:|:--------:|:-----------|
| Agent writes state file directly | 🔴 → 🟢 | HMAC signing (agent can't forge) |
| terminal tool for git commit | 🔴 → 🟢 | Block terminal tool in plugin |
| computer_use → Terminal.app | 🔴 | Disable at agent config level |
| cronjob no_agent=true script | 🔴 | Disable at scheduler level |
| browser/MCP evaluate_script | 🔴 | Disable at agent config level |
| cat .env → get HMAC key | 🟡 → 🔴 | Move to macOS Keychain |
| git commit --no-verify | 🟡 | Server-side pre-receive hook |
| patch replace_all | 🟢 | Block all patch modes |
| skill_manage → write plugin files | 🟢 | Block skill_manage tool |

## Plugin Implementation

### State Management (state.py)
- File: `~/.hermes/moa-gate/state.json`
- HMAC-SHA256(json without hmac field + MOA_GATE_KEY from .env)
- Atomic write: tempfile.NamedTemporaryFile + os.replace
- chmod 600 on state file
- Fail-closed: any read error → return pending state

### Audit Log (audit.py)
- File: `~/.hermes/moa-gate/audit.log`
- Format: JSON Lines, one object per line
- Hash chain: each entry has prev_hash (SHA-256 of prior entry)
- Append-only: `open(path, "a")`
- Tamper detection: verify_chain() walks chain, reports mismatches

### pre_tool_call Hook (__init__.py)
- Blocked tools: patch, write_file, write, git_commit, gh_pr_create, skill_manage, terminal, process
- Terminal whitelist: read-only commands (git log/diff/status, cat, ls, grep, cargo test, pytest, etc.)
- Pipe/redirect/semicolon block: negative lookahead `(?!.*[|;&>])`
- Session isolation: approval session_id ≠ current session → block
- Fail-closed: try/except ALL → return block on any error

### Git Pre-commit Hook (pre-commit.py)
- Standalone Python script (no Hermes dependency)
- Reads state, verifies HMAC, checks status = approved
- Blocks commit if: pending, HMAC mismatch, no state file, no HMAC key
- Installed at `.githooks/pre-commit` in each project repo

## Integration Test Results

23/23 tests passed covering:
- Default pending state, block/approve/revoke cycle
- Terminal read-only vs write detection
- Pipe/redirect/semicolon bypass blocking
- Cross-session isolation
- HMAC tamper detection
- Audit chain integrity
- All slash commands
- Git pre-commit hook