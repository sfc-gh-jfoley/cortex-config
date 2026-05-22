---
name: agent-flag-tester
description: >
  Standalone Cortex Agent flag comparison testing. Creates 3 agent variants
  (BASE, AGENTIC, FASTPATH_OFF), builds/validates eval dataset with ground truth
  verification, runs DEV/TEST evaluations using EXECUTE_AI_EVALUATION, and
  compares results across variants with statistical rigor.
  Use when: flag comparison, A/B test agents, compare EnableAgenticAnalyst,
  compare feature flags, 3-way agent comparison, test agent variants,
  agent flag sweep, evaluate agent flags, which flag config is best.
  Produces flag_sweep_baseline.json — consumed by cortex-agent-optimization
  for automatic FLAG REVALIDATION after optimization iterations.
---

## Prerequisites

- A deployed Snowflake Cortex Agent with at least one `cortex_analyst_text_to_sql` tool
- `snow` CLI installed with a named connection
- Role with: `SNOWFLAKE.CORTEX_USER`, `EXECUTE TASK ON ACCOUNT`, `USAGE`/`CREATE DATASET ON SCHEMA` on agent schema

## Overview

This skill runs a complete flag comparison test in 7 phases:

1. **Discover** — extract agent spec, identify semantic views
2. **Create Variants** — deploy 3 agent clones with different flag configs
3. **Build/Validate Dataset** — create or validate eval table + DEV/TEST splits
4. **Verify Ground Truth** — run queries against semantic views to confirm data exists
5. **Generate Configs** — create YAML eval configs + upload to stage
6. **Fire Evals** — launch all runs via `EXECUTE_AI_EVALUATION` + poll to completion
7. **Compare Results** — extract scores, build comparison table, recommend winner

Each phase has a STOP gate requiring user confirmation before proceeding.

## Parameters

Collect these from the user at the start (or detect from context):

| Parameter | Description | Example |
|---|---|---|
| `<AGENT_FQN>` | Fully qualified agent name | `ACME_ANALYTICS.PUBLIC.ACME_AGENT` |
| `<CONNECTION>` | Snowflake connection name | `default` |
| `<DATABASE>` | Database containing agent | `ACME_ANALYTICS` |
| `<SCHEMA>` | Schema containing agent | `PUBLIC` |
| `<AGENT_NAME>` | Unqualified agent name | `ACME_AGENT` |
| `<RUNS_PER_SPLIT>` | Eval runs per split (default 3) | `3` |
| `<RUN_PREFIX>` | Prefix for run names | `acme_flag_v1` |

---

## Phase 1: Discover Agent

### Step 1.1: Retrieve Agent Spec

```bash
cortex agents describe <AGENT_FQN>
```

If unavailable, fall back to:
```sql
DESCRIBE AGENT <AGENT_FQN>;
```

Extract from the spec:
- `spec.instructions.orchestration` — current instructions
- `spec.tools[]` — list of tools with types and descriptions
- `spec.tool_resources` — mapping of tool names to semantic view FQNs and warehouses
- `spec.models.orchestration` — current model
- `spec.experimental` — current flag settings (if any)

### Step 1.2: Identify Semantic Views

For each tool of type `cortex_analyst_text_to_sql`, extract:
- Tool name (e.g., `query_subscriber_360`)
- Semantic view FQN from `tool_resources.{tool_name}.semantic_view`

Store as `<SEMANTIC_VIEWS>` list for Phase 4 ground truth verification.

### Step 1.3: Validate Semantic Views Exist

For each semantic view:
```sql
DESCRIBE SEMANTIC VIEW <SEMANTIC_VIEW_FQN>;
```

If any fail, STOP — the agent's tools are broken and eval will be meaningless.

**STOP GATE:** Present agent summary (model, tools, semantic views, current flags). Confirm before proceeding.

---

## Phase 2: Create Variants

Load `references/variant-matrix.md` for the default matrix.

### Step 2.0: Select Variants

Present the default matrix and ask:

> "Which variants do you want to test?"
> 1. **All 3** — BASE, AGENTIC, FASTPATH_OFF (recommended for first sweep)
> 2. **AGENTIC + FASTPATH_OFF only** — skip BASE if you already know non-agentic is not an option
> 3. **Custom selection** — pick from the matrix or define custom variants

Store the selected variants as `<VARIANTS>` list. All subsequent phases iterate over only the selected variants — not hardcoded to 3.

### Step 2.1: Generate Variant Specs

For each selected variant:
1. Start with the original agent spec
2. Modify the `experimental` section per the matrix
3. Keep everything else identical (instructions, tools, tool_resources, model, budget)

### Step 2.2: Generate CREATE AGENT SQL

For each variant, generate:
```sql
CREATE AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>_{SUFFIX}
FROM SPECIFICATION $$
<modified_spec_json>
$$;
```

Use `CHR(39)` escaping if the spec contains literal `$$` in instruction text.

**Critical:** All 3 variants MUST be in the same schema as the eval dataset. The eval task DAG resolves agent names relative to the task's schema, ignoring FQN.

**STOP GATE:** Present the CREATE SQL for all 3 variants. Ask user: "Want me to create a rollback clone first so we can undo this?" Then execute upon confirmation.

### Step 2.3: Verify Deployment

For each variant:
```sql
DESCRIBE AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>_{SUFFIX};
```

Confirm all 3 are deployed with correct flags.

---

## Phase 3: Build/Validate Eval Dataset

### Step 3.1: Check for Existing Dataset

```sql
SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = '<SCHEMA>' AND TABLE_NAME = '<AGENT_NAME>_EVAL';
```

**If exists:** Skip to Step 3.3 (validate).

**If not exists:** Create the table using the schema from `references/eval-table-schema.md`:

```sql
CREATE TABLE <DATABASE>.<SCHEMA>.<AGENT_NAME>_EVAL (
    TEST_ID        NUMBER(38,0) AUTOINCREMENT,
    TEST_CATEGORY  VARCHAR,
    INPUT_QUERY    VARCHAR      NOT NULL,
    GROUND_TRUTH   VARIANT,
    SPLIT          VARCHAR      DEFAULT 'VALIDATION'
);
```

Ask the user how they want to populate it:

> 1. **Import from text file** — provide a file with one question per line (recommended for quick start)
> 2. **Manual entry** — write INSERT statements by hand
> 3. **Already have a table** — point to an existing table to import from

If **Option 1 (text file import):**

1. Read the file path from the user. Parse it — one question per line, blank lines ignored, lines starting with `#` treated as category headers.

   Format:
   ```
   # customer_lookup
   Show me the full profile for customer Alex Johnson
   What is the risk tier for account ACC-1001?

   # operations
   Which regions had the most incidents last week?
   Show me the coverage report for the West region
   ```

   Lines after a `# category` header are assigned that TEST_CATEGORY. Lines before any header get category `general`.

2. INSERT the questions (without ground truth yet):
   ```sql
   INSERT INTO <DATABASE>.<SCHEMA>.<AGENT_NAME>_EVAL (TEST_CATEGORY, INPUT_QUERY)
   VALUES ('<category>', '<question>');
   ```

3. **Auto-generate ground truth** — for each question, run it against the semantic view(s) identified in Phase 1:
   ```bash
   cortex analyst query "<INPUT_QUERY>" --view=<SEMANTIC_VIEW_FQN>
   ```
   Capture the analyst's text response as the candidate ground truth.

4. UPDATE the table with generated ground truth:
   ```sql
   UPDATE <DATABASE>.<SCHEMA>.<AGENT_NAME>_EVAL
   SET GROUND_TRUTH = PARSE_JSON('{"ground_truth_output": "<analyst_response>"}')
   WHERE TEST_ID = <id>;
   ```

5. **STOP GATE — Human Review:** Present ALL generated ground truth answers in a table:

   | TEST_ID | Category | Question (truncated) | Generated Ground Truth (truncated) | Status |
   |---|---|---|---|---|
   | 1 | customer_lookup | Show me the full profile... | Alex Johnson (CUS-0001...) | REVIEW |
   | 2 | customer_lookup | What is the risk tier... | Account ACC-1001 has... | REVIEW |
   | ... | ... | ... | ... | ... |

   For each row, the user can:
   - **Accept** — ground truth is correct as-is
   - **Edit** — provide a corrected ground truth
   - **Delete** — remove the question from the eval set (bad question)

   Questions where the analyst returned an error or empty result are flagged as `NEEDS ATTENTION`.

   Do NOT proceed until the user has reviewed all rows. Apply edits/deletions, then re-count to confirm >= 10 valid questions remain.

If **Option 2 (manual):** Show the INSERT format from `references/eval-table-schema.md`. Do NOT proceed until `SELECT COUNT(*) FROM <AGENT_NAME>_EVAL` returns >= 10 rows.

If **Option 3 (import from table):** Ask for the source table FQN. Validate it has at minimum an `INPUT_QUERY` or similarly named VARCHAR column. INSERT into the eval table, then run the ground truth auto-generation flow from Option 1 Step 3-5 for any rows with NULL GROUND_TRUTH.

### Step 3.2: Assign DEV/TEST Splits

Check if splits already exist:
```sql
SELECT DISTINCT SPLIT FROM <DATABASE>.<SCHEMA>.<AGENT_NAME>_EVAL WHERE SPLIT IS NOT NULL;
```

- **2 distinct values:** Ask user which is DEV, which is TEST.
- **0-1 values:** Assign splits — 45% DEV (`TRAIN`) / 55% TEST (`VALIDATION`), stratified by TEST_CATEGORY:

```sql
UPDATE <DATABASE>.<SCHEMA>.<AGENT_NAME>_EVAL
SET SPLIT = 'TRAIN'
WHERE TEST_ID IN (
    SELECT TEST_ID FROM (
        SELECT TEST_ID,
               ROW_NUMBER() OVER (PARTITION BY TEST_CATEGORY ORDER BY RANDOM(42)) AS rn,
               COUNT(*) OVER (PARTITION BY TEST_CATEGORY) AS cat_total
        FROM <DATABASE>.<SCHEMA>.<AGENT_NAME>_EVAL
    )
    WHERE rn <= ROUND(cat_total * 0.45)
);
```

Create views:
```sql
CREATE OR REPLACE VIEW <DATABASE>.<SCHEMA>.<AGENT_NAME>_EVAL_DEV AS
SELECT * FROM <DATABASE>.<SCHEMA>.<AGENT_NAME>_EVAL WHERE SPLIT = 'TRAIN';

CREATE OR REPLACE VIEW <DATABASE>.<SCHEMA>.<AGENT_NAME>_EVAL_TEST AS
SELECT * FROM <DATABASE>.<SCHEMA>.<AGENT_NAME>_EVAL WHERE SPLIT = 'VALIDATION';
```

### Step 3.3: Validate Ground Truth Completeness

Run the validation query from `references/eval-table-schema.md`:
```sql
SELECT
    SPLIT,
    COUNT(*) AS TOTAL,
    COUNT_IF(GROUND_TRUTH IS NULL) AS NULL_GT,
    COUNT_IF(GROUND_TRUTH IS NOT NULL
             AND GROUND_TRUTH:ground_truth_output::STRING IS NULL) AS MISSING_OUTPUT,
    COUNT_IF(GROUND_TRUTH IS NOT NULL
             AND GROUND_TRUTH:ground_truth_output::STRING IS NOT NULL
             AND LEN(TRIM(GROUND_TRUTH:ground_truth_output::STRING)) = 0) AS BLANK_OUTPUT,
    TOTAL - NULL_GT - MISSING_OUTPUT - BLANK_OUTPUT AS VALID
FROM <DATABASE>.<SCHEMA>.<AGENT_NAME>_EVAL
GROUP BY SPLIT
ORDER BY SPLIT;
```

**Gate:** `VALID = TOTAL` for ALL splits. If any gaps → **HARD STOP**. List affected rows and require fixes before proceeding.

**STOP GATE:** Present split distribution table and GT validation results.

---

## Phase 4: Verify Ground Truth

This phase confirms that eval questions are actually answerable by the agent's semantic views.

Load `references/gt-verification.md` for the full methodology.

### Step 4.1: Run Verification Queries

For each INPUT_QUERY in the eval table:

```bash
cortex analyst query "<INPUT_QUERY>" --view=<SEMANTIC_VIEW_FQN>
```

If the agent has multiple semantic views, route each question to the most likely view based on `TEST_CATEGORY` or keyword matching.

### Step 4.2: Classify Results

| Result | Classification |
|---|---|
| Returns 1+ rows | PASS |
| Returns 0 rows | WARN — check if GT expects "no results" |
| Error / invalid SQL | FAIL |
| Analyst refuses query | WARN — may be out of scope |

### Step 4.3: Report and Gate

```
Ground Truth Verification: {PASS} PASS / {WARN} WARN / {FAIL} FAIL out of {TOTAL}
```

- **0 FAIL, 0 WARN:** Proceed.
- **FAIL > 0:** HARD STOP — fix or remove broken questions.
- **WARN only:** Soft gate — review. Edge-case questions expecting empty results are valid. Others should be fixed.

**STOP GATE:** Present verification report. User must acknowledge before proceeding.

---

## Phase 5: Generate YAML Configs + Upload to Stage

### Step 5.1: Create Stage

```sql
CREATE STAGE IF NOT EXISTS <DATABASE>.<SCHEMA>.AGENT_FLAG_TESTER_CONFIGS
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');
```

### Step 5.2: Generate YAML Files

Load `references/eval-config-template.yaml` as the template.

For each combination of:
- **Variant:** each selected variant from `<VARIANTS>` (2 or 3)
- **Split:** DEV, TEST (2)
- **Run slot:** r1 through r`<RUNS_PER_SPLIT>` (N)

Generate a YAML file: `config_{variant}_{split}_r{N}.yaml`

Substitutions per file:
- `{DATABASE}`, `{SCHEMA}` — from parameters
- `{VIEW_NAME}` — `<AGENT_NAME>_EVAL_DEV` or `<AGENT_NAME>_EVAL_TEST`
- `{DATASET_NAME}` — `<AGENT_NAME>_{variant}_{split}_ds_r{N}` (unique per slot to avoid version lock conflicts)
- `{AGENT_FQN}` — `<DATABASE>.<SCHEMA>.<AGENT_NAME>_{SUFFIX}`
- `{VARIANT}` — variant suffix name
- `{DESCRIPTION}` — `"Flag test: {VARIANT} variant, {SPLIT} split, run {N}"`

Total files: `len(<VARIANTS>) × 2 × <RUNS_PER_SPLIT>` (e.g., 3 variants × 2 splits × 3 runs = 18)

### Step 5.3: Upload to Stage

Write each YAML to a local temp file and PUT to stage:
```sql
PUT 'file:///tmp/config_{variant}_{split}_r{N}.yaml'
    @<DATABASE>.<SCHEMA>.AGENT_FLAG_TESTER_CONFIGS/
    AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
```

### Step 5.4: Verify Upload

```sql
LIST @<DATABASE>.<SCHEMA>.AGENT_FLAG_TESTER_CONFIGS/;
```

Confirm file count matches expected (3 × 2 × `<RUNS_PER_SPLIT>`).

**STOP GATE:** Show config summary (variants × splits × runs = total files). Confirm before firing evals.

---

## Phase 6: Fire Eval Runs

### Step 6.1: Launch All Runs

Fire all runs simultaneously — they execute asynchronously:

```sql
-- Repeat for each config file
CALL EXECUTE_AI_EVALUATION(
    'START',
    OBJECT_CONSTRUCT('run_name', '<RUN_PREFIX>_{variant}_{split}_r{N}'),
    '@<DATABASE>.<SCHEMA>.AGENT_FLAG_TESTER_CONFIGS/config_{variant}_{split}_r{N}.yaml'
);
```

Use `snow sql` CLI to bypass CoCo SQL timeout for system functions:
```bash
snow sql -c <CONNECTION> -q "
    USE DATABASE <DATABASE>;
    USE SCHEMA <SCHEMA>;
    CALL EXECUTE_AI_EVALUATION(
        'START',
        OBJECT_CONSTRUCT('run_name', '<RUN_PREFIX>_{variant}_{split}_r{N}'),
        '@<DATABASE>.<SCHEMA>.AGENT_FLAG_TESTER_CONFIGS/config_{variant}_{split}_r{N}.yaml'
    );
"
```

Fire all calls in rapid succession (background with `&` in bash if needed). Each returns immediately.

### Step 6.2: Poll for Completion

Poll every 60 seconds using STATUS:

```sql
CALL EXECUTE_AI_EVALUATION(
    'STATUS',
    OBJECT_CONSTRUCT('run_name', '<RUN_PREFIX>_{variant}_{split}_r{N}'),
    '@<DATABASE>.<SCHEMA>.AGENT_FLAG_TESTER_CONFIGS/config_{variant}_{split}_r{N}.yaml'
);
```

Status values: `CREATED` → `INVOCATION_IN_PROGRESS` → `INVOCATION_COMPLETED` → `COMPUTATION_IN_PROGRESS` → `COMPLETED`

Alternative: use `GET_AI_EVALUATION_DATA` to check for scored results:
```sql
SELECT COUNT(*) AS COMPLETED_METRICS
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>_{SUFFIX}', 'CORTEX AGENT',
    '<RUN_PREFIX>_{variant}_{split}_r{N}'
))
WHERE METRIC_NAME IS NOT NULL;
```

`COMPLETED_METRICS > 0` = done.

### Step 6.3: Handle Failures

If "Dataset version already exists" error:
1. Wait 2-3 minutes and retry that slot
2. If persists 5+ min, clear stale lock:
   ```sql
   ALTER DATASET <DATABASE>.<SCHEMA>.<DATASET_NAME>
   DROP VERSION 'SYSTEM_AI_OBS_CORTEX_AGENT_DATASET_VERSION_DO_NOT_DELETE';
   ```
3. **Never drop the dataset itself** — only the version lock

If a run reports `PARTIALLY_COMPLETED`: check `STATUS_DETAILS` array for error messages.

### Step 6.4: Confirm All Complete

All runs must reach `COMPLETED` before proceeding. Report:
```
Eval Runs: {COMPLETED}/{TOTAL} complete
  BASE_DEV:  r1 ✓  r2 ✓  r3 ✓
  BASE_TEST: r1 ✓  r2 ✓  r3 ✓
  AGENTIC_DEV:  r1 ✓  r2 ✓  r3 ✓
  ...
```

---

## Phase 7: Extract Results + Recommend

### Step 7.1: Extract Aggregate Scores

For each variant × split, compute mean ± stddev across all `<RUNS_PER_SPLIT>` runs:

```sql
SELECT METRIC_NAME,
       ROUND(AVG(EVAL_AGG_SCORE) * 100, 1) AS MEAN_PCT,
       ROUND(STDDEV(EVAL_AGG_SCORE) * 100, 1) AS STDDEV_PCT,
       COUNT(*) AS N
FROM (
    SELECT * FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
        '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>_{SUFFIX}', 'CORTEX AGENT',
        '<RUN_PREFIX>_{variant}_{split}_r1'
    ))
    UNION ALL
    SELECT * FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
        '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>_{SUFFIX}', 'CORTEX AGENT',
        '<RUN_PREFIX>_{variant}_{split}_r2'
    ))
    -- ... repeat through r<RUNS_PER_SPLIT>
)
WHERE METRIC_NAME IS NOT NULL
GROUP BY METRIC_NAME;
```

### Step 7.2: Build Comparison Table

Present a summary table:

| Variant | answer_correctness DEV | answer_correctness TEST | logical_consistency DEV | logical_consistency TEST | tool_selection DEV | tool_selection TEST |
|---|---|---|---|---|---|---|
| BASE | X% ± S% | X% ± S% | X% ± S% | X% ± S% | X% ± S% | X% ± S% |
| AGENTIC | X% ± S% | X% ± S% | X% ± S% | X% ± S% | X% ± S% | X% ± S% |
| FASTPATH_OFF | X% ± S% | X% ± S% | X% ± S% | X% ± S% | X% ± S% | X% ± S% |

Bold the **winner per metric** (highest TEST mean).

### Step 7.3: Per-Question Divergence Analysis

Find questions where variants diverge significantly on TEST correctness:

```sql
-- For each run, get per-question scores across variants
-- Identify questions where MAX(score) - MIN(score) > 0.3 across variants
```

Present the top 10 most-divergent questions with per-variant scores.

### Step 7.4: Recommend Winner

Scoring logic:
1. **Primary:** Highest `answer_correctness` on TEST (mean across runs)
2. **Tiebreaker 1:** Highest `logical_consistency` on TEST
3. **Tiebreaker 2:** Highest `tool_selection_accuracy` on TEST
4. **Tiebreaker 3:** Lowest stddev (most consistent)

Present recommendation with reasoning.

**STOP GATE:** Ask user which variant to promote (or none). If promoting:
1. Apply winning flags to the original agent
2. Drop the 3 test variants
3. Clean up stage configs

---

## Phase 8: Optimization Handoff (Optional)

After promoting a winner, check if the `cortex-agent-optimization` skill is available in this plugin:

```bash
cortex plugin list | grep cortex-agent-toolkit
```

**If NOT_FOUND:** Skip this phase. Present final summary and proceed to Cleanup.

**If AVAILABLE:** Ask the user:

> "Flag winner selected and applied. Do you want to optimize the agent's instructions next?"
> 1. **Yes — start optimization loop** (recommended: instructions + flags interact)
> 2. **No — done for now**

If **Yes:**

1. Record the flag sweep baseline in a file the optimization skill can read:

   Write `flag_sweep_baseline.json` to the agent's workspace (or current directory):
   ```json
   {
     "sweep_date": "<TIMESTAMP>",
     "winning_variant": "<VARIANT_SUFFIX>",
     "winning_flags": {
       "EnableAgenticAnalyst": true,
       "DisableFastPath": true
     },
     "baseline_scores": {
       "answer_correctness": { "dev_mean": 0.XX, "test_mean": 0.XX },
       "logical_consistency": { "dev_mean": 0.XX, "test_mean": 0.XX },
       "tool_selection_accuracy": { "dev_mean": 0.XX, "test_mean": 0.XX }
     },
     "variant_agents_kept": ["<AGENT_NAME>_BASE", "<AGENT_NAME>_AGENTIC", "<AGENT_NAME>_FASTPATH_OFF"],
     "revalidation_interval": 3,
     "eval_table": "<DATABASE>.<SCHEMA>.<AGENT_NAME>_EVAL",
     "stage": "<DATABASE>.<SCHEMA>.AGENT_FLAG_TESTER_CONFIGS"
   }
   ```

2. **Do NOT drop variant agents** — keep them for re-validation after instruction changes.

3. Hand off to `cortex-agent-optimization` with the SETUP intent if no workspace exists,
   or OPTIMIZE intent if one already does. The optimization skill will detect
   `flag_sweep_baseline.json` and use it for re-validation triggers (see that skill's
   FLAG_REVALIDATION intent).

If **No:** Proceed to Cleanup (drop variants, clean stage).

---

## Cleanup

After the test is complete (and user chose NOT to optimize):

```sql
-- Drop variant agents
DROP AGENT IF EXISTS <DATABASE>.<SCHEMA>.<AGENT_NAME>_BASE;
DROP AGENT IF EXISTS <DATABASE>.<SCHEMA>.<AGENT_NAME>_AGENTIC;
DROP AGENT IF EXISTS <DATABASE>.<SCHEMA>.<AGENT_NAME>_FASTPATH_OFF;

-- Optionally remove stage configs
REMOVE @<DATABASE>.<SCHEMA>.AGENT_FLAG_TESTER_CONFIGS/;
DROP STAGE IF EXISTS <DATABASE>.<SCHEMA>.AGENT_FLAG_TESTER_CONFIGS;

-- Keep the eval table and views for future testing
```

If the user chose to optimize (Phase 8 = Yes), skip cleanup — the variant agents and
configs are needed for flag re-validation during the optimization loop.

---

## Key Learnings

- `EnableAgenticAnalyst=true` improves correctness but can reduce logical consistency
- `DisableFastPath=true` forces full reasoning — highest correctness, more latency
- BASE (non-agentic) often wins logical consistency due to simpler reasoning path
- Multi-hop questions (spanning 2+ semantic views) show biggest divergence between variants
- `EXECUTE_AI_EVALUATION` requires YAML config on a stage — no inline metric specification
- Agent and eval dataset MUST be in the same schema (task DAG resolves names relative to schema)
- `GET_AI_EVALUATION_DATA` score column is `EVAL_AGG_SCORE` (not `score` or `metric_value`)
- `GET_AI_EVALUATION_DATA` input column is `INPUT` (not `INPUT_QUERY`)
- Custom metrics use `{{tool_info}}` and `{{ground_truth}}` template variables
- Fire all eval runs simultaneously — they're async and independent
- Each run slot needs its own unique `dataset_name` to avoid version lock conflicts
