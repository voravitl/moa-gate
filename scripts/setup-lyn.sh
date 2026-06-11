#!/usr/bin/env bash
# ============================================================================
# LYN Integration — MCP + Hooks Installer for MOA-GATE
# ============================================================================
# Usage:
#   bash scripts/setup-lyn.sh
#   bash scripts/setup-lyn.sh --skip-docker   # ถ้า docker compose start ไว้แล้ว
#   bash scripts/setup-lyn.sh --only-verify   # ตรวจสอบเฉยๆ ไม่ทำอะไร
#
# What it does:
#   1. ตรวจว่า LYN project อยู่ที่ ~/gitlab/LYN
#   2. cargo build --workspace --release (เผื่อมี commit ใหม่)
#   3. install binaries → ~/.local/bin/ (lyn, lyn-mcp, lyn-memory-sync, etc.)
#   4. ตรวจ/เพิ่ม mcp_servers.lyn ใน ~/.hermes/config.yaml
#   5. docker compose --profile lyn up -d (chrono + redis + rag-api + lyn-*)
#   6. รอจนกว่าทุก container healthy
#   7. ตรวจ mcp tools ผ่าน hermes mcp list
#   8. ตรวจ MCP stdio (lyn-mcp) ตรงๆ
# ============================================================================

set -euo pipefail

LYN_DIR="${LYN_DIR:-$HOME/gitlab/LYN}"
HERMES_CONFIG="${HERMES_CONFIG:-$HOME/.hermes/config.yaml}"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
COMPOSE_PROFILE="${COMPOSE_PROFILE:---profile lyn}"
DOCKER_COMPOSE="${DOCKER_COMPOSE:-docker compose}"
SKIP_DOCKER=false
ONLY_VERIFY=false

BLUE='\033[0;34m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}✅${NC} $1"; }
info() { echo -e "  ${BLUE}ℹ️${NC}  $1"; }
warn() { echo -e "  ${YELLOW}⚠️${NC}  $1"; }
fail() { echo -e "  ${RED}❌${NC} $1"; }

# ── Parse args ────────────────────────────────────────────────────────────
for arg in "$@"; do
  case "$arg" in
    --skip-docker) SKIP_DOCKER=true ;;
    --only-verify) ONLY_VERIFY=true ;;
    *) echo "Unknown: $arg"; exit 1 ;;
  esac
done

echo "========================================"
echo "  LYN Integration — Setup"
echo "========================================"

# ── 1. Check LYN project ─────────────────────────────────────────────────
echo ""
echo "[1] 🔍 LYN project directory..."
if [ -d "$LYN_DIR" ] && [ -f "$LYN_DIR/Cargo.toml" ]; then
  ok "Found LYN at $LYN_DIR"
  cd "$LYN_DIR"
else
  fail "LYN project not found at $LYN_DIR"
  info "Set LYN_DIR env or clone: git clone git@github.com:voravitl/LYN.git \"$LYN_DIR\""
  exit 1
fi

# ── 2. Build (ถ้า --only-verify จะข้าม) ──────────────────────────────────
if [ "$ONLY_VERIFY" = false ]; then
  echo ""
  echo "[2] 🔨 Building LYN binaries..."
  latest_commit=$(git log -1 --format="%h %s" 2>/dev/null || echo "?")
  info "HEAD: $latest_commit"

  if cargo build --workspace --release 2>&1 | tail -3; then
    ok "cargo build --release ผ่าน"
  else
    fail "cargo build ล้มเหลว — ดู log ด้านบน"
    exit 1
  fi
fi

# ── 3. Install binaries ──────────────────────────────────────────────────
echo ""
echo "[3] 📦 Installing binaries to $BIN_DIR..."
mkdir -p "$BIN_DIR"

install_bin() {
  local src="$LYN_DIR/target/release/$1"
  local dst="$2"
  if [ -f "$src" ]; then
    rm -f "$dst"
    cp "$src" "$dst"
    chmod 755 "$dst"
    ok "$1 → $(basename $dst)"
  else
    warn "ไม่เจอ $src — ข้าม"
  fi
}

# primary
install_bin "lyn-cli"       "$BIN_DIR/lyn"
install_bin "lyn-mcp"       "$BIN_DIR/lyn-mcp"

# hooks
install_bin "lyn-memory-sync"  "$BIN_DIR/lyn-memory-sync"
install_bin "lyn-auto-failure" "$BIN_DIR/lyn-auto-failure"
install_bin "lyn-session-start" "$BIN_DIR/lyn-session-start"
install_bin "lyn-session-end"   "$BIN_DIR/lyn-session-end"
install_bin "lyn-hooks"         "$BIN_DIR/lyn-hooks"

# ตรวจ PATH
if ! echo "$PATH" | tr ':' '\n' | grep -qx "$BIN_DIR"; then
  warn "$BIN_DIR ไม่อยู่ใน PATH — เพิ่ม: export PATH=\"\$PATH:$BIN_DIR\""
fi

# ── 4. ตรวจ/เพิ่ม mcp_servers.lyn ใน Hermes config ─────────────────────
echo ""
echo "[4] ⚙️  ตรวจ MCP lyn config..."

if [ -f "$HERMES_CONFIG" ]; then
  if grep -q "^  lyn:" "$HERMES_CONFIG" 2>/dev/null; then
    ok "mcp_servers.lyn มีแล้วใน $HERMES_CONFIG"
  else
    info "กำลังเพิ่ม mcp_servers.lyn..."
    # ใช้ Python แทน sed — ปลอดภัยกว่า
    python3 -c "
import yaml, os
cfg_file = os.environ['HERMES_CONFIG']
with open(cfg_file) as f:
    cfg = yaml.safe_load(f)
ms = cfg.setdefault('mcp_servers', {})
if 'lyn' not in ms:
    ms['lyn'] = {
        'url': 'http://127.0.0.1:3004/',
        'connect_timeout': 30,
        'timeout': 120
    }
    with open(cfg_file, 'w') as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)
    print('✅ เพิ่ม mcp_servers.lyn แล้ว')
else:
    print('ℹ️  มีอยู่แล้ว')
" 2>&1 | sed 's/^/  /'
  fi
else
  warn "ไม่เจอ $HERMES_CONFIG — ต้องตั้งค่า MCP lyn ด้วยตัวเอง:"
  warn "  url: http://127.0.0.1:3004/"
fi

# ── 5. Docker Compose ────────────────────────────────────────────────────
if [ "$SKIP_DOCKER" = false ] && [ "$ONLY_VERIFY" = false ]; then
  echo ""
  echo "[5] 🐳 Starting docker compose $COMPOSE_PROFILE..."

  cd "$LYN_DIR"
  $DOCKER_COMPOSE $COMPOSE_PROFILE up -d 2>&1 | tail -5
  ok "docker compose started"

  # รอทุก container healthy
  echo -n "     Waiting for containers..."
  for i in $(seq 1 30); do
    unhealthy=$($DOCKER_COMPOSE $COMPOSE_PROFILE ps --format json 2>/dev/null | python3 -c "
import json, sys
statuses = [json.loads(l) for l in sys.stdin]
unhealthy = [s['Service'] for s in statuses if s.get('Health') not in ('healthy', None)]
print(' '.join(unhealthy))
" 2>/dev/null || echo ".")
    if [ -z "$unhealthy" ]; then
      echo " done"
      break
    fi
    sleep 2
  done

  $DOCKER_COMPOSE $COMPOSE_PROFILE ps 2>&1 | sed 's/^/  /'
fi

# ── 6. MCP smoke test ────────────────────────────────────────────────────
echo ""
echo "[6] 🔌 MCP smoke test..."

if command -v lyn-mcp &>/dev/null; then
  # stdio test
  stdio_ok=$(printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"1.0"}}}' '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | lyn-mcp 2>/dev/null | head -1 | grep -c '"result"' || true)
  if [ "$stdio_ok" -gt 0 ]; then
    ok "lyn-mcp stdio MCP — initialize OK"
  else
    warn "lyn-mcp stdio อาจมีปัญหา — ตรวจด้วย lyn-mcp ตรงๆ"
  fi
else
  fail "lyn-mcp ไม่ได้อยู่ใน PATH"
fi

# HTTP port 3004
if curl -sS -X POST http://127.0.0.1:3004/ \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' 2>/dev/null | grep -q '"result"' 2>/dev/null; then
  ok "lyn-mcp HTTP :3004 — tools/list OK"
else
  warn "lyn-mcp HTTP :3004 ยังไม่ตอบ — ตรวจ docker compose ps"
fi

# ── 7. hermes mcp check ─────────────────────────────────────────────────
echo ""
echo "[7] 🤖 Hermes MCP integration..."

if command -v hermes &>/dev/null; then
  hermes mcp list 2>/dev/null | grep -q lyn && ok "hermes mcp list → lyn enabled" || warn "lyn ไม่เจอใน hermes mcp list"
else
  warn "hermes CLI ไม่ได้ PATH"
fi

# ── 8. Hook binary smoke ─────────────────────────────────────────────────
echo ""
echo "[8] 🪝  Hook binaries smoke..."
for hook in lyn-memory-sync lyn-auto-failure lyn-session-start lyn-session-end; do
  if command -v "$hook" &>/dev/null; then
    ok "$hook — installed"
  else
    fail "$hook — not found"
  fi
done

# ── Summary ──────────────────────────────────────────────────────────────
echo ""
echo "========================================"
echo "  ✅ LYN Setup Complete!"
echo "========================================"
echo ""
echo "   Binaries:  $BIN_DIR/lyn, lyn-mcp, lyn-*"
echo "   Docker:    \$LYN_DIR — $($DOCKER_COMPOSE $COMPOSE_PROFILE ps 2>/dev/null | grep -c lyn) containers"
echo "   MCP HTTP:  http://127.0.0.1:3004/"
echo "   Hermes:    hermes mcp list → lyn"
echo ""
echo "   Next: hermes reload MCP or restart session"
echo "========================================"
