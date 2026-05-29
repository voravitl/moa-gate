#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# AI-DLC Compass — One-shot Installer
# ============================================================================
# Installs as a separate Hermes plugin alongside MOA-Gate.
#
# Usage:
#   bash <(curl -sL https://raw.githubusercontent.com/voravitl/moa-gate/main/ai-dlc/scripts/install.sh)
#   cd moa-gate && bash ai-dlc/scripts/install.sh
#
# What it does:
#   1. Symlink ai-dlc plugin to ~/.hermes/plugins/ai-dlc
#   2. Create default steering rules in ~/wiki/steering/ (if not exist)
#   3. Create state directory ~/.hermes/ai-dlc/
#   4. Set INCEPTION phase as default
#   5. Show next steps
# ============================================================================

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
PLUGIN_SRC="$REPO_DIR/ai-dlc"
PLUGIN_LINK="$HOME/.hermes/plugins/ai-dlc"
STEERING_DIR="$HOME/wiki/steering"
STATE_DIR="$HOME/.hermes/ai-dlc"

echo "========================================"
echo "  AI-DLC Compass — Installer"
echo "========================================"

# ── Step 1: Symlink plugin ──────────────────────────────────────────
echo ""
echo "[1/5] \U0001f4e6 Plugin symlink..."
mkdir -p "$HOME/.hermes/plugins"
ln -sfn "$PLUGIN_SRC" "$PLUGIN_LINK"
echo "       \u2705 $PLUGIN_LINK \u2192 $PLUGIN_SRC"

# ── Step 2: Steering rules ──────────────────────────────────────────
echo ""
echo "[2/5] \U0001f4cb Steering rules..."
mkdir -p "$STEERING_DIR"

for rule_file in security.yaml architecture.yaml compliance.yaml; do
    target="$STEERING_DIR/$rule_file"
    if [ ! -f "$target" ]; then
        cp "$PLUGIN_SRC/steering/rules/$rule_file" "$target"
        echo "       \u2705 Created $target"
    else
        echo "       \u23ed\ufe0f Skipped (exists): $target"
    fi
done

# ── Step 3: State directory ─────────────────────────────────────────
echo ""
echo "[3/5] \U0001f4be State directory..."
mkdir -p "$STATE_DIR"
echo "       \u2705 $STATE_DIR"

# ── Step 4: Set initial phase ───────────────────────────────────────
echo ""
echo "[4/5] \U0001f3f0 Phase..."
PHASE_FILE="$STATE_DIR/phase.json"
if [ ! -f "$PHASE_FILE" ]; then
    python3 -c "
import json, os
from datetime import datetime, timezone
data = {'phase': 'INCEPTION', 'history': [{'from': None, 'to': 'INCEPTION', 'timestamp': datetime.now(timezone.utc).isoformat(), 'reason': 'Install'}], 'current_phase_start': datetime.now(timezone.utc).isoformat()}
with open(os.path.expanduser('$PHASE_FILE'), 'w') as f:
    json.dump(data, f, indent=2)
"
    echo "       \u2705 Phase set to INCEPTION"
else
    echo "       \u23ed\ufe0f Skipped (exists)"
fi

# ── Step 5: Verify ──────────────────────────────────────────────────
echo ""
echo "[5/5] \u2705 Verify..."
python3 -m py_compile "$PLUGIN_SRC/__init__.py" && echo "       \u2705 __init__.py OK"
python3 -m py_compile "$PLUGIN_SRC/steering/registry.py" && echo "       \u2705 registry.py OK"
python3 -m py_compile "$PLUGIN_SRC/engine/phase.py" && echo "       \u2705 phase.py OK"
python3 -m py_compile "$PLUGIN_SRC/engine/verifier.py" && echo "       \u2705 verifier.py OK"

echo ""
echo "========================================"
echo "  \u2705 AI-DLC Compass installed!"
echo "========================================"
echo ""
echo "What's next:"
echo "  1. Edit steering rules: $STEERING_DIR/"
echo "  2. /ai-dlc steer ls         (list rules)"
echo "  3. /ai-dlc phase            (check phase)"
echo ""
echo "Integration:"
echo "  - Works alongside MOA-Gate at ~/.hermes/plugins/moa-gate/"
echo "  - Steering violations auto-escalate to MOA-Gate Tier 2"
echo "  - Shared state: $STATE_DIR/"
echo ""
