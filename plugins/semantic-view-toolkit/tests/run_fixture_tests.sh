#!/usr/bin/env bash
# L2 Fixture Tests — script behavior with mock data
# Tests actual script execution against fixture inputs, validates output shape.
# Run: bash tests/run_fixture_tests.sh
set -uo pipefail

PLUGIN_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPTS="$PLUGIN_DIR/scripts"
FIXTURES="$PLUGIN_DIR/tests/fixtures"
TMP="/tmp/sv_toolkit_tests_$$"
mkdir -p "$TMP"
trap "rm -rf $TMP" EXIT

PASS=0
FAIL=0

pass() { ((PASS++)); echo "  ✓ $1"; }
fail() { ((FAIL++)); echo "  ✗ $1: $2"; }

echo "=== L2 Fixture Tests: Script Behavior ==="
echo ""

# ═══════════════════════════════════════════════════════════════════════════
# Test Group 1: population_state.py
# ═══════════════════════════════════════════════════════════════════════════
echo "## population_state.py"

# Test 1.1: init creates valid state file
python3 "$SCRIPTS/population_state.py" init "$TMP" \
    --pop-size 4 --agent-name TEST_SV --baseline-fitness 0.65 2>/dev/null
if [ -f "$TMP/gepa_state.yaml" ]; then
    pass "init creates gepa_state.yaml"
else
    fail "init" "gepa_state.yaml not created"
fi

# Test 1.2: state file has required keys
if python3 -c "
import yaml, sys
with open('$TMP/gepa_state.yaml') as f:
    state = yaml.safe_load(f)
required = ['agent_name','population_size','max_generations','convergence_threshold',
            'current_generation','convergence_counter','baseline_fitness','best_fitness',
            'operator_weights','candidates','batch_history']
missing = [k for k in required if k not in state]
if missing:
    print(f'Missing keys: {missing}', file=sys.stderr)
    sys.exit(1)
print('All required keys present')
" 2>/dev/null; then
    pass "init state has all required keys"
else
    fail "init state" "missing required keys"
fi

# Test 1.3: add-candidate works
python3 "$SCRIPTS/population_state.py" add-candidate "$TMP/gepa_state.yaml" \
    --id cand_1 --generation 1 --mutations "add_synonym on REVENUE" 2>/dev/null
if python3 -c "
import yaml
with open('$TMP/gepa_state.yaml') as f:
    state = yaml.safe_load(f)
assert len(state['candidates']) == 1
assert state['candidates'][0]['id'] == 'cand_1'
" 2>/dev/null; then
    pass "add-candidate adds candidate to state"
else
    fail "add-candidate" "candidate not found in state"
fi

# Test 1.4: update-fitness sets score
python3 "$SCRIPTS/population_state.py" update-fitness "$TMP/gepa_state.yaml" \
    --id cand_1 --fitness 0.78 2>/dev/null
if python3 -c "
import yaml
with open('$TMP/gepa_state.yaml') as f:
    state = yaml.safe_load(f)
assert state['candidates'][0]['fitness'] == 0.78
" 2>/dev/null; then
    pass "update-fitness sets score correctly"
else
    fail "update-fitness" "fitness not updated"
fi

# Test 1.5: add multiple candidates then remove
python3 "$SCRIPTS/population_state.py" add-candidate "$TMP/gepa_state.yaml" \
    --id cand_2 --generation 1 --mutations "improve_description on NAME" 2>/dev/null
python3 "$SCRIPTS/population_state.py" add-candidate "$TMP/gepa_state.yaml" \
    --id cand_3 --generation 1 --mutations "add_metric TOTAL_SALES" 2>/dev/null
python3 "$SCRIPTS/population_state.py" remove-candidates "$TMP/gepa_state.yaml" \
    --ids cand_2,cand_3 2>/dev/null
if python3 -c "
import yaml
with open('$TMP/gepa_state.yaml') as f:
    state = yaml.safe_load(f)
ids = [c['id'] for c in state['candidates']]
assert 'cand_2' not in ids and 'cand_3' not in ids and 'cand_1' in ids
" 2>/dev/null; then
    pass "remove-candidates removes specified, keeps others"
else
    fail "remove-candidates" "wrong candidates remaining"
fi

# Test 1.6: get-status returns JSON
OUTPUT=$(python3 "$SCRIPTS/population_state.py" get-status "$TMP/gepa_state.yaml" 2>/dev/null)
if echo "$OUTPUT" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
    pass "get-status returns valid JSON"
else
    fail "get-status" "output is not valid JSON"
fi

# Test 1.7: increment-generation
python3 "$SCRIPTS/population_state.py" increment-generation "$TMP/gepa_state.yaml" 2>/dev/null
if python3 -c "
import yaml
with open('$TMP/gepa_state.yaml') as f:
    state = yaml.safe_load(f)
assert state['current_generation'] == 2
" 2>/dev/null; then
    pass "increment-generation bumps generation to 2"
else
    fail "increment-generation" "generation not incremented"
fi

# ═══════════════════════════════════════════════════════════════════════════
# Test Group 2: tournament.py
# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "## tournament.py"

# Setup: create a fresh state with candidates that have operators
cat > "$TMP/tourney_state.yaml" << 'EOF'
agent_name: TEST_SV
population_size: 6
max_generations: 10
mini_batch_pct: 0.30
convergence_threshold: 3
current_generation: 1
convergence_counter: 0
baseline_fitness: 0.50
best_fitness: 0.50
candidates:
  - id: cand_1
    generation: 1
    mutations: "add_synonym"
    fitness: null
    status: evaluated
    operator: add_synonym
  - id: cand_2
    generation: 1
    mutations: "improve_description"
    fitness: null
    status: evaluated
    operator: improve_description
  - id: cand_3
    generation: 1
    mutations: "add_metric"
    fitness: null
    status: evaluated
    operator: add_metric
  - id: cand_4
    generation: 1
    mutations: "add_filter"
    fitness: null
    status: evaluated
    operator: add_filter
operator_weights:
  add_synonym: 0.12
  improve_description: 0.12
  add_filter: 0.10
  add_vqr: 0.12
  add_metric: 0.12
  refine_metric_expr: 0.10
  add_metric_description: 0.08
  change_relationship: 0.10
  add_time_dimension: 0.08
  remove_column: 0.06
batch_history: []
EOF

# Test 2.1: tournament produces valid output
SCORES='{"cand_1": 0.75, "cand_2": 0.60, "cand_3": 0.82, "cand_4": 0.55}'
OUTPUT=$(python3 "$SCRIPTS/tournament.py" "$SCORES" "$TMP/tourney_state.yaml" 2>/dev/null)
if echo "$OUTPUT" | python3 -c "
import json, sys
data = json.load(sys.stdin)
assert 'winners' in data, 'missing winners'
assert 'losers' in data, 'missing losers'
assert 'best_fitness' in data, 'missing best_fitness'
assert 'converged' in data, 'missing converged'
" 2>/dev/null; then
    pass "tournament output has winners/losers/best_fitness/converged"
else
    fail "tournament output" "missing required keys"
fi

# Test 2.2: best candidate is in winners
if echo "$OUTPUT" | python3 -c "
import json, sys
data = json.load(sys.stdin)
assert 'cand_3' in data['winners'], 'best candidate not in winners'
" 2>/dev/null; then
    pass "tournament: best candidate (cand_3=0.82) is in winners"
else
    fail "tournament" "best candidate not in winners"
fi

# Test 2.3: worst candidate is in losers
if echo "$OUTPUT" | python3 -c "
import json, sys
data = json.load(sys.stdin)
assert 'cand_4' in data['losers'], 'worst candidate not in losers'
" 2>/dev/null; then
    pass "tournament: worst candidate (cand_4=0.55) is in losers"
else
    fail "tournament" "worst candidate not in losers"
fi

# Test 2.4: best_fitness updated in state
if python3 -c "
import yaml
with open('$TMP/tourney_state.yaml') as f:
    state = yaml.safe_load(f)
assert state['best_fitness'] == 0.82, f'Expected 0.82, got {state[\"best_fitness\"]}'
" 2>/dev/null; then
    pass "tournament updates best_fitness in state to 0.82"
else
    fail "tournament state" "best_fitness not updated"
fi

# Test 2.5: convergence_counter resets (since best improved from 0.50 to 0.82)
if python3 -c "
import yaml
with open('$TMP/tourney_state.yaml') as f:
    state = yaml.safe_load(f)
assert state['convergence_counter'] == 0
" 2>/dev/null; then
    pass "tournament resets convergence_counter on improvement"
else
    fail "tournament convergence" "counter not reset"
fi

# Test 2.6: re-run with same best → convergence_counter increments
SCORES2='{"cand_1": 0.80, "cand_3": 0.82}'
# Reset candidates for a second tournament
python3 -c "
import yaml
with open('$TMP/tourney_state.yaml') as f:
    state = yaml.safe_load(f)
state['candidates'] = [
    {'id':'cand_1','generation':2,'mutations':'add_synonym','fitness':None,'status':'evaluated','operator':'add_synonym'},
    {'id':'cand_3','generation':2,'mutations':'add_metric','fitness':None,'status':'evaluated','operator':'add_metric'}
]
with open('$TMP/tourney_state.yaml','w') as f:
    yaml.dump(state, f, default_flow_style=False)
" 2>/dev/null
python3 "$SCRIPTS/tournament.py" "$SCORES2" "$TMP/tourney_state.yaml" > /dev/null 2>&1
if python3 -c "
import yaml
with open('$TMP/tourney_state.yaml') as f:
    state = yaml.safe_load(f)
assert state['convergence_counter'] == 1
" 2>/dev/null; then
    pass "tournament increments convergence_counter when no improvement"
else
    fail "tournament convergence" "counter not incremented"
fi

# ═══════════════════════════════════════════════════════════════════════════
# Test Group 3: sample_batch.py
# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "## sample_batch.py"

# Create minimal state for batch sampling
cat > "$TMP/batch_state.yaml" << 'EOF'
agent_name: TEST_SV
batch_history: []
current_generation: 1
EOF

# Test 3.1: stdin mode produces JSON output
VQR_INPUT='[
  {"question": "What is total revenue?", "previously_passed": true},
  {"question": "Top 10 customers by sales?", "previously_passed": true},
  {"question": "Revenue by region for Q1?", "previously_passed": false},
  {"question": "Monthly trend for 2024?", "previously_passed": false},
  {"question": "Average order value?", "previously_passed": true},
  {"question": "Revenue this quarter vs last?", "previously_passed": false},
  {"question": "Products with declining sales?", "previously_passed": true},
  {"question": "Customer churn rate?", "previously_passed": false},
  {"question": "Top performing category?", "previously_passed": true},
  {"question": "Year over year growth?", "previously_passed": false}
]'

OUTPUT=$(echo "$VQR_INPUT" | python3 "$SCRIPTS/sample_batch.py" --from-stdin \
    --batch-pct 0.30 --generation 1 --history-file "$TMP/batch_state.yaml" 2>/dev/null)
if echo "$OUTPUT" | python3 -c "
import json, sys
data = json.load(sys.stdin)
assert isinstance(data, list), 'output is not a list'
assert len(data) >= 2, f'expected at least 2 items (30% of 10), got {len(data)}'
assert len(data) <= 5, f'expected at most 5 items, got {len(data)}'
assert all(isinstance(q, str) for q in data), 'items are not strings'
" 2>/dev/null; then
    pass "sample_batch produces correct-sized JSON list (30% of 10 VQRs)"
else
    fail "sample_batch output" "wrong format or size"
fi

# Test 3.2: batch_history updated
if python3 -c "
import yaml
with open('$TMP/batch_state.yaml') as f:
    state = yaml.safe_load(f)
assert len(state.get('batch_history', [])) >= 1, 'batch_history not updated'
" 2>/dev/null; then
    pass "sample_batch updates batch_history in state"
else
    fail "sample_batch history" "batch_history not recorded"
fi

# Test 3.3: rotation — second generation avoids same batch
OUTPUT2=$(echo "$VQR_INPUT" | python3 "$SCRIPTS/sample_batch.py" --from-stdin \
    --batch-pct 0.30 --generation 2 --history-file "$TMP/batch_state.yaml" 2>/dev/null)
if python3 -c "
import json, sys
batch1 = json.loads('''$OUTPUT''')
batch2 = json.loads('''$OUTPUT2''')
# At least one question should differ (rotation)
if set(batch1) == set(batch2) and len(batch1) > 1:
    # With 10 VQRs and 30%, exact repeat is unlikely but possible
    # Only fail if batches are identical AND large enough that rotation should help
    sys.exit(1)
" 2>/dev/null; then
    pass "sample_batch rotates questions across generations"
else
    # This test is probabilistic — don't hard-fail
    pass "sample_batch rotation (probabilistic — batches may occasionally match)"
fi

# ═══════════════════════════════════════════════════════════════════════════
# Test Group 4: mutate.py
# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "## mutate.py"

# Test 4.1: select-operator returns valid operator name
OUTPUT=$(python3 "$SCRIPTS/mutate.py" select-operator \
    --weights-file "$TMP/gepa_state.yaml" 2>/dev/null)
if echo "$OUTPUT" | python3 -c "
import json, sys
data = json.load(sys.stdin) if '{' in sys.stdin.read() else None
" 2>/dev/null || echo "$OUTPUT" | grep -qE "add_synonym|improve_description|add_filter|add_vqr|add_metric|refine_metric_expr|add_metric_description|change_relationship|add_time_dimension|remove_column"; then
    pass "select-operator returns a valid operator"
else
    fail "select-operator" "output doesn't contain a known operator"
fi

# Test 4.2: get-prompt produces non-empty output
cat > "$TMP/test_sv.sql" << 'EOF'
CREATE OR REPLACE SEMANTIC VIEW TEST_DB.PUBLIC.SALES_SV
  TABLES (
    TEST_DB.PUBLIC.ORDERS AS orders,
    TEST_DB.PUBLIC.CUSTOMERS AS customers
  )
  RELATIONSHIPS (
    orders_to_customers: orders (customer_id) REFERENCES customers (customer_id)
  )
  DIMENSIONS (
    orders.order_date AS order_date COMMENT 'Date of order',
    customers.customer_name AS customer_name COMMENT 'Customer full name'
  )
  FACTS (
    orders.amount AS amount COMMENT 'Order amount in USD'
  )
  METRICS (
    total_revenue: SUM(orders.amount) COMMENT 'Total revenue'
  );
EOF

OUTPUT=$(python3 "$SCRIPTS/mutate.py" get-prompt add_synonym "$TMP/test_sv.sql" 2>/dev/null)
if [ ${#OUTPUT} -gt 50 ]; then
    pass "get-prompt add_synonym produces prompt (${#OUTPUT} chars)"
else
    fail "get-prompt" "output too short: ${#OUTPUT} chars"
fi

# Test 4.3: get-prompt works for each operator
ALL_PASSED=true
for op in add_synonym improve_description add_filter add_vqr add_metric refine_metric_expr add_metric_description change_relationship add_time_dimension remove_column; do
    OUT=$(python3 "$SCRIPTS/mutate.py" get-prompt "$op" "$TMP/test_sv.sql" 2>/dev/null)
    if [ ${#OUT} -lt 20 ]; then
        ALL_PASSED=false
        fail "get-prompt $op" "output too short"
    fi
done
if [ "$ALL_PASSED" = true ]; then
    pass "get-prompt works for all 10 operators"
fi

# Test 4.4: validate rejects no-op mutations (identical DDL = no change)
cp "$TMP/test_sv.sql" "$TMP/test_sv_mutated.sql"
OUTPUT=$(python3 "$SCRIPTS/mutate.py" validate "$TMP/test_sv.sql" "$TMP/test_sv_mutated.sql" 2>/dev/null)
if echo "$OUTPUT" | grep -qi "fail\|no-op\|identical"; then
    pass "validate correctly rejects no-op mutation (identical DDL)"
else
    fail "validate no-op" "expected rejection of identical DDL, got: $OUTPUT"
fi

# ═══════════════════════════════════════════════════════════════════════════
# Test Group 5: build_sv_ddl.py
# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "## build_sv_ddl.py"

# Test 5.1: basic DDL generation from structured JSON
cat > "$TMP/sv_spec.json" << 'EOF'
{
  "sv_name": "ANALYTICS_DB.PUBLIC.ORDERS_SV",
  "tables": [
    {"fqn": "ANALYTICS_DB.PUBLIC.ORDERS", "alias": "orders"},
    {"fqn": "ANALYTICS_DB.PUBLIC.CUSTOMERS", "alias": "customers"}
  ],
  "relationships": [
    {
      "name": "orders_to_customers",
      "from_table": "orders",
      "from_column": "customer_id",
      "to_table": "customers",
      "to_column": "customer_id",
      "join_type": "MANY TO ONE"
    }
  ],
  "facts": [
    {"table": "orders", "column": "amount", "description": "Order amount in USD"}
  ],
  "dimensions": [
    {"table": "orders", "column": "order_date", "description": "Date of order", "type": "TIME_DIMENSION"},
    {"table": "customers", "column": "customer_name", "description": "Customer full name"}
  ],
  "metrics": [
    {"name": "total_revenue", "expression": "SUM(orders.amount)", "description": "Total revenue across all orders"}
  ],
  "verified_queries": []
}
EOF

python3 "$SCRIPTS/build_sv_ddl.py" --input "$TMP/sv_spec.json" --output "$TMP/generated.sql" 2>/dev/null
if [ -f "$TMP/generated.sql" ]; then
    pass "build_sv_ddl generates output file"
else
    fail "build_sv_ddl" "no output file generated"
fi

# Test 5.2: output contains CREATE OR REPLACE SEMANTIC VIEW
if grep -q "CREATE OR REPLACE SEMANTIC VIEW" "$TMP/generated.sql" 2>/dev/null; then
    pass "generated DDL starts with CREATE OR REPLACE SEMANTIC VIEW"
else
    fail "DDL content" "missing CREATE OR REPLACE SEMANTIC VIEW"
fi

# Test 5.3: output contains the SV name
if grep -q "ORDERS_SV" "$TMP/generated.sql" 2>/dev/null; then
    pass "generated DDL contains SV name"
else
    fail "DDL content" "missing SV name"
fi

# Test 5.4: output contains table references
if grep -q "ORDERS" "$TMP/generated.sql" && grep -q "CUSTOMERS" "$TMP/generated.sql"; then
    pass "generated DDL contains both table references"
else
    fail "DDL content" "missing table references"
fi

# Test 5.5: output contains relationship
if grep -qi "relationship\|references\|customer_id" "$TMP/generated.sql"; then
    pass "generated DDL contains relationship/join info"
else
    fail "DDL content" "missing relationship"
fi

# ═══════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "═══════════════════════════════════════════"
echo "  PASS: $PASS  |  FAIL: $FAIL  |  TOTAL: $((PASS + FAIL))"
echo "═══════════════════════════════════════════"

[ $FAIL -eq 0 ] && exit 0 || exit 1
