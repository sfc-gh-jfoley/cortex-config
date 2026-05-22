#!/usr/bin/env bash
# =============================================================================
# semantic-view-ddl — Multitenant Governance Integration Tests
# Validates that Phase 03 RAP templates and new reference file integrate
# with the existing skill structure.
# TDD RED PHASE: These tests should FAIL until implementation is complete.
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
PHASES_DIR="$SKILL_DIR/phases"
REFERENCE_DIR="$SKILL_DIR/reference"

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
section "Test 1: Phase 03 — RAP templates exist (not just delegation)"
# ---------------------------------------------------------------------------

PHASE_03="$PHASES_DIR/03_classify.md"
if [ -f "$PHASE_03" ]; then
  # Check for 3 concrete RAP patterns (user/role/session-attr)
  RAP_PATTERNS=0

  # Pattern A: user-per-tenant (CURRENT_USER)
  if grep -qi "CURRENT_USER" "$PHASE_03"; then
    RAP_PATTERNS=$((RAP_PATTERNS + 1))
    pass "Phase 03 contains CURRENT_USER() RAP pattern (Pattern A)"
  else
    fail "Phase 03 missing CURRENT_USER() RAP pattern" "Plan requires 3 RAP patterns as templates"
  fi

  # Pattern B: role-per-tenant (CURRENT_ROLE)
  if grep -qi "CURRENT_ROLE" "$PHASE_03"; then
    RAP_PATTERNS=$((RAP_PATTERNS + 1))
    pass "Phase 03 contains CURRENT_ROLE() RAP pattern (Pattern B)"
  else
    fail "Phase 03 missing CURRENT_ROLE() RAP pattern" "Plan requires Pattern B: role-per-tenant"
  fi

  # Pattern C: session attribute (SET_SYS_CONTEXT or immutable_session_attribute)
  if grep -qi "SET_SYS_CONTEXT\|session.attribute\|immutable_session_attribute" "$PHASE_03"; then
    RAP_PATTERNS=$((RAP_PATTERNS + 1))
    pass "Phase 03 contains session attribute RAP pattern (Pattern C)"
  else
    fail "Phase 03 missing session attribute RAP pattern" "Plan requires Pattern C: session attribute with SET_SYS_CONTEXT"
  fi

  if [ "$RAP_PATTERNS" -ge 3 ]; then
    pass "Phase 03 has all 3 RAP patterns (${RAP_PATTERNS}/3)"
  else
    fail "Phase 03 only has ${RAP_PATTERNS}/3 RAP patterns" "All 3 patterns required: user/role/session-attr"
  fi
else
  fail "Phase 03 not found" "03_classify.md must exist"
fi

# ---------------------------------------------------------------------------
section "Test 2: Phase 03 Step 3.4 — RAP handler provides informational pattern guidance"
# ---------------------------------------------------------------------------

if [ -f "$PHASE_03" ]; then
  # Plan (revised per G6): "informational RAP pattern summaries with one-liner descriptions
  # and 'which to pick' decision tree. Still delegates to data-governance for actual DDL."
  # Check for pattern summaries with example predicates (not full CREATE DDL — that's data-governance's job)
  if grep -qi "Pattern A\|Pattern B\|Pattern C\|User-per-tenant\|Role-per-tenant\|Session attribute" "$PHASE_03"; then
    pass "Phase 03 Step 3.4 contains informational RAP pattern decision tree"
  else
    fail "Phase 03 Step 3.4 missing RAP pattern guidance" \
         "Plan: 'Informational RAP pattern summaries with decision tree, delegates to data-governance for DDL'"
  fi
fi

# ---------------------------------------------------------------------------
section "Test 3: Phase 07 — MTT cross-reference to cortex-agent-ddl Phase 4b"
# ---------------------------------------------------------------------------

PHASE_07="$PHASES_DIR/07_iterate_enrich.md"
if [ -f "$PHASE_07" ]; then
  if grep -qi "Phase 4b\|cortex-agent-ddl\|tenant.*isolation.*pattern\|MTT.*agent" "$PHASE_07"; then
    pass "Phase 07 cross-references cortex-agent-ddl Phase 4b for MTT agents"
  else
    fail "Phase 07 missing MTT → cortex-agent-ddl Phase 4b cross-reference" \
         "Plan: 'If IS_MTT=true, downstream Cortex Agent MUST use matching isolation pattern (see cortex-agent-ddl Phase 4b)'"
  fi
else
  fail "Phase 07 not found" "07_iterate_enrich.md must exist"
fi

# ---------------------------------------------------------------------------
section "Test 4: Reference — multitenant_sv_guidance.md exists"
# ---------------------------------------------------------------------------

MT_REF="$REFERENCE_DIR/multitenant_sv_guidance.md"
if [ -f "$MT_REF" ] && [ -s "$MT_REF" ]; then
  pass "reference/multitenant_sv_guidance.md exists and is non-empty ($(wc -c < "$MT_REF") bytes)"
else
  fail "reference/multitenant_sv_guidance.md missing or empty" \
       "Plan requires: How RAPs on base tables propagate through SVs to agents"
fi

# ---------------------------------------------------------------------------
section "Test 5: Reference — multitenant_sv_guidance.md content quality"
# ---------------------------------------------------------------------------

if [ -f "$MT_REF" ]; then
  # Must explain RAP propagation through SVs
  if grep -qi "propagat\|RAP.*SV\|SV.*RAP\|row access.*semantic\|semantic.*row access" "$MT_REF"; then
    pass "Multitenant reference explains RAP propagation through SVs"
  else
    fail "Multitenant reference missing RAP-through-SV propagation explanation" \
         "Core content: How RAPs on base tables propagate through SVs to agents"
  fi

  # Must mention agents
  if grep -qi "agent\|DATA_AGENT_RUN" "$MT_REF"; then
    pass "Multitenant reference covers agent interaction"
  else
    fail "Multitenant reference missing agent interaction coverage" \
         "Must explain how RAPs interact with Cortex Analyst SQL generation through the SV"
  fi
else
  fail "(skipped) Content checks — file does not exist" "Create reference/multitenant_sv_guidance.md first"
  fail "(skipped) Agent coverage check" "Create reference/multitenant_sv_guidance.md first"
fi

# ---------------------------------------------------------------------------
section "Test 6: Existing skill structure integrity after changes"
# ---------------------------------------------------------------------------

# Verify all original phases still exist and are non-empty
ORIGINAL_PHASES=(
  "01_context.md"
  "02_profile_describe.md"
  "03_classify.md"
  "04_relationships.md"
  "05_generate_ddl.md"
  "06_execute_validate.md"
  "07_iterate_enrich.md"
  "08_drift_monitor.md"
)

ALL_ORIGINAL_OK=true
for phase in "${ORIGINAL_PHASES[@]}"; do
  if [ -f "$PHASES_DIR/$phase" ] && [ -s "$PHASES_DIR/$phase" ]; then
    : # silent pass for existing files
  else
    fail "Original phase $phase missing or empty after changes" "Existing skill structure must be preserved"
    ALL_ORIGINAL_OK=false
  fi
done

if $ALL_ORIGINAL_OK; then
  pass "All 8 original phases preserved and non-empty"
fi

# Verify original reference file still exists
if [ -f "$REFERENCE_DIR/ddl_syntax.md" ] && [ -s "$REFERENCE_DIR/ddl_syntax.md" ]; then
  pass "Original reference/ddl_syntax.md preserved"
else
  fail "reference/ddl_syntax.md missing or empty" "Existing reference files must be preserved"
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
