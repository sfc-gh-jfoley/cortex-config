# Flag Sweep — Multi-Agent Flag Comparison Evaluation

## Purpose

Compare multiple Cortex Agent variants side-by-side using the same eval dataset.
Typical use case: testing feature flags (EnableAgenticAnalyst, DisableFastPath, etc.)
across agent clones to measure the impact of each flag on correctness and consistency.

This sub-skill can be invoked standalone OR as part of the feedback loop with
the optimize workflow (see "Re-validation After Instruction Changes" below).

## Prerequisites

- An eval dataset table with INPUT_QUERY (VARCHAR) and GROUND_TRUTH (VARIANT) columns
- Two or more agent variants deployed in the **same schema** as the eval table
- `snow` CLI installed with a named connection
- Role with: `SNOWFLAKE.CORTEX_USER`, `EXECUTE TASK ON ACCOUNT`, `USAGE`/`CREATE DATASET ON SCHEMA`

## Critical Constraint: Schema Co-location

The eval system's task DAG resolves agent names relative to the task's schema,
ignoring the fully-qualified name you provide. This means:

**Agents and the eval dataset table MUST be in the same Snowflake schema.**

If agents are in `DB.SCHEMA_A` and the eval table is in `DB.SCHEMA_B`, the
COMPUTE_METRICS tasks will fail with "Cortex Agent does not exist."

## Workflow

### Step 1: Define the Sweep Matrix

Ask the user (or read from a config) which flags to compare. Default matrix:

| Variant Name | EnableAgenticAnalyst | DisableFastPath |
|---|---|---|
| BASE | false | (default) |
| AGENTIC | true | (default) |
| FASTPATH_OFF | true | true |

The user can select a subset (e.g., AGENTIC + FASTPATH_OFF only) or define custom variants.

**STOP GATE:** Confirm the variant matrix with the user before proceeding.

### Step 2: Deploy Agent Variants

For each row in the matrix, create (or verify) an agent in the target schema.

```sql
CREATE AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>_{SUFFIX}
FROM SPECIFICATION $$
<modified_spec_json>
$$;
```

Use `CHR(39)` escaping if the spec contains literal `$$` in instruction text.
Name convention: `{BASE_AGENT}_{VARIANT_SUFFIX}` (e.g., MY_AGENT_BASE, MY_AGENT_AGENTIC).

**STOP GATE:** Show the deploy SQL for each variant and ask for confirmation.

### Step 3: Prepare Eval Dataset

Ensure the eval table exists in the same schema as the agents:
```sql
USE DATABASE <DATABASE>;
USE SCHEMA <SCHEMA>;
SELECT COUNT(*) FROM <EVAL_TABLE>;
```

Validate GROUND_TRUTH column format:
```sql
SELECT INPUT_QUERY,
       GROUND_TRUTH:ground_truth_output::STRING IS NOT NULL AS has_gt
FROM <EVAL_TABLE>
WHERE NOT has_gt;
-- Should return 0 rows
```

If ground truth validation fails, **HARD STOP** — list affected rows and require fixes.

### Step 4: Generate YAML Configs + Upload to Stage

Create a stage for configs:
```sql
CREATE STAGE IF NOT EXISTS <DATABASE>.<SCHEMA>.FLAG_SWEEP_CONFIGS
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');
```

Load `references/eval-setup.md` for the YAML template. For each combination of:
- **Variant:** each selected variant
- **Split:** DEV, TEST
- **Run slot:** r1 through r`<RUNS_PER_SPLIT>`

Generate a YAML file: `config_{variant}_{split}_r{N}.yaml`

Substitutions per file:
- `table_name` → `<DATABASE>.<SCHEMA>.<EVAL_VIEW>` (DEV or TEST view)
- `dataset_name` → `<AGENT_NAME>_{variant}_{split}_ds_r{N}` (unique per slot)
- `agent_name` → `<DATABASE>.<SCHEMA>.<AGENT_NAME>_{SUFFIX}`
- `description` → `"Flag sweep: {VARIANT} variant, {SPLIT} split, run {N}"`

Upload each to the stage:
```sql
PUT 'file:///tmp/config_{variant}_{split}_r{N}.yaml'
    @<DATABASE>.<SCHEMA>.FLAG_SWEEP_CONFIGS/
    AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
```

Verify:
```sql
LIST @<DATABASE>.<SCHEMA>.FLAG_SWEEP_CONFIGS/;
```

**STOP GATE:** Show config summary (variants x splits x runs = total files).

### Step 5: Launch Evals

Fire all runs simultaneously via `snow` CLI (bypasses CoCo SQL timeout):

```bash
snow sql -c <CONNECTION> -q "
    USE DATABASE <DATABASE>;
    USE SCHEMA <SCHEMA>;
    CALL EXECUTE_AI_EVALUATION(
        'START',
        OBJECT_CONSTRUCT('run_name', '<RUN_PREFIX>_{variant}_{split}_r{N}'),
        '@<DATABASE>.<SCHEMA>.FLAG_SWEEP_CONFIGS/config_{variant}_{split}_r{N}.yaml'
    );
"
```

Fire all calls in rapid succession. Each returns immediately (async).

### Step 6: Poll for Completion

Poll every 60 seconds using `GET_AI_EVALUATION_DATA`:

```sql
SELECT COUNT(*) AS COMPLETED_METRICS
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>_{SUFFIX}', 'CORTEX AGENT',
    '<RUN_PREFIX>_{variant}_{split}_r{N}'
))
WHERE METRIC_NAME IS NOT NULL;
```

`COMPLETED_METRICS > 0` = done.

Alternative — use STATUS check:
```sql
CALL EXECUTE_AI_EVALUATION(
    'STATUS',
    OBJECT_CONSTRUCT('run_name', '<RUN_PREFIX>_{variant}_{split}_r{N}'),
    '@<DATABASE>.<SCHEMA>.FLAG_SWEEP_CONFIGS/config_{variant}_{split}_r{N}.yaml'
);
```

Handle "Dataset version already exists" per `references/eval-setup.md` lock troubleshooting.

Report progress:
```
Eval Runs: {COMPLETED}/{TOTAL} complete
  BASE_DEV:  r1 done  r2 done  r3 done
  BASE_TEST: r1 done  r2 running  r3 done
  ...
```

### Step 7: Extract Results + Populate Question Manifest

**7a: Create manifest table (if not exists)**

Load `references/question-manifest.md` for the DDL. Create the table:
```sql
CREATE TABLE IF NOT EXISTS <DATABASE>.<SCHEMA>.<AGENT_NAME>_QUESTION_MANIFEST (...);
-- Full DDL in references/question-manifest.md
```

**7b: INSERT per-question scores into manifest**

For each variant x split x run, INSERT results using the pattern from `references/question-manifest.md`:
```sql
INSERT INTO <DATABASE>.<SCHEMA>.<AGENT_NAME>_QUESTION_MANIFEST
    (INPUT_ID, INPUT_TEXT, METRIC_NAME, SCORE, SOURCE, RUN_LABEL, VARIANT, ITERATION, AGENT_FQN, DURATION_MS, LLM_CALL_COUNT, ERROR)
SELECT INPUT_ID, INPUT, METRIC_NAME, EVAL_AGG_SCORE,
    'flag_sweep',
    '<RUN_PREFIX>_{variant}_{split}_r{N}',
    '<VARIANT>',
    NULL,
    '<DATABASE>.<SCHEMA>.<AGENT_NAME>_{SUFFIX}',
    DURATION_MS, LLM_CALL_COUNT, ERROR
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>_{SUFFIX}', 'CORTEX AGENT',
    '<RUN_PREFIX>_{variant}_{split}_r{N}'
))
WHERE METRIC_NAME IS NOT NULL;
```

**7c: Aggregate scores per variant per metric**

For each variant x split, compute mean +/- stddev across all runs:

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

**Per-question divergence analysis:**

Find questions where variants diverge significantly on TEST correctness.
For each variant, get per-question scores from `GET_AI_EVALUATION_DATA` (column `INPUT` for question text,
`EVAL_AGG_SCORE` for score, `METRIC_NAME` to filter). Identify questions where
MAX(score) - MIN(score) > 0.3 across variants.

Present the top 10 most-divergent questions with per-variant scores.

### Step 8: Report and Recommend

Present a summary table:

| Variant | answer_correctness DEV | answer_correctness TEST | logical_consistency DEV | logical_consistency TEST |
|---|---|---|---|---|
| BASE | X% +/- S% | X% +/- S% | X% +/- S% | X% +/- S% |
| AGENTIC | X% +/- S% | X% +/- S% | X% +/- S% | X% +/- S% |
| FASTPATH_OFF | X% +/- S% | X% +/- S% | X% +/- S% | X% +/- S% |

Bold the **winner per metric** (highest TEST mean).

Scoring logic:
1. **Primary:** Highest `answer_correctness` on TEST (mean across runs)
2. **Tiebreaker 1:** Highest `logical_consistency` on TEST
3. **Tiebreaker 2:** Lowest stddev (most consistent)

**STOP GATE:** Ask the user which variant to promote (or none).

If promoting:
1. Apply winning flags to the original agent
2. Drop the variant agents
3. Record the winning flags and scores in `optimization_log.md` (if it exists)
4. Clean up stage configs

## Re-validation After Instruction Changes

This sub-skill supports a feedback loop with the optimize workflow:

**When to re-validate:** After every 3 accepted optimization iterations (or on user request),
the optimize workflow should trigger a flag re-validation to confirm the current flag choice
still holds under the updated instructions.

**Re-validation flow:**
1. The optimize workflow calls this sub-skill with `mode=REVALIDATE`
2. Skip Steps 1-3 (variants and dataset already exist from initial sweep)
3. Generate fresh YAML configs pointing at the current (instruction-modified) variant agents
4. Run Steps 5-8 as normal
5. Compare new scores to the **initial sweep baseline** (stored in `optimization_log.md`)
6. If the winner changes:
   - **HARD STOP** — present the shift to the user
   - Apply new winning flags to the original agent
   - Resume optimization with the new flag config
7. If the winner holds: log confirmation and continue optimization

**Detecting flag/instruction interaction:**
- If a metric drops >10% from the initial sweep baseline on the current winner, flag it even if the winner doesn't change — the instructions may be degrading the flag config's strengths.
- If stddev increases significantly (>2x initial), the instructions may be introducing inconsistency.

## Key Learnings from Flag Sweep Testing

- EnableAgenticAnalyst=true improves correctness but can reduce logical consistency
- DisableFastPath=true (with agentic) gives the highest correctness by forcing full reasoning
- The BASE (non-agentic) agent is often most logically consistent because it follows a simpler path
- Multi-hop questions (spanning 2+ semantic views) show the biggest divergence between variants
- EXECUTE_AI_EVALUATION requires YAML config on a stage — no inline metric specification
- Agent and eval dataset MUST be in the same schema (task DAG resolves names relative to schema)
- GET_AI_EVALUATION_DATA score column is `EVAL_AGG_SCORE` (not `score` or `metric_value`)
- GET_AI_EVALUATION_DATA input column is `INPUT` (not `INPUT_QUERY`)
- Fire all eval runs simultaneously — they're async and independent
- Each run slot needs its own unique `dataset_name` to avoid version lock conflicts
