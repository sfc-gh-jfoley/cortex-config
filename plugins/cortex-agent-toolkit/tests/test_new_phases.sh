#!/usr/bin/env bash
# =============================================================================
# cortex-agent-ddl — New Phase Integration Tests
# Validates that new phase files (04b, 08) and reference files integrate
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
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"
SKILLS_DIR="$PLUGIN_DIR/skills"
DDL_DIR="$SKILLS_DIR/cortex-agent-ddl"
PHASES_DIR="$DDL_DIR/phases"
REFERENCE_DIR="$DDL_DIR/reference"

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
section "Test 1: Phase 04b — Tenant Isolation file exists and is non-empty"
# ---------------------------------------------------------------------------

PHASE_04_5="$PHASES_DIR/04b_tenant_isolation.md"
if [ -f "$PHASE_04_5" ] && [ -s "$PHASE_04_5" ]; then
  pass "phases/04b_tenant_isolation.md exists and is non-empty ($(wc -c < "$PHASE_04_5") bytes)"
else
  fail "phases/04b_tenant_isolation.md missing or empty" "Plan item 2: Add multitenant security phase"
fi

# ---------------------------------------------------------------------------
section "Test 2: Phase 04b — Contains required RAP patterns"
# ---------------------------------------------------------------------------

if [ -f "$PHASE_04_5" ]; then
  # Pattern A: user-per-tenant with CURRENT_USER()
  if grep -qi "CURRENT_USER" "$PHASE_04_5"; then
    pass "Phase 04b contains CURRENT_USER() pattern (Pattern A: user-per-tenant)"
  else
    fail "Phase 04b missing CURRENT_USER() pattern" "Plan requires Pattern A: user-per-tenant RAP on CURRENT_USER()"
  fi

  # Pattern B: role-per-tenant with CURRENT_ROLE()
  if grep -qi "CURRENT_ROLE" "$PHASE_04_5"; then
    pass "Phase 04b contains CURRENT_ROLE() pattern (Pattern B: role-per-tenant)"
  else
    fail "Phase 04b missing CURRENT_ROLE() pattern" "Plan requires Pattern B: role-per-tenant"
  fi

  # Pattern C: session attribute with SET_SYS_CONTEXT or is_immutable_session_attribute
  if grep -qi "SET_SYS_CONTEXT\|is_immutable_session_attribute" "$PHASE_04_5"; then
    pass "Phase 04b contains session attribute pattern (Pattern C)"
  else
    fail "Phase 04b missing session attribute pattern" "Plan requires Pattern C: SET_SYS_CONTEXT / is_immutable_session_attribute"
  fi

  # Entitlement table with MEMOIZABLE UDF
  if grep -qi "MEMOIZABLE" "$PHASE_04_5"; then
    pass "Phase 04b contains MEMOIZABLE UDF pattern"
  else
    fail "Phase 04b missing MEMOIZABLE UDF pattern" "Plan requires entitlement table pattern with MEMOIZABLE UDF"
  fi
else
  fail "Phase 04b does not exist — skipping content checks" "File must exist first"
  fail "(skipped) Pattern A check" "Depends on Phase 04b existing"
  fail "(skipped) Pattern B check" "Depends on Phase 04b existing"
  fail "(skipped) Pattern C check" "Depends on Phase 04b existing"
  fail "(skipped) MEMOIZABLE check" "Depends on Phase 04b existing"
fi

# ---------------------------------------------------------------------------
section "Test 3: Phase 08 — CI/CD Deploy file exists and is non-empty"
# ---------------------------------------------------------------------------

PHASE_08="$PHASES_DIR/08_cicd_deploy.md"
if [ -f "$PHASE_08" ] && [ -s "$PHASE_08" ]; then
  pass "phases/08_cicd_deploy.md exists and is non-empty ($(wc -c < "$PHASE_08") bytes)"
else
  fail "phases/08_cicd_deploy.md missing or empty" "Plan item 1: Add Agent CI/CD Deployment Phase"
fi

# ---------------------------------------------------------------------------
section "Test 4: Phase 08 — Contains required CI/CD patterns"
# ---------------------------------------------------------------------------

if [ -f "$PHASE_08" ]; then
  # GitHub Actions with snowflake-cli-action
  if grep -qi "snowflake-cli-action\|snowflakedb/snowflake-cli" "$PHASE_08"; then
    pass "Phase 08 references snowflake-cli-action for GitHub Actions"
  else
    fail "Phase 08 missing snowflake-cli-action reference" "Plan requires GitHub Actions workflow using snowflakedb/snowflake-cli-action@v2.0.2"
  fi

  # Service user / OIDC
  if grep -qi "WORKLOAD_IDENTITY\|OIDC\|TYPE = SERVICE\|TYPE=SERVICE" "$PHASE_08"; then
    pass "Phase 08 contains service user / OIDC pattern"
  else
    fail "Phase 08 missing service user / OIDC pattern" "Plan requires service user creation with WORKLOAD_IDENTITY and OIDC"
  fi

  # snow sql for CREATE AGENT FROM SPECIFICATION
  if grep -qi "snow sql\|CREATE AGENT FROM SPECIFICATION" "$PHASE_08"; then
    pass "Phase 08 references snow sql or CREATE AGENT FROM SPECIFICATION"
  else
    fail "Phase 08 missing snow sql / CREATE AGENT FROM SPECIFICATION" "Plan requires snow sql to execute CREATE AGENT FROM SPECIFICATION from Git-tracked spec"
  fi

  # Environment promotion (DEV/TEST/PROD)
  if grep -qi "DEV.*PROD\|environment.*promot\|promotion" "$PHASE_08"; then
    pass "Phase 08 contains environment promotion pattern (DEV → PROD)"
  else
    fail "Phase 08 missing environment promotion pattern" "Plan requires DEV → TEST → PROD with parameterized FQNs"
  fi

  # Rollback via GET_DDL
  if grep -qi "GET_DDL\|rollback" "$PHASE_08"; then
    pass "Phase 08 contains rollback / GET_DDL pattern"
  else
    fail "Phase 08 missing rollback / GET_DDL pattern" "Plan requires rollback via GET_DDL(AGENT, ...) capture before deploy"
  fi

  # Agent drift detection
  if grep -qi "drift\|DESCRIBE.*spec\|spec.*DESCRIBE" "$PHASE_08"; then
    pass "Phase 08 contains drift detection pattern"
  else
    fail "Phase 08 missing drift detection pattern" "Plan requires agent drift detection (compare live DESCRIBE vs committed spec)"
  fi
else
  fail "Phase 08 does not exist — skipping content checks" "File must exist first"
  fail "(skipped) snowflake-cli-action check" "Depends on Phase 08 existing"
  fail "(skipped) OIDC check" "Depends on Phase 08 existing"
  fail "(skipped) snow sql check" "Depends on Phase 08 existing"
  fail "(skipped) env promotion check" "Depends on Phase 08 existing"
  fail "(skipped) rollback check" "Depends on Phase 08 existing"
  fail "(skipped) drift detection check" "Depends on Phase 08 existing"
fi

# ---------------------------------------------------------------------------
section "Test 5: Reference — CI/CD patterns file"
# ---------------------------------------------------------------------------

CICD_REF="$REFERENCE_DIR/cicd_patterns.md"
if [ -f "$CICD_REF" ] && [ -s "$CICD_REF" ]; then
  pass "reference/cicd_patterns.md exists and is non-empty ($(wc -c < "$CICD_REF") bytes)"
else
  fail "reference/cicd_patterns.md missing or empty" "Plan requires reusable YAML templates (GitHub/GitLab/Azure)"
fi

# Check it includes multi-platform templates
if [ -f "$CICD_REF" ]; then
  PLATFORMS_FOUND=0
  for platform in "GitHub" "GitLab" "Azure"; do
    if grep -qi "$platform" "$CICD_REF"; then
      PLATFORMS_FOUND=$((PLATFORMS_FOUND + 1))
    fi
  done
  if [ "$PLATFORMS_FOUND" -ge 2 ]; then
    pass "reference/cicd_patterns.md covers $PLATFORMS_FOUND/3 CI/CD platforms"
  else
    fail "reference/cicd_patterns.md covers only $PLATFORMS_FOUND/3 platforms" "Plan requires GitHub/GitLab/Azure templates"
  fi
fi

# ---------------------------------------------------------------------------
section "Test 6: Agent spec reference — variables block documented"
# ---------------------------------------------------------------------------

SPEC_REF="$REFERENCE_DIR/agent_spec_syntax.md"
if [ -f "$SPEC_REF" ]; then
  # Check for variables block documentation
  if grep -qi "variables\|is_immutable_session_attribute" "$SPEC_REF"; then
    pass "reference/agent_spec_syntax.md documents the variables block"
  else
    fail "reference/agent_spec_syntax.md missing variables block documentation" \
         "Plan requires documenting the variables block in DATA_AGENT_RUN payload"
  fi
else
  fail "reference/agent_spec_syntax.md not found" "Required reference file is missing entirely"
fi

# ---------------------------------------------------------------------------
section "Test 7: SKILL.md — Phase reference table includes new phases"
# ---------------------------------------------------------------------------

SKILL_MD="$DDL_DIR/SKILL.md"
if [ -f "$SKILL_MD" ]; then
  # Check Phase 4b is listed in the phase table or workflow
  if grep -qi "04b\|4b.*tenant\|tenant.*isol" "$SKILL_MD"; then
    pass "SKILL.md references Phase 4b (tenant isolation)"
  else
    fail "SKILL.md does not reference Phase 4b" "SKILL.md phase reference table must include Phase 4b"
  fi

  # Check Phase 8 is listed
  if grep -qi "08.*ci\|phase.*8.*deploy\|cicd\|ci/cd" "$SKILL_MD"; then
    pass "SKILL.md references Phase 8 (CI/CD deploy)"
  else
    fail "SKILL.md does not reference Phase 8" "SKILL.md phase reference table must include Phase 8"
  fi
else
  fail "SKILL.md not found" "Required skill manifest is missing"
fi

# ---------------------------------------------------------------------------
section "Test 8: Phase 05 self-check — MTT warning integration"
# ---------------------------------------------------------------------------

PHASE_05="$PHASES_DIR/05_self_check.md"
if [ -f "$PHASE_05" ]; then
  # Check that Phase 5 references multitenancy / tenant check
  if grep -qi "tenant\|multi.?tenant\|MTT\|RAP.*base.*table\|Phase 4b" "$PHASE_05"; then
    pass "Phase 05 self-check references multitenancy / tenant isolation"
  else
    fail "Phase 05 self-check missing MTT warning" \
         "Plan requires: WARN 'If agent serves multiple tenants, confirm RAP exists on base tables'"
  fi
else
  fail "Phase 05 self-check not found" "Required phase file is missing"
fi

# ---------------------------------------------------------------------------
section "Test 9: Phase numbering consistency — 04b sits between 04 and 05"
# ---------------------------------------------------------------------------

# Verify phase files maintain consistent ordering: 04 < 04b < 05
PHASE_04="$PHASES_DIR/04_assemble_spec.md"
if [ -f "$PHASE_04" ] && [ -f "$PHASE_04_5" ] && [ -f "$PHASE_05" ]; then
  # All three exist — ordering is structural (filenames sort correctly)
  pass "Phase ordering maintained: 04 → 04b → 05 (all files exist)"

  # Check Phase 04b has proper YAML frontmatter with name field
  if head -5 "$PHASE_04_5" | grep -q "^---"; then
    pass "Phase 04b has YAML frontmatter"
  else
    fail "Phase 04b missing YAML frontmatter" "All phase files use YAML frontmatter (---) with name/description"
  fi
else
  if [ ! -f "$PHASE_04" ]; then
    fail "Phase 04 missing — cannot verify ordering" "04_assemble_spec.md must exist"
  fi
  if [ ! -f "$PHASE_04_5" ]; then
    fail "Phase 04b missing — cannot verify ordering" "04b_tenant_isolation.md must exist"
  fi
  if [ ! -f "$PHASE_05" ]; then
    fail "Phase 05 missing — cannot verify ordering" "05_self_check.md must exist"
  fi
fi

# ---------------------------------------------------------------------------
section "Test 10: Phase 07 — Mentions Phase 08 CI/CD handoff"
# ---------------------------------------------------------------------------

PHASE_07="$PHASES_DIR/07_test_harden.md"
if [ -f "$PHASE_07" ]; then
  if grep -qi "Phase 8\|phase.*08\|cicd\|ci/cd.*deploy\|production.*deploy" "$PHASE_07"; then
    pass "Phase 07 mentions Phase 08 handoff for CI/CD deployment"
  else
    fail "Phase 07 does not mention Phase 08 handoff" \
         "Plan requires: Update Phase 7 handoff menu to include CI/CD deployment option"
  fi
else
  fail "Phase 07 not found" "07_test_harden.md must exist"
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
