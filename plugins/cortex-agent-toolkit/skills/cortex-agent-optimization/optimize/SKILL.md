---
name: cortex-agent-optimization-iterate
description: "Run a single optimization iteration: analyze DEV failures, edit instructions, build/deploy, eval."
parent_skill: cortex-agent-optimization
---

## Step 1: Read Context

Load project context:
- Read `metadata.yaml` to get all parameters (`<DATABASE>`, `<SCHEMA>`, `<AGENT_NAME>`, `<CONNECTION>`, `<CLI_TOOL>`, `<STAGE_PATH>`, `<DEV_DATASET_NAME>`, `<TEST_DATASET_NAME>`, `<DEV_SPLIT_VALUE>`, `<TEST_SPLIT_VALUE>`, `<EXECUTION_MODE>`, `<WORKSPACE_ROOT>`, `<AGENT_DIR>`, `<RUNS_PER_SPLIT>`).
- Read `optimization_log.md` — understand current scores, previous iterations, what's been tried, and the consecutive-rejection counter.
- Read `DEPLOYMENT_INSTRUCTIONS.md` (if it exists) for project-specific workflow details.
- Ask the user for the iteration name (`<ITER_NAME>`, e.g., `iter7`) or auto-increment from the last iteration in the log.
- **Check for unassigned feedback rows:** If `SELECT COUNT(*) FROM <EVAL_TABLE> WHERE SPLIT IS NULL` returns > 0, inform the user that promoted feedback rows exist but haven't been split-assigned yet. Suggest running `eval-data` Workflow A or C before proceeding, or acknowledge and continue.

**If resuming an interrupted iteration:** See `references/resume-iteration.md` for checkpoint detection queries and resume workflow.

## Step 2: Pre-flight Validation and DEV Eval

### Pre-flight: Ground Truth Completeness

**MANDATORY before firing any eval runs.** Run the GT completeness check from `eval-data/SKILL.md` Workflow E against the DEV view:

```sql
SELECT 
    COUNT(*) AS TOTAL_QUESTIONS,
    COUNT_IF(GROUND_TRUTH IS NULL 
             OR TRY_PARSE_JSON(GROUND_TRUTH):ground_truth_output::STRING IS NULL
             OR LEN(TRIM(TRY_PARSE_JSON(GROUND_TRUTH):ground_truth_output::STRING)) = 0) AS MISSING_GT
FROM <DATABASE>.<SCHEMA>.AGENT_EVAL_DEV;
```

- If `MISSING_GT = 0`: proceed to fire eval runs.
- If `MISSING_GT > 0`: **HARD STOP**. List the questions with `eval-data/SKILL.md` Workflow E Step 2 query. Do NOT fire eval runs — missing GT scores 0 and silently corrupts all metrics.

### Fire DEV Eval Runs

Fire all `<RUNS_PER_SPLIT>` DEV runs simultaneously — each uses its own slot config:
```sql
-- Fire all simultaneously (do not wait between calls)
CALL EXECUTE_AI_EVALUATION(
  'START',
  OBJECT_CONSTRUCT('run_name', '<ITER_NAME>_dev_r1'),
  '<STAGE_PATH>/eval_config_dev_r1.yaml'
);
-- Repeat immediately for r2 through r<RUNS_PER_SPLIT>, using eval_config_dev_r2.yaml etc.
```

Then poll all runs in parallel using the parallel polling pattern from `references/eval-polling.md` until every slot reports `COMPLETED_METRICS > 0`.

If "Dataset version already exists" error occurs on a slot:
- Wait 2-3 minutes and retry that slot.
- If persists 5+ min with no eval running on that slot, clear its stale lock:
  ```sql
  ALTER DATASET <DATABASE>.<SCHEMA>.<DEV_DATASET_NAME>_r<N>
  DROP VERSION 'SYSTEM_AI_OBS_CORTEX_AGENT_DATASET_VERSION_DO_NOT_DELETE';
  ```
- Other slots are unaffected — only clear the failing slot.
- **NEVER drop the dataset itself** — only the version lock.

## Step 3: Analyze DEV Failures

Query aggregate results across all `<RUNS_PER_SPLIT>` DEV runs. Build a UNION ALL query with one SELECT block per run (`<ITER_NAME>_dev_r1` through `<ITER_NAME>_dev_r<RUNS_PER_SPLIT>`):
```sql
SELECT METRIC_NAME,
       ROUND(AVG(EVAL_AGG_SCORE) * 100, 1) AS MEAN_SCORE_PCT,
       ROUND(STDDEV(EVAL_AGG_SCORE) * 100, 1) AS STDDEV_PCT,
       COUNT(*) AS N
FROM (
  SELECT * FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT', '<ITER_NAME>_dev_r1'
  ))
  UNION ALL
  SELECT * FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT', '<ITER_NAME>_dev_r2'
  ))
  -- ... add one UNION ALL block per run through r<RUNS_PER_SPLIT>
)
WHERE METRIC_NAME IS NOT NULL
GROUP BY METRIC_NAME;
```

### Step 3a: Correctness Comparison View

For the first DEV run (`<ITER_NAME>_dev_r1`), run the Correctness Comparison View from `references/eval-setup.md` to categorize each question. This separates real failures from format noise:

- **`BOTH_AGREE_WRONG` + `LENIENT_BUILTIN`** → Real failures. These drive instruction changes in Step 4-5.
- **`FALSE_NEGATIVE`** → Agent was actually correct. Do NOT try to fix these — instead consider updating the ground truth to be less prescriptive.
- **`BOTH_AGREE_CORRECT`** → No action needed.

Use the `verdict_reason` explanation from `factual_correctness_verdict` to understand exactly what was wrong or missing. This explanation is more actionable than the raw `answer_correctness` score for guiding instruction edits.

### Step 3b: Per-Question Failure Analysis

For per-question failure analysis, query individual question scores across all `<RUNS_PER_SPLIT>` runs. Filter to questions where the `factual_correctness_verdict` score is `0` (use this as the primary failure signal, not `answer_correctness < 1.0`).

Distinguish failure confidence:
- **High-confidence failures**: `factual_correctness_verdict = 0` in all `<RUNS_PER_SPLIT>` runs — these drive instruction changes.
- **Noise candidates**: Failed in only 1 of `<RUNS_PER_SPLIT>` runs — generally should not drive changes unless a clear pattern emerges across multiple questions.
- **False negatives**: `factual_correctness_verdict = 1` but `answer_correctness < 1.0` — the agent was correct. Flag these for ground truth review but do NOT fix the agent.

**CRITICAL: Only analyze DEV failures. Do NOT examine TEST results at this stage.**

### Step 3c: Populate Question Manifest

If `<AGENT_NAME>_QUESTION_MANIFEST` exists, INSERT DEV results per run using the pattern from `references/question-manifest.md` with `SOURCE='optimize_dev'`, `ITERATION='<ITER_NAME>'`, `VARIANT=NULL`. If the table doesn't exist, skip.

## Step 4: Classify Failures

### Step 4.0: Transfer Opportunity Check

Before classifying, query the manifest for failing questions that passed under a different flag config:

```sql
SELECT INPUT_TEXT, VARIANT AS passing_variant, SCORE
FROM <AGENT_NAME>_QUESTION_MANIFEST
WHERE SOURCE = 'flag_sweep' AND METRIC_NAME = 'answer_correctness' AND SCORE >= 0.8
  AND INPUT_ID IN (<failing INPUT_IDs from Step 3>);
```

If results exist, present them as context: the flag config may handle these questions differently. This informs classification but is not a gate. If no manifest exists, skip.

### Step 4.1: Classification Tree

Classify each high-confidence failure using this ordered decision tree. Evaluate conditions top-to-bottom; the first match is the classification.

1. **Routing Check:**
   
   **If `ground_truth_invocations` is provided (not NULL):**
   - Compare actual tool sequence to ground truth
   - If the first tool called differs from ground truth → **Routing error**
     - Fix: Add keyword triggers or negative routing rules to `orchestration_instructions.md`
   - If tools match → proceed to Step 2
   
   **If `ground_truth_invocations` is NULL:**
   - Ground truth does not specify expected tool sequence
   - Skip routing verification
   - Proceed directly to Step 2

2. **Check if any tool call returned an error/exception.** If yes → **Tool error.** Fix: add retry logic to `orchestration_instructions.md` ("retry up to 2x on transient errors before reporting failure").

3. **Compare answer structure to ground truth output.** If the facts are correct but the format/structure doesn't match → **Formatting error.** Fix: add explicit format templates to `response_instructions.md`.

4. **Compare answer content to ground truth output.** If facts are wrong, missing, or incomplete despite correct tool calls → **Content error.** Fix: add domain-specific rules or corrected examples to `response_instructions.md`.

5. **Re-read the current instructions that should govern this behavior.** If the instructions can reasonably be interpreted to produce the agent's (wrong) behavior → **Instruction ambiguity.** Fix: rewrite the ambiguous rule with a concrete example showing expected behavior.

6. **Check the optimization log for this failure pattern.** If the same failure has persisted across 2+ prior iterations despite targeted fixes → **Model behavior limit.** Fix: consider architectural changes (tool guardrails, workflow restructuring) or document as a known limitation.

For questions that failed in only 1 of `<RUNS_PER_SPLIT>` runs: classify as **Intermittent** — noise that should not drive instruction changes unless a clear cross-question pattern emerges.

**⚠️ STOP (supervised mode):** Present failure analysis with classifications and proposed instruction changes to the user. In autonomous mode: proceed if all failures have a single unambiguous classification; stop and ask if any failure has multiple plausible classifications or if the proposed change touches 3+ files.

**Optional: Deep-dive debugging**

For complex failures requiring detailed trace analysis, consider using bundled `debug-single-query-for-cortex-agent` skill:
- Provides GET_AI_RECORD_TRACE queries with span-level detail
- Analyzes observability logs for errors and warnings
- Useful when classification is ambiguous or when investigating tool execution issues

Example handoff: "I've identified 3 routing failures. Would you like me to deep-dive into request_id X using the debug skill?"

## Step 5: Edit Instructions

Before making changes, verify a snapshot of the current `agent/*.md` state exists in `snapshots/` (either `baseline/` or the last accepted iteration). If not, create one now.

Modify the relevant `agent/*.md` files based on the failure analysis. Follow optimization patterns (load `references/optimization-patterns.md`):
- **Prefer examples over verbose procedural rules**
- **Fix buggy examples** — agents faithfully reproduce them
- **Small, targeted changes** — one pattern per iteration
- **Add "WRONG" examples** — showing what NOT to do is effective
- **Don't over-strengthen rules** that failed 2+ iterations — diminishing returns

**⚠️ STOP (supervised mode):** Present the proposed instruction changes (diff) and get approval before building. In autonomous mode: proceed.

**Viewing changes:**
If `show_diff.py` exists in scripts/:
```bash
python scripts/show_diff.py --from snapshots/<last_iteration>/ --to agent/
```
Otherwise, manually review changed files in `agent/` directory.

## Step 6: Build and Deploy

```bash
python <WORKSPACE_ROOT>/scripts/build_agent_spec.py
<CLI_TOOL> sql --connection <CONNECTION> --filename <WORKSPACE_ROOT>/<AGENT_DIR>/deploy.sql
```

Verify deployment:
```sql
DESCRIBE AGENT <AGENT_FQN>;
```

## Step 7: Re-run DEV Eval

Fire all `<RUNS_PER_SPLIT>` DEV runs simultaneously using the same slot configs as Step 2, with post-edit run names (e.g., `<ITER_NAME>_dev_post_r1` through `<ITER_NAME>_dev_post_r<RUNS_PER_SPLIT>`). Poll all in parallel until every slot reports completion.

Apply the paired t-test to check for regression vs the previous accepted iteration's DEV means (same formula as `review/SKILL.md` Step 2, using DEV per-run means). If t < the critical value for `<RUNS_PER_SPLIT>` on any metric, the edit likely degraded performance — return to Step 5 and adjust. Otherwise proceed to TEST.

## Step 8: Run TEST Eval (only if DEV is satisfactory)

### Pre-flight: TEST Ground Truth Completeness

Run the same GT completeness check against the TEST view before firing TEST runs:
```sql
SELECT COUNT(*) AS TOTAL, 
       COUNT_IF(GROUND_TRUTH IS NULL 
                OR TRY_PARSE_JSON(GROUND_TRUTH):ground_truth_output::STRING IS NULL
                OR LEN(TRIM(TRY_PARSE_JSON(GROUND_TRUTH):ground_truth_output::STRING)) = 0) AS MISSING_GT
FROM <DATABASE>.<SCHEMA>.AGENT_EVAL_TEST;
```
If `MISSING_GT > 0`: **HARD STOP** — same as Step 2 pre-flight.

### Fire TEST Eval Runs

Fire all `<RUNS_PER_SPLIT>` TEST runs simultaneously — each uses its own slot config:
```sql
-- Fire all simultaneously (do not wait between calls)
CALL EXECUTE_AI_EVALUATION(
  'START',
  OBJECT_CONSTRUCT('run_name', '<ITER_NAME>_test_r1'),
  '<STAGE_PATH>/eval_config_test_r1.yaml'
);
-- Repeat immediately for r2 through r<RUNS_PER_SPLIT>, using eval_config_test_r2.yaml etc.
```

Poll all runs in parallel using the parallel polling pattern from `references/eval-polling.md` until every slot reports completion.

Handle dataset version lock errors per-slot per `references/eval-setup.md` lock troubleshooting.

### Step 8b: Populate Question Manifest (TEST)

If `<AGENT_NAME>_QUESTION_MANIFEST` exists, INSERT TEST results per run using the pattern from `references/question-manifest.md` with `SOURCE='optimize_test'`, `ITERATION='<ITER_NAME>'`, `VARIANT=NULL`. If the table doesn't exist, skip.

## Step 9: Log Results

Append the iteration to `optimization_log.md` with: run names, changes made, files changed, score table (DEV Mean ± StdDev | TEST Mean ± StdDev | Combined Mean per metric), comparison delta vs previous accepted iteration, and `Decision: PENDING`.

Continue to `review/SKILL.md` for the accept/reject decision.

## Step 10: Flag Re-validation Check (after review accepts)

**This step runs ONLY after `review/SKILL.md` returns an ACCEPT decision.**

Check if a flag sweep baseline exists:
```bash
ls <WORKSPACE_ROOT>/flag_sweep_baseline.json 2>/dev/null && echo "EXISTS" || echo "NONE"
```

**If NONE:** Skip — no flag sweep was done, so no re-validation needed.

**If EXISTS:** Read `flag_sweep_baseline.json` and count accepted iterations since the last flag validation:

1. Parse `revalidation_interval` from the baseline file (default: 3)
2. Count accepted iterations in `optimization_log.md` since `sweep_date` (or last re-validation date)
3. If count >= `revalidation_interval`:

   Present to user:

   > "You've accepted {N} instruction iterations since the last flag validation on {DATE}.
   > Instruction changes can shift which flag config performs best.
   > Want to re-validate the flag choice now?"
   > 1. **Yes — run flag re-validation** (recommended)
   > 2. **Skip for now** — continue optimizing, ask again after next accept
   > 3. **Disable** — never auto-check (remove flag_sweep_baseline.json)

   If **Yes:** Route to `flag-sweep/SKILL.md` with `mode=REVALIDATE`. That workflow will:
   - Re-use the existing variant agents (listed in `variant_agents_kept`)
   - Apply the CURRENT instructions to all variants (rebuild each variant with latest instructions + its flag config)
   - Run fresh evals and compare to the baseline scores
   - If the winner shifts or scores degrade >10%, HARD STOP for user decision
   - Update `flag_sweep_baseline.json` with new scores and reset the iteration counter

   If **Skip:** Increment a `deferred_count` in the baseline file. Ask again after the next accept.

   If **Disable:** Delete `flag_sweep_baseline.json`. No further auto-checks.
