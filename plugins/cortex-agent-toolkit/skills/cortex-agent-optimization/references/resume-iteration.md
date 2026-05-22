# Resuming Interrupted Iterations

If an optimization iteration is interrupted (network issue, timeout, stale version lock), use this workflow to resume from the last checkpoint.

## Step 1: Identify Iteration State

Check what completed. Build a UNION ALL query for all runs `<ITER_NAME>_dev_r1` through `<ITER_NAME>_dev_r<RUNS_PER_SPLIT>` (read `<RUNS_PER_SPLIT>` from `metadata.yaml`):

```sql
-- Repeat one SELECT block per run r1 through r<RUNS_PER_SPLIT>
SELECT '<ITER_NAME>_dev_r1' AS RUN_NAME, COUNT(*) AS COMPLETED
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
  '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT', '<ITER_NAME>_dev_r1'
)) WHERE METRIC_NAME IS NOT NULL
UNION ALL
SELECT '<ITER_NAME>_dev_r2', COUNT(*)
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
  '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT', '<ITER_NAME>_dev_r2'
)) WHERE METRIC_NAME IS NOT NULL;
-- ... add blocks through r<RUNS_PER_SPLIT>

-- Repeat for TEST runs (_test_r1 through _test_r<RUNS_PER_SPLIT>)
```

**Interpretation:**
- `COMPLETED = 0`: Run not started or failed
- `COMPLETED > 0`: Run completed successfully

## Step 2: Resume from Checkpoint

| Checkpoint | What Completed | Resume Action |
|-----------|----------------|---------------|
| A | No DEV runs | Start from `optimize/SKILL.md` Step 2 |
| B | k of `<RUNS_PER_SPLIT>` DEV runs (k < N) | Re-fire the incomplete runs simultaneously using their slot configs (`eval_config_dev_r<k+1>.yaml` through `eval_config_dev_r<N>.yaml`); poll all in parallel |
| C | All `<RUNS_PER_SPLIT>` DEV runs | Proceed to Step 3 (failure analysis) |
| D | Analysis done, instructions edited | Rebuild and deploy (Step 6) |
| E | Deployed, no re-eval | Run re-eval DEV (Step 7) |
| F | k of `<RUNS_PER_SPLIT>` TEST runs (k < N) | Re-fire incomplete TEST runs simultaneously using their slot configs (`eval_config_test_r<k+1>.yaml` through `eval_config_test_r<N>.yaml`) |
| G | All `<RUNS_PER_SPLIT>` TEST runs done | Proceed to `review/SKILL.md` |

## Step 3: Clear Stale Locks if Needed

If a resumed run fails with "version already exists", clear only the stale lock on the specific slot that failed:

```sql
-- Clear the stale lock on the specific DEV slot that failed (replace _r<N> with the actual slot):
ALTER DATASET <DATABASE>.<SCHEMA>.<DEV_DATASET_NAME>_r<N>
DROP VERSION 'SYSTEM_AI_OBS_CORTEX_AGENT_DATASET_VERSION_DO_NOT_DELETE';

-- Repeat for TEST slot if needed:
ALTER DATASET <DATABASE>.<SCHEMA>.<TEST_DATASET_NAME>_r<N>
DROP VERSION 'SYSTEM_AI_OBS_CORTEX_AGENT_DATASET_VERSION_DO_NOT_DELETE';
```

Other slots are unaffected — only clear the specific slot that is stuck.

**NEVER drop the dataset itself** — only drop stale version locks.

## Step 4: Document Interruption

Add note to `optimization_log.md`:

```markdown
**Note:** Iteration interrupted at [checkpoint] on [timestamp]. Resumed from [checkpoint] on [timestamp].
```

## Common Interruption Scenarios

### Scenario 1: Network timeout during eval run

**Symptoms:** Eval started but query history shows incomplete

**Action:**
1. Use checkpoint detection query to see which runs completed
2. Clear stale version lock if present
3. Resume from next incomplete run

### Scenario 2: Dataset version lock stuck

**Symptoms:** "Dataset version already exists" error persists for 10+ minutes

**Action:**
1. Check Snowflake query history for running EXECUTE_AI_EVALUATION calls
2. If none running, clear the stale lock with ALTER DATASET ... DROP VERSION
3. Continue from the failed run

### Scenario 3: Iteration paused mid-analysis

**Symptoms:** DEV evals complete but no instruction changes made

**Action:**
1. Re-read `optimization_log.md` to see what was analyzed
2. Continue from Step 4 (classify failures)
3. Complete editing and deployment

### Scenario 4: Deployed but TEST not run

**Symptoms:** Agent deployed, DEV re-eval done, but no TEST runs

**Action:**
1. Verify deployment with `DESCRIBE AGENT <AGENT_FQN>`
2. Check DEV re-eval scores show no regression
3. Proceed to Step 8 (run TEST eval)

## Avoiding Interruptions

**Best practices:**
1. Use polling helper (`references/eval-polling.md`) to monitor progress
2. Set longer timeout_ms for eval SQL calls if network is slow
3. Complete full iterations in one session when possible
4. Save work frequently - commit instruction edits before deploying
