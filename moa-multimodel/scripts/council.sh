#!/bin/bash
# MOA Multi-Model Council runner.
# Runs 3 real models (claude + codex + agy) as adversarial voices on a diff,
# extracts verdicts, writes PR comments, and updates moa-gate state.json.
#
# Usage: council.sh <diff-file> [pr-number]
#
# Output (stdout): human-readable summary
# Output (files):  $RUN_DIR/pr-<N>-{architect,skeptic,pragmatist}.md
#                  $RUN_DIR/moa-status (VERDICT|voice[|reason] lines)
#
# Env:
#   MOA_RUN_DIR          — per-run private dir holding voice cmd files;
#                          created via mktemp -d if unset
#   MOA_GATE_PLUGIN_PATH — path to moa-gate plugin (defaults to
#                          sibling dir, then ~/.hermes/plugins/moa-gate)
set -e

DIFF=${1:?"Usage: $0 <diff-file> [pr-number]"}
PR=${2:-"manual"}

# Per-run private working dir — fixed /tmp paths collide between
# concurrent runs and are pre-creatable/symlinkable by other local users
# (the cmd files in it get executed via bash)
RUN_DIR="${MOA_RUN_DIR:-}"
if [ -z "$RUN_DIR" ]; then
  RUN_DIR=$(mktemp -d "${TMPDIR:-/tmp}/moa-council.XXXXXX")
  trap 'rm -rf "$RUN_DIR"' EXIT
fi
chmod 700 "$RUN_DIR"
STATUS_FILE="$RUN_DIR/moa-status"

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
  local verdict_file="$RUN_DIR/pr-${PR}-${voice}.md"

  if [ ! -f "$cmd_file" ]; then
    echo "SKIPPED|$voice|cmd_file_missing" >> "$STATUS_FILE"
    return 0
  fi

  # `|| exit_code=$?` keeps set -e from killing the script on voice failure
  local out
  local exit_code=0
  out=$(bash "$cmd_file" 2>&1) || exit_code=$?

  if [ $exit_code -ne 0 ]; then
    if is_rate_limit "$out"; then
      echo "=== RATE LIMIT on $voice (waiting 60s, retry ONCE) ==="
      sleep 60
      exit_code=0
      out=$(bash "$cmd_file" 2>&1) || exit_code=$?
      if [ $exit_code -ne 0 ] || is_empty "$out" || is_rate_limit "$out"; then
        echo "ESCALATED|$voice|rate_limit_after_retry" >> "$STATUS_FILE"
        return 0
      fi
    else
      echo "HARD_FAIL|$voice|exit_$exit_code" >> "$STATUS_FILE"
      return 0
    fi
  fi

  if is_empty "$out"; then
    echo "EMPTY|$voice|no_output" >> "$STATUS_FILE"
    return 0
  fi

  # Extract verdict — last standalone keyword wins, so an echoed prompt
  # ("Return ONLY: APPROVE or REQUEST_CHANGES") earlier in the output
  # cannot override the model's final verdict. -w prevents substring
  # hits like DISAPPROVE.
  local verdict
  verdict=$(echo "$out" | grep -woiE 'REQUEST_CHANGES|APPROVED?' | tail -1 | tr '[:lower:]' '[:upper:]')
  case "$verdict" in
    APPROVED) verdict="APPROVE" ;;
    APPROVE|REQUEST_CHANGES) ;;
    *) verdict="UNCLEAR" ;;
  esac

  # Write verdict file (full body, not just verdict)
  {
    echo "## MOA $(echo "$voice" | awk '{print toupper(substr($0,1,1)) substr($0,2)}') Review"
    echo
    echo "$out" | tail -50
    echo
    echo "**Verdict: $verdict**"
  } > "$verdict_file"

  echo "$verdict|$voice" >> "$STATUS_FILE"
}

# ── Entry ───────────────────────────────────────────────────────────
exit_code=0
rm -f "$STATUS_FILE"
touch "$STATUS_FILE"

# Run all 3 voices
run_voice architect "$RUN_DIR/claude-cmd.sh"
run_voice skeptic   "$RUN_DIR/codex-cmd.sh"
run_voice pragmatist "$RUN_DIR/agy-cmd.sh"

# ── Compose verdict ────────────────────────────────────────────────
approve_count=0
escalated_count=0
total_substantive=0
safety_dissent=0
verdict_summary=""

while IFS='|' read -r verdict voice _; do
  case "$verdict" in
    APPROVE)
      approve_count=$((approve_count + 1))
      total_substantive=$((total_substantive + 1))
      verdict_summary="${verdict_summary}${voice}=APPROVE "
      ;;
    REQUEST_CHANGES)
      total_substantive=$((total_substantive + 1))
      verdict_summary="${verdict_summary}${voice}=REQUEST_CHANGES "
      # Mirror moa-gate SAFETY_ROLES: dissent from the skeptic voice
      # forces manual review regardless of the approval count
      if [ "$voice" = "skeptic" ]; then
        safety_dissent=1
      fi
      ;;
    UNCLEAR)
      escalated_count=$((escalated_count + 1))
      verdict_summary="${verdict_summary}${voice}=UNCLEAR "
      ;;
    ESCALATED|EMPTY|HARD_FAIL|SKIPPED)
      escalated_count=$((escalated_count + 1))
      verdict_summary="${verdict_summary}${voice}=ESCALATED "
      ;;
  esac
done < "$STATUS_FILE"

echo ""
echo "=== MOA Council Summary (PR #${PR}) ==="
echo "Run dir: ${RUN_DIR}"
echo "Substantive verdicts: ${total_substantive}/3"
echo "Approvals: ${approve_count}"
echo "Escalated/empty: ${escalated_count}"
echo "Verdicts: ${verdict_summary}"

# ── Write moa-gate state.json if 2/3 approve (no safety dissent) ──
if [ $approve_count -ge 2 ] && [ $total_substantive -ge 2 ] && [ $safety_dissent -eq 0 ]; then
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
    python3 - <<'PYEOF' || echo "⚠️  Continuing despite state update failure"
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
elif [ $safety_dissent -eq 1 ]; then
  echo ""
  echo "⚠️  Skeptic dissent (safety role) — auto-approve withheld, manual review required"
fi

# ── Post PR comments if PR number provided ─────────────────────────
if [ "$PR" != "manual" ] && command -v gh >/dev/null 2>&1; then
  for voice in architect skeptic pragmatist; do
    f="$RUN_DIR/pr-${PR}-${voice}.md"
    if [ -f "$f" ]; then
      gh pr comment "$PR" --body-file "$f" 2>/dev/null || true
      # Label only on an actual APPROVE — a REQUEST_CHANGES/UNCLEAR
      # verdict must not get a "*-approved" label
      if grep -qxF '**Verdict: APPROVE**' "$f"; then
        case "$voice" in
          architect) gh pr edit "$PR" --add-label moa-claude-approved 2>/dev/null || true ;;
          skeptic)   gh pr edit "$PR" --add-label moa-codex-approved 2>/dev/null || true ;;
          pragmatist) gh pr edit "$PR" --add-label moa-agy-approved 2>/dev/null || true ;;
        esac
      fi
    fi
  done
  echo "Posted ${total_substantive} PR comment(s) and labels"
fi

exit "$exit_code"
