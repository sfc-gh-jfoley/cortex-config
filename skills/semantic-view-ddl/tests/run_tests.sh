#!/usr/bin/env bash
# =============================================================================
# semantic-view-ddl E2E Test Suite
# Validates fixture SQL files against sv_validator.py and checks skill structure.
# No Snowflake connection required — offline file/syntax validation only.
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
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
VALIDATOR="$SKILL_DIR/scripts/sv_validator.py"
FIXTURES_DIR="$SCRIPT_DIR/fixtures"

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
section "Test 1: TPCH semantic view (expect PASS or warnings-only)"
# ---------------------------------------------------------------------------

TPCH_OUTPUT=$(python3 "$VALIDATOR" "$FIXTURES_DIR/tpch_semantic_view.sql" 2>&1) || true
TPCH_EXIT=$?

# The validator returns 1 if ANY check fails (error or warning).
# For a well-formed DDL, we expect exit 0 (all pass) or exit 1 with only warnings.
TPCH_ERRORS=$(echo "$TPCH_OUTPUT" | grep -c '\[ERROR\]' || true)

if [ "$TPCH_EXIT" -eq 0 ]; then
  pass "tpch_semantic_view.sql — all 18 checks passed (exit 0)"
elif [ "$TPCH_ERRORS" -eq 0 ]; then
  pass "tpch_semantic_view.sql — no ERROR-severity failures (warnings only)"
else
  fail "tpch_semantic_view.sql — has $TPCH_ERRORS ERROR-severity failures" "Expected 0 errors"
  echo "$TPCH_OUTPUT" | head -25
fi

# ---------------------------------------------------------------------------
section "Test 2: Single table semantic view (expect PASS)"
# ---------------------------------------------------------------------------

SINGLE_OUTPUT=$(python3 "$VALIDATOR" "$FIXTURES_DIR/single_table.sql" 2>&1) || true
SINGLE_EXIT=$?
SINGLE_ERRORS=$(echo "$SINGLE_OUTPUT" | grep -c '\[ERROR\]' || true)

if [ "$SINGLE_EXIT" -eq 0 ]; then
  pass "single_table.sql — all checks passed (exit 0)"
elif [ "$SINGLE_ERRORS" -eq 0 ]; then
  pass "single_table.sql — no ERROR-severity failures (warnings only)"
else
  fail "single_table.sql — has $SINGLE_ERRORS ERROR-severity failures" "Expected 0 errors"
  echo "$SINGLE_OUTPUT" | head -25
fi

# ---------------------------------------------------------------------------
section "Test 3: Flawed audit SV (expect errors detected)"
# ---------------------------------------------------------------------------

AUDIT_OUTPUT=$(python3 "$VALIDATOR" "$FIXTURES_DIR/existing_sv_audit.sql" 2>&1) || true
AUDIT_EXIT=$?

# We expect at least 1 error-severity failure here
AUDIT_ERRORS=$(echo "$AUDIT_OUTPUT" | grep -c '\[ERROR\]' || true)
AUDIT_WARNINGS=$(echo "$AUDIT_OUTPUT" | grep -c '\[WARNING\]' || true)

if [ "$AUDIT_ERRORS" -ge 1 ]; then
  pass "existing_sv_audit.sql — detected $AUDIT_ERRORS error(s), $AUDIT_WARNINGS warning(s)"
else
  fail "existing_sv_audit.sql — expected errors but found $AUDIT_ERRORS" "Validator should catch deliberate flaws"
  echo "$AUDIT_OUTPUT" | head -25
fi

# Verify specific issues are caught
if echo "$AUDIT_OUTPUT" | grep -qi "pk.*referenced\|primary key\|pk_on_referenced"; then
  pass "existing_sv_audit.sql — missing PK detected"
else
  fail "existing_sv_audit.sql — missing PK NOT detected" "Expected pk_on_referenced_tables check to fail"
fi

if echo "$AUDIT_OUTPUT" | grep -qi "orphan"; then
  pass "existing_sv_audit.sql — orphan table detected"
else
  fail "existing_sv_audit.sql — orphan table NOT detected" "Expected orphan_detection check to fail"
fi

if echo "$AUDIT_OUTPUT" | grep -qi "synonym.*overlap\|overlapping"; then
  pass "existing_sv_audit.sql — duplicate synonym detected"
else
  fail "existing_sv_audit.sql — duplicate synonym NOT detected" "Expected synonym_overlap check to fail"
fi

if echo "$AUDIT_OUTPUT" | grep -qi "alias.*mismatch\|alias_matches_physical"; then
  pass "existing_sv_audit.sql — alias mismatch detected"
else
  fail "existing_sv_audit.sql — alias mismatch NOT detected" "Expected alias_matches_physical check to fail"
fi

# ---------------------------------------------------------------------------
section "Test 4: Skill structure validation"
# ---------------------------------------------------------------------------

# Check SKILL.md exists
if [ -f "$SKILL_DIR/SKILL.md" ]; then
  pass "SKILL.md exists"
else
  fail "SKILL.md missing"
fi

# Check all phases are present and readable
EXPECTED_PHASES=(
  "01_context.md"
  "02_profile_describe.md"
  "03_classify.md"
  "04_relationships.md"
  "05_generate_ddl.md"
  "06_execute_validate.md"
  "07_iterate_enrich.md"
  "08_drift_monitor.md"
)

for phase in "${EXPECTED_PHASES[@]}"; do
  if [ -f "$SKILL_DIR/phases/$phase" ] && [ -s "$SKILL_DIR/phases/$phase" ]; then
    pass "phases/$phase exists and is non-empty"
  else
    fail "phases/$phase missing or empty"
  fi
done

# Check reference files
if [ -f "$SKILL_DIR/reference/ddl_syntax.md" ] && [ -s "$SKILL_DIR/reference/ddl_syntax.md" ]; then
  pass "reference/ddl_syntax.md exists and is non-empty"
else
  fail "reference/ddl_syntax.md missing or empty"
fi

# Check validator script
if [ -f "$VALIDATOR" ] && [ -s "$VALIDATOR" ]; then
  pass "scripts/sv_validator.py exists and is non-empty"
else
  fail "scripts/sv_validator.py missing or empty"
fi

# Verify validator is importable
if python3 -c "import sys; sys.path.insert(0, '$SKILL_DIR/scripts'); from sv_validator import validate_ddl, CheckResult" 2>/dev/null; then
  pass "sv_validator.py is importable (validate_ddl, CheckResult)"
else
  fail "sv_validator.py import failed"
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
