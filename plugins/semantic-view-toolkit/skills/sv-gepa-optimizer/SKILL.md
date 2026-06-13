# sv-gepa-optimizer

Population-based evolutionary optimization for Snowflake Semantic Views using Genetic Evaluation and Parameter Adaptation (GEPA).

## When to Use

Use this skill when:
- Sequential optimization (sv-optimization) has stalled — 2-3 consecutive rejections indicate a local optimum
- You want to explore the SV structure space broadly rather than greedily
- Multiple aspects of the SV need simultaneous improvement (descriptions, metrics, relationships)
- The SV has enough VQRs (5+) for meaningful mini-batch evaluation

Do NOT use when:
- The SV has fewer than 5 VQRs (use sv-optimization for sequential single-mutation improvement)
- You haven't established a baseline eval score yet (run sv-evaluation first)
- The issue is a single known defect (use targeted sv-optimization instead)

## Prerequisites

- An existing semantic view with at least 5 VQRs defined
- A baseline eval score recorded in `_SV_TOOLKIT_META.EVAL_HISTORY`
- Eval prerequisites met:
  - `EXECUTE TASK` privilege on the account
  - `CREATE TASK` and `CREATE DATASET` privilege in the schema
  - `MONITOR` privilege on the warehouse
- `CREATE OR REPLACE SEMANTIC VIEW` privilege (for deploying candidate SVs)
- Cortex Analyst enabled in the account

## Configuration

| Parameter | Default | Range | Description |
|---|---|---|---|
| `population_size` | 6 | 4–12 | Candidates per generation |
| `max_generations` | 10 | 3–20 | Hard generation cap |
| `mini_batch_pct` | 0.30 | 0.20–0.50 | Fraction of VQRs evaluated per generation |
| `convergence_threshold` | 3 | 2–5 | Generations without improvement before stopping |

---

## Phase 1: Initialize Population

### Step 1: Read Context

Gather the current state of the semantic view and any prior optimization history.

```sql
-- Get current DDL structure
DESCRIBE SEMANTIC VIEW <DB>.<SCHEMA>.<SV_NAME>;
```

Save the output to a local file for the scripts to reference (e.g., `/tmp/gepa_workspace/current_sv.sql`).

```sql
-- Check baseline score (reads from structured EVAL_HISTORY table written by sv-evaluation)
SELECT run_name, mean_score, run_timestamp
FROM <DB>._SV_TOOLKIT_META.EVAL_HISTORY
WHERE sv_fqn LIKE '%<SV_NAME>%'
ORDER BY run_timestamp DESC
LIMIT 5;
```

Record the most recent `mean_score` as `baseline_fitness`.

Check if a previous GEPA run was interrupted:
```bash
ls /tmp/gepa_workspace/gepa_state.yaml 2>/dev/null
```

### Step 2: Resume or Initialize

**If `gepa_state.yaml` exists → Resume Protocol** (see end of document)

**If not → Initialize fresh population:**

```bash
uvx --with pyyaml python scripts/population_state.py init /tmp/gepa_workspace \
  --pop-size 6 \
  --agent-name "<DB>.<SCHEMA>.<SV_NAME>" \
  --baseline-fitness <BASELINE_SCORE>
```

This creates `gepa_state.yaml` with:
- Uniform operator weights (10 operators)
- Generation counter at 1
- Convergence counter at 0
- Empty candidate list

### Step 3: Create Population

For each candidate slot (1 to `population_size`):

**3a. Select mutation operator:**
```bash
uvx --with pyyaml python scripts/mutate.py select-operator \
  --weights-file /tmp/gepa_workspace/gepa_state.yaml
```

Returns: `{"operator": "add_synonym", "target_hint": "...", "weight": 0.12}`

**3b. Generate mutation prompt:**
```bash
uvx --with pyyaml python scripts/mutate.py get-prompt <OPERATOR> /tmp/gepa_workspace/current_sv.sql
```

Returns: `{"operator": "...", "prompt": "<full LLM prompt>"}`

**3c. Apply mutation (LLM-assisted):**

Use the returned prompt with CORTEX.COMPLETE to generate the mutated DDL:

```sql
-- Read ~/.snowflake/cortex/vault/LLMs.md for current default_agent value — do not hardcode
SELECT SNOWFLAKE.CORTEX.COMPLETE(
    '<default_agent>',
    '<mutation_prompt_escaped>'
) AS mutated_ddl;
```

Save the result to `/tmp/gepa_workspace/candidates/cand_<N>.sql`.

**3d. Validate mutation:**
```bash
uvx --with pyyaml python scripts/mutate.py validate \
  /tmp/gepa_workspace/current_sv.sql \
  /tmp/gepa_workspace/candidates/cand_<N>.sql
```

If validation fails (`status: FAIL`), regenerate with the error feedback. Retry up to 2 times before skipping this candidate slot.

**3e. Register candidate:**
```bash
uvx --with pyyaml python scripts/population_state.py add-candidate \
  /tmp/gepa_workspace/gepa_state.yaml \
  --id "cand_<N>" \
  --generation 1 \
  --mutations "<OPERATOR>: <brief description of change>"
```

### Step 4: STOP Gate (GUIDED mode)

Present the population matrix to the user:

```
┌─────────┬──────────────────────┬──────────────────────────────────────┐
│ Candidate│ Operator             │ Mutation Summary                     │
├─────────┼──────────────────────┼──────────────────────────────────────┤
│ cand_1  │ add_synonym          │ Added synonyms to REVENUE, REGION    │
│ cand_2  │ improve_description  │ Rewrote descriptions for 3 columns   │
│ cand_3  │ add_vqr             │ Added "top 10 customers by spend"    │
│ cand_4  │ change_relationship  │ Changed INNER→LEFT on orders→items   │
│ cand_5  │ add_metric          │ Added avg_order_value metric         │
│ cand_6  │ remove_column       │ Removed INTERNAL_ID, AUDIT_TS        │
└─────────┴──────────────────────┴──────────────────────────────────────┘

Baseline fitness: 0.65 (from eval: full_eval_20250520)
Population size: 6 | Mini-batch: 30% of VQRs | Max generations: 10
```

**Wait for user approval before deploying candidates.**

---

## Phase 2: Evaluate Generation

### Step 5: Deploy Candidate SVs

For each validated candidate, deploy as a separate semantic view:

```sql
CREATE OR REPLACE SEMANTIC VIEW <DB>.<SCHEMA>.<SV_NAME>_GEPA_CAND_<N>
  <DDL from /tmp/gepa_workspace/candidates/cand_<N>.sql>
;
```

Verify deployment:
```sql
SHOW SEMANTIC VIEWS LIKE '%_GEPA_CAND_%' IN SCHEMA <DB>.<SCHEMA>;
```

### Step 6: Create Mini-Batch

Select a stratified subset of VQRs for this generation's evaluation:

```bash
# First, extract VQR questions from current SV (pipe as JSON)
echo '<vqr_json_array>' | uvx --with pyyaml python scripts/sample_batch.py \
  --from-stdin \
  --batch-pct 0.30 \
  --generation <G> \
  --history-file /tmp/gepa_workspace/gepa_state.yaml
```

Input VQR JSON format:
```json
[
  {"question": "What is total revenue?", "previously_passed": true},
  {"question": "Show top customers by region", "previously_passed": false}
]
```

The script returns a JSON array of selected question strings and records the batch in state.

### Step 7: Fire Evaluations

For each candidate, start an AI evaluation using the mini-batch VQRs:

```sql
CALL SNOWFLAKE.CORTEX.EXECUTE_AI_EVALUATION(
    '<SV_NAME>__gen<G>__cand_<N>',
    '<DB>.<SCHEMA>.<SV_NAME>_GEPA_CAND_<N>',
    $$
    metrics:
      - sql_correctness
    questions:
      - "What is total revenue?"
      - "Show top customers by region"
      ... (selected mini-batch questions)
    $$
);
```

**Naming convention:** `<SV_NAME>__gen<G>__cand_<N>` (double underscore separators)

### Step 8: Collect Scores

Poll each evaluation for completion (see references/eval-polling.md for pattern):

```sql
-- Check status
SELECT SNOWFLAKE.CORTEX.GET_AI_EVALUATION_STATUS('<SV_NAME>__gen<G>__cand_<N>') AS status;
```

Poll every 30 seconds, max 15 minutes per candidate.

Once COMPLETED, retrieve the fitness score:

```sql
SELECT AVG(sql_correctness) AS mean_score
FROM TABLE(SNOWFLAKE.CORTEX.GET_ANALYST_AI_EVALUATION_DATA('<SV_NAME>__gen<G>__cand_<N>'));
```

Collect all scores into a JSON object:
```json
{"cand_1": 0.75, "cand_2": 0.60, "cand_3": 0.82, "cand_4": 0.55, "cand_5": 0.70, "cand_6": 0.68}
```

**Error handling:**
- If a candidate evaluation FAILS (invalid DDL, permission error): score = 0.0
- If a candidate times out and has ≥80% partial results: use partial mean score
- If a candidate times out with <80% results: score = 0.0

---

## Phase 3: Select and Evolve

### Step 9: Run Tournament

```bash
uvx --with pyyaml python scripts/tournament.py \
  '{"cand_1": 0.75, "cand_2": 0.60, "cand_3": 0.82, "cand_4": 0.55, "cand_5": 0.70, "cand_6": 0.68}' \
  /tmp/gepa_workspace/gepa_state.yaml
```

Returns:
```json
{
  "winners": ["cand_3", "cand_1", "cand_5"],
  "losers": ["cand_2", "cand_4", "cand_6"],
  "best_fitness": 0.82,
  "gen_best_fitness": 0.82,
  "convergence_counter": 0,
  "converged": false
}
```

The script automatically:
- Ranks candidates by score
- Splits into winners (top half) and losers (bottom half)
- Boosts operator weights for winner mutations (+0.02)
- Penalizes loser operators (-0.01, floor 0.02)
- Normalizes weights to sum to 1.0
- Updates convergence counter
- Saves updated state

### Step 10: Update State and Clean Losers

Remove eliminated candidates from state:
```bash
uvx --with pyyaml python scripts/population_state.py remove-candidates \
  /tmp/gepa_workspace/gepa_state.yaml \
  --ids "cand_2,cand_4,cand_6"
```

Drop loser candidate SVs:
```sql
DROP SEMANTIC VIEW IF EXISTS <DB>.<SCHEMA>.<SV_NAME>_GEPA_CAND_2;
DROP SEMANTIC VIEW IF EXISTS <DB>.<SCHEMA>.<SV_NAME>_GEPA_CAND_4;
DROP SEMANTIC VIEW IF EXISTS <DB>.<SCHEMA>.<SV_NAME>_GEPA_CAND_6;
```

### Step 11: Check Convergence

Read the `converged` flag from the tournament output.

**If `converged: false`:**

1. Increment generation:
```bash
uvx --with pyyaml python scripts/population_state.py increment-generation \
  /tmp/gepa_workspace/gepa_state.yaml
```

2. Fill empty slots by mutating winners:
   - For each empty slot, pick a random winner as the base
   - Apply a new mutation (repeat Step 3a–3e using winner's DDL as input)
   - Register new candidates for the next generation

3. Return to **Phase 2, Step 5** (deploy and evaluate next generation)

**If `converged: true`:**

Check convergence reason via:
```bash
uvx --with pyyaml python scripts/population_state.py get-status \
  /tmp/gepa_workspace/gepa_state.yaml
```

Proceed to Phase 4.

---

## Phase 4: Validate Winner

### Step 12: Deploy Winner as Production SV

Identify the best candidate (highest fitness across all generations):

```bash
uvx --with pyyaml python scripts/population_state.py get-status \
  /tmp/gepa_workspace/gepa_state.yaml
```

Read the winner's DDL and deploy as the production semantic view:

```sql
CREATE OR REPLACE SEMANTIC VIEW <DB>.<SCHEMA>.<SV_NAME>
  <DDL from winning candidate>
;
```

### Step 13: Full Evaluation

Run a complete evaluation using ALL VQRs (not mini-batch):

```sql
CALL SNOWFLAKE.CORTEX.EXECUTE_AI_EVALUATION(
    '<SV_NAME>__gepa_final',
    '<DB>.<SCHEMA>.<SV_NAME>',
    $$
    metrics:
      - sql_correctness
    $$
);
```

Poll until COMPLETED and retrieve full results:

```sql
SELECT
    AVG(sql_correctness) AS mean_score,
    COUNT(*) AS total_vqrs,
    SUM(CASE WHEN sql_correctness = 1.0 THEN 1 ELSE 0 END) AS perfect_count,
    SUM(CASE WHEN sql_correctness = 0.0 THEN 1 ELSE 0 END) AS failed_count
FROM TABLE(SNOWFLAKE.CORTEX.GET_ANALYST_AI_EVALUATION_DATA('<SV_NAME>__gepa_final'));
```

### Step 14: Accept/Reject

**ACCEPT if:**
- Full eval score > baseline score
- No new regressions (questions that previously passed now failing)
- Improvement is statistically meaningful (>= 2% absolute improvement)

**REJECT if:**
- Full eval score <= baseline score
- New regressions detected (even if overall score improved slightly)
- Score improvement < 2% (not worth the structural changes)

**On REJECT:** Revert to original DDL:
```sql
CREATE OR REPLACE SEMANTIC VIEW <DB>.<SCHEMA>.<SV_NAME>
  <original DDL from /tmp/gepa_workspace/current_sv.sql>
;
```

### Step 15: Log and Cleanup

Record the GEPA run results:

```sql
-- Record final GEPA result in structured EVAL_HISTORY (matches sv-evaluation write schema)
-- config_yaml carries GEPA-specific metadata as a serialized string
INSERT INTO <DB>._SV_TOOLKIT_META.EVAL_HISTORY
    (run_name, sv_fqn, total_vqrs, mean_score, perfect_count, failed_count, regressions, config_yaml)
VALUES (
    CONCAT('<SV_NAME>', '_gepa_', TO_CHAR(CURRENT_TIMESTAMP(), 'YYYYMMDD_HH24MISS')),
    '<DB>.<SCHEMA>.<SV_NAME>',
    <TOTAL_VQRS>,
    <FINAL_SCORE>,
    <PERFECT_COUNT>,
    <FAILED_COUNT>,
    <REGRESSIONS>,
    '{"source":"gepa","status":"<ACCEPTED|REJECTED|CONVERGED|FAILED>","generations":<G>,"baseline_fitness":<BASELINE>,"best_candidate":"<cand_id>","best_operator":"<winning_operator>","convergence_reason":"<reason>","operator_weights_final":<weights_json>}'
);
```

Drop all remaining candidate SVs:
```sql
-- Find and drop all GEPA candidate SVs
SHOW SEMANTIC VIEWS LIKE '%_GEPA_CAND_%' IN SCHEMA <DB>.<SCHEMA>;

DROP SEMANTIC VIEW IF EXISTS <DB>.<SCHEMA>.<SV_NAME>_GEPA_CAND_1;
DROP SEMANTIC VIEW IF EXISTS <DB>.<SCHEMA>.<SV_NAME>_GEPA_CAND_2;
-- ... (all remaining candidates)
```

Remove workspace:
```bash
rm -rf /tmp/gepa_workspace
```

Report final summary:
```
┌─────────────────────────────────────────────────────┐
│ GEPA Optimization Complete                          │
├─────────────────────────────────────────────────────┤
│ Status:           ACCEPTED                          │
│ Generations:      4                                 │
│ Baseline Score:   0.65                              │
│ Final Score:      0.82 (+17%)                       │
│ Best Operator:    add_synonym (weight: 0.18)        │
│ Convergence:      Counter hit threshold (3 gens)    │
│ Candidates Tried: 24                                │
│ Eval Runs:        28 (24 mini-batch + 4 full)       │
└─────────────────────────────────────────────────────┘
```

---

## Resume Protocol

If `gepa_state.yaml` exists when starting the skill:

### Step 1: Read State
```bash
uvx --with pyyaml python scripts/population_state.py get-status \
  /tmp/gepa_workspace/gepa_state.yaml
```

### Step 2: Check Environment

```sql
-- Are candidate SVs deployed?
SHOW SEMANTIC VIEWS LIKE '%_GEPA_CAND_%' IN SCHEMA <DB>.<SCHEMA>;
```

### Step 3: Determine Resume Point

| State | Candidate SVs Exist? | Eval Results? | Resume At |
|-------|---------------------|---------------|-----------|
| Candidates registered, not deployed | No | No | Phase 2, Step 5 |
| Candidates deployed, no eval fired | Yes | No | Phase 2, Step 7 |
| Eval fired, incomplete | Yes | Partial | Phase 2, Step 8 (continue polling) |
| Eval complete, no tournament | Yes | Yes | Phase 3, Step 9 |
| Tournament done, next gen needed | Partial (winners only) | Yes | Phase 3, Step 11 |

### Step 4: Resume

Pick up execution at the identified phase/step. Report to user:
```
Resuming GEPA optimization from generation <G>, Phase <P>, Step <S>.
Previous best fitness: <score> (candidate: <id>)
```

---

## Cleanup Intent

When user says "gepa cleanup" or "clean gepa svs":

```sql
-- Find all GEPA candidate SVs in the schema
SHOW SEMANTIC VIEWS LIKE '%_GEPA_CAND_%' IN SCHEMA <DB>.<SCHEMA>;
```

For each found SV:
```sql
DROP SEMANTIC VIEW IF EXISTS <DB>.<SCHEMA>.<SV_NAME>;
```

Remove local state:
```bash
rm -rf /tmp/gepa_workspace
```

Report:
```
Cleaned up:
- Dropped N candidate semantic views
- Removed gepa_state.yaml and workspace
```

---

## Key Differences from Agent GEPA

| Aspect | Agent GEPA | SV GEPA (this skill) |
|--------|-----------|----------------------|
| Target | Agent instructions (YAML) | Semantic View DDL |
| Deploy | `CREATE OR REPLACE CORTEX AGENT` | `CREATE OR REPLACE SEMANTIC VIEW ..._GEPA_CAND_<N>` |
| Eval Function | `EXECUTE_AI_EVALUATION` (agent type) | `EXECUTE_AI_EVALUATION` (analyst type) |
| Results Function | `GET_AI_EVALUATION_DATA` | `GET_ANALYST_AI_EVALUATION_DATA` |
| Metrics | 4 agent metrics | `sql_correctness` only |
| Mutations | Agent instruction rewrites | SV DDL operators (synonym, description, metric, etc.) |
| Scripts | agent-toolkit scripts/ | semantic-view-toolkit scripts/ (shared) |
