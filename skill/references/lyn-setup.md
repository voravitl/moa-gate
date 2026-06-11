---
name: moa-gate-lyn-setup
description: "Set up LYN MCP server + hooks for Hermes Agent — part of MOA-GATE plugin"
keywords: [lyn, setup, mcp, hooks, integration]
---
# LYN Integration Setup

## Prerequisites

- LYN project at `~/gitlab/LYN/` (with `Cargo.toml`)
- Hermes Agent with `~/.hermes/config.yaml`
- Docker + Docker Compose
- Rust 1.82+ + cargo

## Installation

```bash
# One-shot
bash ~/.hermes/plugins/moa-gate/scripts/setup-lyn.sh

# Or from repo
bash ~/gitlab/MOA-GATE/scripts/setup-lyn.sh
```

## What it does

| Step | Action |
|------|--------|
| 1 | ตรวจ LYN project directory |
| 2 | `cargo build --workspace --release` |
| 3 | install 7 binaries → `~/.local/bin/` (lyn, lyn-mcp, 5 hooks) |
| 4 | add `mcp_servers.lyn` → `~/.hermes/config.yaml` |
| 5 | `docker compose --profile lyn up -d` |
| 6 | MCP smoke test (stdio + HTTP:3004) |
| 7 | Verify `hermes mcp list` has `lyn` |

## Manual steps (ถ้าไม่อยากรัน script)

```bash
# Build
cd ~/gitlab/LYN && cargo build --workspace --release

# Install binaries
install -m755 target/release/lyn-cli ~/.local/bin/lyn
install -m755 target/release/lyn-mcp ~/.local/bin/lyn-mcp
install -m755 target/release/lyn-memory-sync ~/.local/bin/
install -m755 target/release/lyn-auto-failure ~/.local/bin/
install -m755 target/release/lyn-session-start ~/.local/bin/
install -m755 target/release/lyn-session-end ~/.local/bin/
install -m755 target/release/lyn-hooks ~/.local/bin/

# Docker
docker compose --profile lyn up -d

# Add MCP to Hermes config (~/.hermes/config.yaml):
# mcp_servers:
#   lyn:
#     url: http://127.0.0.1:3004/
#     connect_timeout: 30
#     timeout: 120
```

## Verify

```bash
# Docker containers
docker compose --profile lyn ps

# MCP tools via HTTP
curl -s -X POST http://127.0.0.1:3004/ \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | jq '.result.tools | length'

# Hermes integration
hermes mcp list | grep lyn
hermes tools list | grep lyn
```
