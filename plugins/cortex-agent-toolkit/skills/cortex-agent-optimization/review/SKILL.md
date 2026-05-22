---
name: cortex-agent-optimization-review
description: "Review iteration results and make accept/reject decision."
parent_skill: cortex-agent-optimization
---

## Step 1: Compute Per-Run Means

Read `metadata.yaml` for parameters if not already loaded. Read `optimization_log.md` to identify the **previous accepted iteration** name (or `baseline` if no iterations have been accepted yet).

Query per-run means for both the current iter and the previous accepted iter. For each, build a query per run (r1 through r`<RUNS_PER_SPLIT>`) — do NOT union them together:

```sql
-- Current iter, DEV split — repeat for r1 through r<RUNS_PER_SPLIT>
SELECT '<ITER_NAME>_dev_r1' AS RUN, METRIC_NAME,
       AVG(EVAL_AGG_SCORE) AS MEAN
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
  '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT', '<ITER_NAME>_dev_r1'
)) WHERE METRIC_NAME IS NOT NULL GROUP BY METRIC_NAME;
```

Run the same structure for TEST (`<ITER_NAME>_test_r1` through `_r<RUNS_PER_SPLIT>`), and for the previous accepted iteration's DEV and TEST runs (using the previous iter name from `optimization_log.md`).

Produce a paired difference table for each split and metric:

| Run | Metric | iter_mean | prev_mean | diff |
|-----|--------|-----------|-----------|------|
| r1  | answer_correctness | ... | ... | ... |
| r2  | answer_correctness | ... | ... | ... |
| ... | ... | ... | ... | ... |

Also compute aggregate (mean ± stddev across all `<RUNS_PER_SPLIT>` runs) for display purposes.

## Step 2: Apply Acceptance Criteria

For each metric, compute the **paired t-statistic** from the `<RUNS_PER_SPLIT>` per-run TEST differences:

```
d_i = iter_test_r_i_mean - prev_test_r_i_mean   (for i = 1 to RUNS_PER_SPLIT)
t = mean(d) / (stddev(d) / sqrt(RUNS_PER_SPLIT))
```

Compare t against the one-sided critical value (α = 0.10 — reject only if regression is statistically significant):

| runs_per_split | df | reject if t < |
|---|---|---|
| 3 | 2 | −1.886 |
| 4 | 3 | −1.638 |
| 5 | 4 | −1.533 |
| 6 | 5 | −1.476 |
| 8 | 7 | −1.415 |
| 10 | 9 | −1.383 |

- **ACCEPT** if t ≥ critical value for **all** metrics (no statistically significant regression on TEST)
- **REJECT** if t < critical value for **any** metric

## Step 3: Present Recommendation

**⚠️ STOP (supervised mode):** Present the accept/reject recommendation with full data. In autonomous mode: proceed with the recommendation automatically.

Present:
- DEV scores (mean ± stddev) + delta vs previous accepted iteration
- TEST scores (mean ± stddev) + delta vs previous accepted iteration
- Per-run paired differences and t-statistics for each TEST metric
- **Correctness Verdict Summary** (from first TEST run): Run the Comparison View query from `references/eval-setup.md` on `<ITER_NAME>_test_r1` and report category counts:
  - `BOTH_AGREE_CORRECT`: X questions
  - `FALSE_NEGATIVE`: X questions (agent correct, built-in penalized — these are NOT regressions)
  - `BOTH_AGREE_WRONG`: X questions (real failures remaining)
  - `LENIENT_BUILTIN`: X questions (real failures the built-in was lenient on)
- **Actionable verdict reasons** for any `BOTH_AGREE_WRONG` or `LENIENT_BUILTIN` questions — show the `verdict_reason` explanation
- Recommendation: **ACCEPT** or **REJECT** with t-statistic and critical value

**Decision signal priority:** When `answer_correctness` shows a regression but `factual_correctness_verdict` is stable or improved, the regression is likely format noise — do NOT reject on that basis alone. The verdict metric is the authoritative correctness signal.

Wait for user confirmation (supervised mode only).

## Step 4: Finalize Decision

### If ACCEPT:
1. Update `optimization_log.md` — mark the iteration's Decision as **ACCEPTED**, record final scores.
2. Note this as the new "last accepted iteration" for future comparisons.
3. Snapshot current `agent/*.md` files to `snapshots/<ITER_NAME>/`.
4. Reset the consecutive-rejection counter to 0 in `optimization_log.md`.

### If REJECT:
1. Update `optimization_log.md` — mark the iteration's Decision as **REJECTED** with the reason.
2. Increment the consecutive-rejection counter in `optimization_log.md`.
3. **If counter reaches 3:** Stop the optimization loop entirely. Report:
   - Remaining failures that could not be resolved
   - Summary of what was tried across all rejected iterations
   - Recommendation on whether architectural changes are needed (different tools, guardrails, workflow restructuring)
4. Restore `agent/*.md` files from the last accepted snapshot in `snapshots/` (the most recent accepted `<ITER_NAME>/` directory, or `baseline/` if no iterations have been accepted).
5. Rebuild and redeploy with reverted instructions:
   ```bash
   python <WORKSPACE_ROOT>/scripts/build_agent_spec.py
   <CLI_TOOL> sql --connection <CONNECTION> --filename <WORKSPACE_ROOT>/<AGENT_DIR>/deploy.sql
   ```
6. Verify revert: `DESCRIBE AGENT <AGENT_FQN>;`

## Step 5: Cumulative Summary

Update the summary section of `optimization_log.md`:

```markdown
## Summary: Baseline → <ITER_NAME>

| Metric | Baseline Combined | Current Combined | Delta |
|--------|------------------|-----------------|-------|
| [metric_1] | X% | Y% | +/-Z% |
| [metric_2] | X% | Y% | +/-Z% |

**Key learnings:**
- [What worked or didn't work in this iteration]
```

If accepted, the project is ready for the next iteration. Continue to `optimize/SKILL.md` when ready.

If rejected and consecutive-rejection counter < 3, revert is complete. Continue to `optimize/SKILL.md` with a different approach targeting the same or different failures.

If rejected and consecutive-rejection counter = 3, the optimization loop is terminated. Present the final summary and recommend next steps.
