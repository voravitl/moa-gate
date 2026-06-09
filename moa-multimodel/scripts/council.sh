#!/bin/bash
# MOA Multi-Model Council runner.
# Runs 3 real models (claude + codex + agy) as adversarial voices on a diff,
# extracts verdicts, writes PR comments, and updates moa-gate state.json.
#
# Usage: council.sh <diff-file> [pr-number]
#
# Output (stdout): human-readable summary
# Output (files):  /tmp/pr-<N>-{architect,skeptic,pragmatist}.md
#                  /tmp/moa-status (KEY=VALUE lines for state file)
#
# Env:
#   MOA_GATE_PLUGIN_PATH — path to moa-gate plugin (defaults to
#                          sibling dir, then ~/.hermes/plugins/moa-gate)
set -e

DIFF=${1:?"Usage: $0 <diff-file> [pr-number]"}
PR=${2:-"manual"}

# Resolve moa-gate plugin path: env > sibling dir > ~/.hermes
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$PLUGIN_ROOT")"
MOA_GATE_PLUGIN_PATH="${MOA_GATE_PLUGIN_PATH:-}"
if [ -z "$MOA_GATE_PLUGIN_PATH" ]; then
  if [ -f "$REPO_ROOT/state.py" ]; then
    MOA_GATE_PLUGIN_PATH="$REPO_ROOT"
  elif [ -f "$HOME/.hermes/plugins/moa-gate/state.py" ]; then
    MOA_GATE_PLUGIN_PATH="$HOME/.hermes/plugins/moa-gate"
  fi
fi

# Rate-limit patterns (apply to stderr or first 5 lines of stdout only,
# to avoid false positives from words like "throttle" in code review)
RATE_LIMIT_PATTERNS='^\s*error.*rate limit|^\s*error.*429|^\s*error.*too many requests|^\s*error.*quota exceeded|HTTP.*429|^rate limit exceeded|^429 Too Many Requests'

is_rate_limit() {
  local out=$1
  echo "$out" | head -5 | grep -qiE "$RATE_LIMIT_PATTERNS"
}

is_empty() {
  local out=$1
  [ -z "$out" ] || [ "$(echo -n "$out" | wc -c)" -lt 10 ]
}

# Run a voice CLI, classify result, write verdict file
run_voice() {
  local voice=$1
  local cmd_file=$2
  local verdict_file="/tmp/pr-${PR}-${voice}.md"

  if [ ! -f "$cmd_file" ]; then
    echo "SKIPPED|$voice|cmd_file_missing" >> /tmp/moa-status
    return 0
  fi

  local out
  out=$(bash "$cmd_file" 2>&1)
  local exit_code=$?

  if [ $exit_code -ne 0 ]; then
    if is_rate_limit "$out"; then
      echo "=== RATE LIMIT on $voice (waiting 60s, retry ONCE) ==="
      sleep 60
      out=$(bash "$cmd_file" 2>&1)
      exit_code=$?
      if [ $exit_code -ne 0 ] || is_empty "$out" || is_rate_limit "$out"; then
        echo "ESCALATED|$voice|rate_limit_after_retry" >> /tmp/moa-status
        return 0
      fi
    else
      echo "HARD_FAIL|$voice|exit_$exit_code" >> /tmp/moa-status
      return 0
    fi
  fi

  if is_empty "$out"; then
    echo "EMPTY|$voice|no_output" >> /tmp/moa-status
    return 0
  fi

  # Extract verdict
  local verdict
  if echo "$out" | grep -qiE "REQUEST_CHANGES"; then
    verdict="REQUEST_CHANGES"
  elif echo "$out" | tail -20 | grep -qiE "APPROVE"; then
    verdict="APPROVE"
  else
    verdict="UNCLEAR"
  fi

  # Write verdict file (full body, not just verdict)
  {
    echo "## MOA $(echo $voice | awk '{print toupper(substr($0,1,1)) substr($0,2)}') Review"
    echo
    echo "$out" | tail -50
    echo
    echo "**Verdict: $verdict**"
  } > "$verdict_file"

  echo "$verdict|$voice" >> /tmp/moa-status
}

# ── Entry ───────────────────────────────────────────────────────────
rm -f /tmp/moa-status
touch /tmp/moa-status

# Run all 3 voices
run_voice architect /tmp/claude-cmd.sh
run_voice skeptic   /tmp/codex-cmd.sh
run_voice pragmatist /tmp/agy-cmd.sh

# ── Compose verdict ────────────────────────────────────────────────
approve_count=0
escalated_count=0
total_substantive=0
verdict_summary=""

while IFS='|' read -r verdict voice; do
  case "$verdict" in
    APPROVE)
      approve_count=$((approve_count + 1))
      total_substantive=$((total_substantive + 1))
      verdict_summary="${verdict_summary}${voice}=APPROVE "
      ;;
    REQUEST_CHANGES)
      total_substantive=$((total_substantive + 1))
      verdict_summary="${verdict_summary}${voice}=REQUEST_CHANGES "
      ;;
    ESCALATED|EMPTY|HARD_FAIL|SKIPPED)
      escalated_count=$((escalated_count + 1))
      verdict_summary="${verdict_summary}${voice}=ESCALATED "
      ;;
  esac
done < /tmp/moa-status

echo ""
echo "=== MOA Council Summary (PR #${PR}) ==="
echo "Substantive verdicts: ${total_substantive}/3"
echo "Approvals: ${approve_count}"
echo "Escalated/empty: ${escalated_count}"
echo "Verdicts: ${verdict_summary}"

# ── Write moa-gate state.json if 2/3 approve ──────────────────────
if [ $approve_count -ge 2 ] && [ $total_substantive -ge 2 ]; then
  echo ""
  echo "=== Writing moa-gate state.json (auto-approve) ==="

  if [ -z "$MOA_GATE_PLUGIN_PATH" ] || [ ! -f "$MOA_GATE_PLUGIN_PATH/state.py" ]; then
    echo "⚠️  Skipping state update — moa-gate plugin not found (set MOA_GATE_PLUGIN_PATH)"
  else
    approved_by=$(echo "$verdict_summary" | tr ' ' '\n' | grep "=APPROVE" | cut -d= -f1 | tr '\n' ',' | sed 's/,$//')
    MOA_GATE_PLUGIN_PATH="$MOA_GATE_PLUGIN_PATH" \
    APPROVED_BY="$approved_by" \
    APPROVE_COUNT="$approve_count" \
    TOTAL_SUB="$total_substantive" \
    PR_NUM="$PR" \
    python3 - <<'PYEOF'
import os, sys
sys.path.insert(0, os.environ["MOA_GATE_PLUGIN_PATH"])
try:
    import state as st
    r = st.approve(
        approved_by=os.environ["APPROVED_BY"].split(","),
        reason=f"MOA Multi-Model Council {os.environ['APPROVE_COUNT']}/{os.environ['TOTAL_SUB']} APPROVE for PR #{os.environ['PR_NUM']} (auto-triggered)",
        session_id="",
        ttl_seconds=3600,
    )
    print("✅ state.json updated:", r.get("status"), r.get("expires_at"))
except Exception as exc:
    print("⚠️  state update failed:", exc)
    sys.exit(1)
PYEOF
  fi

elif [ $total_substantive -lt 2 ]; then
  echo ""
  echo "🛑 Less than 2 substantive voices — blocking (need manual review)"
  exit_code=2
fi

# ── Post PR comments if PR number provided ─────────────────────────
if [ "$PR" != "manual" ] && command -v gh >/dev/null 2>&1; then
  for voice in architect skeptic pragmatist; do
    f="/tmp/pr-${PR}-${voice}.md"
    if [ -f "$f" ]; then
      gh pr comment "$PR" --body-file "$f" 2>/dev/null || true
      case "$voice" in
        architect) gh pr edit "$PR" --add-label moa-claude-approved 2>/dev/null || true ;;
        skeptic)   gh pr edit "$PR" --add-label moa-codex-approved 2>/dev/null || true ;;
        pragmatist) gh pr edit "$PR" --add-label moa-agy-approved 2>/dev/null || true ;;
      esac
    fi
  done
  echo "Posted ${total_substantive} PR comment(s) and labels"
fi

exit 0
