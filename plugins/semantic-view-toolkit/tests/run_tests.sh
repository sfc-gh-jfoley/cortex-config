#!/usr/bin/env bash
# semantic-view-toolkit test suite
# Run: bash tests/run_tests.sh
set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0
FAIL=0

pass() { ((PASS++)); echo "  ✓ $1"; }
fail() { ((FAIL++)); echo "  ✗ $1"; }

echo "=== semantic-view-toolkit test suite ==="
echo "Plugin dir: $PLUGIN_DIR"
echo ""

# ─── Test 1: Plugin structure ───────────────────────────────────────────
echo "## Structure tests"

[ -f "$PLUGIN_DIR/SKILL.md" ] && pass "Router SKILL.md exists" || fail "Router SKILL.md missing"
[ -f "$PLUGIN_DIR/README.md" ] && pass "README.md exists" || fail "README.md missing"
[ -f "$PLUGIN_DIR/PREREQUISITES.md" ] && pass "PREREQUISITES.md exists" || fail "PREREQUISITES.md missing"
[ -f "$PLUGIN_DIR/CUSTOMER_GUIDE.md" ] && pass "CUSTOMER_GUIDE.md exists" || fail "CUSTOMER_GUIDE.md missing"

# ─── Test 2: All 9 skills have SKILL.md ─────────────────────────────────
echo ""
echo "## Skill SKILL.md tests"

SKILLS="sv-discovery sv-ddl sv-audit sv-evaluation sv-optimization sv-gepa-optimizer sv-watch sv-composer vqr-generator"
for skill in $SKILLS; do
    [ -f "$PLUGIN_DIR/skills/$skill/SKILL.md" ] && pass "$skill/SKILL.md" || fail "$skill/SKILL.md missing"
done

# ─── Test 3: All 11 references exist ────────────────────────────────────
echo ""
echo "## References tests"

REFS="relationship-detection confidence-scoring account-usage-patterns ddl-syntax mutation-operators convergence-criteria tournament-rules mini-batch-strategy eval-polling queryable-objects composable-sv-patterns"
for ref in $REFS; do
    [ -f "$PLUGIN_DIR/references/$ref.md" ] && pass "references/$ref.md" || fail "references/$ref.md missing"
done

# ─── Test 4: All 5 scripts exist and compile ────────────────────────────
echo ""
echo "## Scripts tests"

SCRIPTS="population_state.py tournament.py sample_batch.py mutate.py build_sv_ddl.py"
for script in $SCRIPTS; do
    if [ -f "$PLUGIN_DIR/scripts/$script" ]; then
        if python3 -c "import py_compile; py_compile.compile('$PLUGIN_DIR/scripts/$script', doraise=True)" 2>/dev/null; then
            pass "scripts/$script compiles"
        else
            fail "scripts/$script has syntax errors"
        fi
    else
        fail "scripts/$script missing"
    fi
done

# ─── Test 5: sv-ddl has phases ──────────────────────────────────────────
echo ""
echo "## Phase file tests"

DDL_PHASES="01_context 02_profile_describe 03_classify 04_relationships 05_generate_ddl 06_execute_validate 07_iterate_enrich 08_drift_monitor"
for phase in $DDL_PHASES; do
    [ -f "$PLUGIN_DIR/skills/sv-ddl/phases/$phase.md" ] && pass "sv-ddl/phases/$phase.md" || fail "sv-ddl/phases/$phase.md missing"
done

DISCOVERY_PHASES="01_connect_scope 02_scan 03_analyze 04_recommend 05_handoff"
for phase in $DISCOVERY_PHASES; do
    [ -f "$PLUGIN_DIR/skills/sv-discovery/phases/$phase.md" ] && pass "sv-discovery/phases/$phase.md" || fail "sv-discovery/phases/$phase.md missing"
done

AUDIT_PHASES="10_audit_connect 11_audit_scan 12_audit_recommend"
for phase in $AUDIT_PHASES; do
    [ -f "$PLUGIN_DIR/skills/sv-audit/phases/$phase.md" ] && pass "sv-audit/phases/$phase.md" || fail "sv-audit/phases/$phase.md missing"
done

# ─── Test 6: Router contains all skill routes ────────────────────────────
echo ""
echo "## Router routing table tests"

for skill in $SKILLS; do
    if grep -q "$skill" "$PLUGIN_DIR/SKILL.md"; then
        pass "Router references $skill"
    else
        fail "Router missing reference to $skill"
    fi
done

# ─── Test 7: Skill-loader registry updated ──────────────────────────────
echo ""
echo "## Skill-loader registry tests"

LOADER="$HOME/.snowflake/cortex/skills/skill-loader/SKILL.md"
if [ -f "$LOADER" ]; then
    grep -q "semantic-view-toolkit" "$LOADER" && pass "skill-loader has toolkit entry" || fail "skill-loader missing toolkit entry"
    grep -q "sv-discovery" "$LOADER" && pass "skill-loader has sv-discovery" || fail "skill-loader missing sv-discovery"
    grep -q "sv-evaluation" "$LOADER" && pass "skill-loader has sv-evaluation" || fail "skill-loader missing sv-evaluation"
    grep -q "sv-gepa-optimizer" "$LOADER" && pass "skill-loader has sv-gepa-optimizer" || fail "skill-loader missing sv-gepa-optimizer"
    grep -q "(LEGACY)" "$LOADER" && pass "skill-loader marks old skills as LEGACY" || fail "skill-loader missing LEGACY markers"
else
    fail "skill-loader SKILL.md not found"
fi

# ─── Test 8: GEPA references exist ──────────────────────────────────────
echo ""
echo "## GEPA-specific tests"

[ -f "$PLUGIN_DIR/skills/sv-gepa-optimizer/references/sv-mutation-operators.md" ] && pass "sv-mutation-operators.md exists" || fail "sv-mutation-operators.md missing"
[ -f "$PLUGIN_DIR/skills/sv-evaluation/references/failure-analysis.md" ] && pass "failure-analysis.md exists" || fail "failure-analysis.md missing"

# ─── Summary ─────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════"
echo "  PASS: $PASS  |  FAIL: $FAIL  |  TOTAL: $((PASS + FAIL))"
echo "═══════════════════════════════════════════"

[ $FAIL -eq 0 ] && exit 0 || exit 1
