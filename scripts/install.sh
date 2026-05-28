#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# MOA Gate — One-shot Installer
# ============================================================================
# Usage:
#   AI-friendly:  bash <(curl -sL https://raw.githubusercontent.com/voravitl/moa-gate/main/scripts/install.sh)
#   Manual:       git clone git@github.com:voravitl/moa-gate.git && cd moa-gate && bash scripts/install.sh
#
# What it does:
#   1. Clone/update plugin repo to ~/.hermes/plugins/moa-gate
#   2. Symlink moa-adviser skill to ~/.hermes/skills/devops/moa-adviser
#   3. Install global git pre-commit hook (P0)
#   4. Auto-generate MOA_GATE_KEY if missing
#   5. Show next steps
# ============================================================================

REPO_URL="git@github.com:voravitl/moa-gate.git"
PLUGIN_DIR="$HOME/.hermes/plugins/moa-gate"
SKILL_LINK="$HOME/.hermes/skills/devops/moa-adviser"
HOOK_DIR="$HOME/.hermes/moa-gate"
HOOK_FILE="$HOOK_DIR/pre-commit.py"
ENV_FILE="$HOME/.hermes/.env"

echo "========================================"
echo "  MOA Gate — One-Shot Installer"
echo "========================================"

# ── Step 1: Clone / Pull plugin ──────────────────────────────────────────
echo ""
echo "[1/5] 📦 Plugin..."

if [ -d "$PLUGIN_DIR/.git" ]; then
    echo "       Already cloned, pulling updates..."
    git -C "$PLUGIN_DIR" pull --ff-only
else
    mkdir -p "$(dirname "$PLUGIN_DIR")"
    git clone "$REPO_URL" "$PLUGIN_DIR"
fi
echo "       ✅ $PLUGIN_DIR"

# ── Step 2: Symlink skill ────────────────────────────────────────────────
echo ""
echo "[2/5] 🧠 Skill..."
mkdir -p "$HOME/.hermes/skills/devops"
ln -sfn "$PLUGIN_DIR/skill" "$SKILL_LINK"
echo "       ✅ $SKILL_LINK → $PLUGIN_DIR/skill"

# ── Step 3: Install pre-commit hook (P0) ─────────────────────────────────
echo ""
echo "[3/5] 🔒 Pre-commit hook..."
mkdir -p "$HOOK_DIR"
cp "$PLUGIN_DIR/hooks/pre-commit.py" "$HOOK_FILE"
chmod +x "$HOOK_FILE"
git config --global core.hooksPath "$HOOK_DIR"
echo "       ✅ Global hooksPath → $HOOK_DIR"
echo "       ✅ All git repos now check MOA Gate before every commit"

# ── Step 4: Auto-generate HMAC key ───────────────────────────────────────
echo ""
echo "[4/5] 🔑 HMAC key..."
if grep -q "MOA_GATE_KEY" "$ENV_FILE" 2>/dev/null; then
    echo "       Already set in $ENV_FILE"
else
    mkdir -p "$(dirname "$ENV_FILE")"
    KEY=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))")
    echo "MOA_GATE_KEY=$KEY" >> "$ENV_FILE"
    echo "       ✅ Auto-generated → $ENV_FILE"
fi

# ── Step 5: Verify ───────────────────────────────────────────────────────
echo ""
echo "[5/5] ✅ Verify..."
python3 -c "
import sys, os
os.environ['MOA_GATE_KEY'] = open('$ENV_FILE').read().split('MOA_GATE_KEY=', 1)[1].split()[0]
sys.path.insert(0, '$PLUGIN_DIR')
import state as st
d = st.read()
print(f'       State: {d[\"status\"]}')
print(f'       Gate ready ✅')
"
echo ""

# ── Done ─────────────────────────────────────────────────────────────────
echo "========================================"
echo "  ✅ MOA Gate Installed!"
echo "========================================"
echo ""
echo "   📍 Plugin: $PLUGIN_DIR"
echo "   📍 Skill:  $SKILL_LINK"
echo "   📍 Hook:   $(git config --global core.hooksPath 2>/dev/null || echo '-')"
echo ""
echo "   Next step: reload Hermes → /reset"
echo "   Try:       /moa-status"
echo "   Council:   /moa-adviser --voices 5 --task \"...\""
echo "========================================"
