#!/usr/bin/env bash
# =============================================================================
# cortex-agent-toolkit E2E Test Suite
# Validates fixture YAML specs and checks for customer data contamination.
# No Snowflake connection required — offline structural validation only.
# =============================================================================

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"

PASS_COUNT=0
FAIL_COUNT=0
TOTAL=0

pass() {
  PASS_COUNT=$((PASS_COUNT + 1))
  TOTAL=$((TOTAL + 1))
  echo -e "  ${GREEN}✓${RESET} $1"
}

fail() {
  FAIL_COUNT=$((FAIL_COUNT + 1))
  TOTAL=$((TOTAL + 1))
  echo -e "  ${RED}✗${RESET} $1"
  if [ -n "${2:-}" ]; then
    echo -e "    ${YELLOW}→ $2${RESET}"
  fi
}

section() {
  echo ""
  echo -e "${CYAN}${BOLD}[$1]${RESET}"
}

# ---------------------------------------------------------------------------
section "Test 1: Spec validation (validate_specs.py)"
# ---------------------------------------------------------------------------

VALIDATE_OUTPUT=$(python3 "$SCRIPT_DIR/validate_specs.py" 2>&1) || true
VALIDATE_EXIT=$?

echo "$VALIDATE_OUTPUT"
echo ""

if [ "$VALIDATE_EXIT" -eq 0 ]; then
  pass "validate_specs.py — all checks passed"
else
  fail "validate_specs.py — some checks failed (exit $VALIDATE_EXIT)"
fi

# ---------------------------------------------------------------------------
section "Test 2: Customer data contamination check"
# ---------------------------------------------------------------------------

# Search for known customer/internal references that should NOT be shipped
CONTAMINATION_PATTERNS="snowhouse\|DISH\|dish_network\|marcus.williams\|Marcus Williams\|CORA_EVAL\|cora_eval"

CONTAM_HITS=$(grep -ri "$CONTAMINATION_PATTERNS" "$PLUGIN_DIR/skills/" 2>/dev/null | grep -v "tests/" | grep -v ".pyc" || true)

if [ -z "$CONTAM_HITS" ]; then
  pass "No customer/internal data contamination in skills/"
else
  CONTAM_COUNT=$(echo "$CONTAM_HITS" | wc -l | tr -d ' ')
  fail "Found $CONTAM_COUNT potential contamination(s) in skills/" "Matches:"
  echo "$CONTAM_HITS" | head -10
fi

# Also check fixtures themselves are clean
FIXTURE_CONTAM=$(grep -ri "$CONTAMINATION_PATTERNS" "$SCRIPT_DIR/fixtures/" 2>/dev/null || true)

if [ -z "$FIXTURE_CONTAM" ]; then
  pass "No customer/internal data contamination in test fixtures"
else
  fail "Contamination found in test fixtures" "Fixtures should use TPCH/generic data only"
  echo "$FIXTURE_CONTAM" | head -5
fi

# ---------------------------------------------------------------------------
section "Summary"
# ---------------------------------------------------------------------------

echo ""
if [ "$FAIL_COUNT" -eq 0 ]; then
  echo -e "${GREEN}${BOLD}All $TOTAL tests passed.${RESET}"
  exit 0
else
  echo -e "${RED}${BOLD}$FAIL_COUNT/$TOTAL tests failed.${RESET}"
  exit 1
fi
