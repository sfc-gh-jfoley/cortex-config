# SV Optimization — Optimize (One Iteration)

> Procedural reference for the `sv-iterative-optimizer` skill. Loaded by the router in `SKILL.md` (OPTIMIZE intent). Not independently invokable.

## Prerequisites

Setup phase must be complete (`references/setup.md` has run):
- `SV_FQN`, `BASELINE_SCORE`, `ACCEPT_THRESHOLD`, `EVAL_QUESTIONS`, `REPEATS`, `RUN`, `CAND_FQN`, `OPTIMIZATION_LOG_TABLE` are set
- All writes target `CAND_FQN`; run `python3 scripts/candidate.py guard --source <SV_FQN> --target <CAND_FQN>` before each one. Production is never modified here (see `references/candidate-promotion.md`).
- `_SV_TOOLKIT_META.OPTIMIZATION_LOG` exists

---

## Step 1: Load Current SV State

```sql
-- Current candidate DDL (the working copy being mutated)
SELECT GET_DDL('SEMANTIC_VIEW', '<CAND_FQN>');
```

Save the result as `CURRENT_DDL`. Get most recent score as `SCORE_BEFORE`:
```sql
SELECT run_name, mean_score
FROM <DB>._SV_TOOLKIT_META.EVAL_HISTORY
WHERE sv_fqn = '<SV_FQN>'
ORDER BY run_timestamp DESC
LIMIT 1;
```

---

## Step 2: Analyze Recent Failures

Get the most recent eval run name, then query failures:
```sql
WITH raw AS (
  SELECT INPUT, OUTPUT, GROUND_TRUTH, ERROR, EVAL_AGG_SCORE, METRIC_STATUS, METRIC_CALLS
  FROM TABLE(SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA(
    '<DB>', '<SCHEMA>', '<SV_FQN>', 'SEMANTIC VIEW', '<latest_run_name>'
  ))
  WHERE METRIC_NAME = 'sql_correctness'
)
SELECT
  INPUT AS question,
  OUTPUT AS generated_sql,
  GROUND_TRUTH AS reference_sql,
  EVAL_AGG_SCORE AS sql_correctness,
  ERROR AS error_message
FROM raw
WHERE sql_correctness < 1.0
ORDER BY sql_correctness ASC;
```

Map failures to mutation operators using the table in `SKILL.md` (Mutation Strategy section).
Select the operator that addresses the most common failure pattern.

---

## Step 3: Apply Mutation

Select ONE mutation operator from `references/mutation-operators.md`. Apply it to the SV DDL.

For operators 1-10, build the prompt with `scripts/mutate.py get-prompt <operator> <candidate_ddl_path> --failures-file <f>`
(failure format: "Failure summary format" in `references/eval-data.md`). Operators 11-13 are described in
`references/mutation-operators.md` and have no template.

For LLM-assisted mutations (descriptions, synonyms), use CORTEX.COMPLETE:
```sql
-- COMPLETE needs a literal model name. Resolve one at runtime: probe candidates
-- in the quality tier (a larger reasoning model — mutation benefits from it) and
-- keep the first that returns without a "model unavailable" error. Ask the
-- operator which models their account has enabled. Do not hardcode a version.
SELECT SNOWFLAKE.CORTEX.COMPLETE(
    '<COMPLETE_MODEL>',
    '<prompt_from_mutate.py_get-prompt>'
) AS mutated_ddl;
```

For structural mutations (add metric, change relationship), generate DDL changes directly.

Save proposed DDL as `CANDIDATE_DDL`.

**STOP GATE (INTERACTIVE mode):** Show the proposed change and wait for approval:
```
Proposed mutation: <OPERATOR>
Target: <column/relationship being changed>
Change: <before → after>

Apply this change and run evaluation? (yes / skip / different mutation)
```

**AUTONOMOUS mode:** apply the proposed mutation and run the evaluation — no wait.

---

## Step 4: Deploy Mutation to the Candidate

Mutate only the candidate. Because a candidate is created with plain `CREATE SEMANTIC VIEW`, apply a mutation by creating a fresh candidate for this iteration from `CANDIDATE_DDL`:

```bash
ITER_CAND=$(python3 scripts/candidate.py name --source <SV_FQN> --kind cand --run "$(python3 scripts/candidate.py new-run | jq -r .run)" | jq -r .candidate)
python3 scripts/candidate.py guard --source <SV_FQN> --target "$ITER_CAND"
python3 scripts/candidate.py rewrite-ddl --source <SV_FQN> --candidate "$ITER_CAND" < candidate_ddl.sql > iter.sql
python3 scripts/candidate.py register manifest.json --run <RUN> --source <SV_FQN> --candidate "$ITER_CAND" --ddl-file iter.sql
```

`candidate_ddl.sql` must be the full DDL (a GET_DDL result with the mutation applied). Deploy `iter.sql`; if the name exists, stop. If deploy fails, report the error, discard `ITER_CAND`, STOP. The previous candidate stays the fallback.

---

## Step 5: Evaluate

Route to `sv-evaluation` for `ITER_CAND` with the Cortex Analyst contract:
- `analyst_params` + `source_metadata.type: verified_queries`, listing only `EVAL_QUESTIONS` (the hold-out set; guide VQRs are not scored)
- `sql_correctness` pinned to `v3`; never compare against a score from another metric version
- Run it `REPEATS` times (>=2) on the same question list; record each as `EVAL_RUN_NAME_i`
- Candidates have no materializations; the baseline was measured without them as well

After eval completes, get score:
```sql
SELECT AVG(EVAL_AGG_SCORE) AS score_after,
       SUM(CASE WHEN EVAL_AGG_SCORE = 1.0 THEN 1 ELSE 0 END) AS perfect,
       SUM(CASE WHEN EVAL_AGG_SCORE = 0.0 THEN 1 ELSE 0 END) AS failed
FROM TABLE(SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA(
  '<DB>', '<SCHEMA>', '<ITER_CAND_NAME>', 'SEMANTIC VIEW', '<EVAL_RUN_NAME_i>'
))
WHERE METRIC_NAME = 'sql_correctness';
```

Store `SCORE_AFTER` as the mean over the repeats. Compute `SCORE_BEFORE` the same way (mean of >=2 runs of the previous state on the same question list); a single earlier run is not enough.

---

## Step 6: Accept or Reject

`ACCEPT_THRESHOLD` comes from setup (twice the observed run-to-run range, at least one question's worth).

**ACCEPT if:**
- `SCORE_AFTER - SCORE_BEFORE >= ACCEPT_THRESHOLD`, and the per-repeat scores of the candidate do not overlap the previous state's range
- No regressions that persist across repeats (a previously-passing question failing in every repeat)

**REJECT otherwise.**

**On ACCEPT:** `ITER_CAND` becomes the working candidate (`candidate.py set-status ... --status evaluated`).
**On REJECT:** discard `ITER_CAND` (mark `discarded`; drop only via the exact names from `candidate.py cleanup-plan`, gate `SV-CANDIDATE-CLEANUP`). Production is never touched and needs no revert.

**Applying a result to production** is a separate step through gate `SV-PROMOTE` (OPERATOR_REQUIRED in both modes): retarget consumers or apply the full approved DDL with `CREATE OR ALTER` after saving a rollback copy. See `references/candidate-promotion.md`.

---

## Step 7: Write to OPTIMIZATION_LOG

Dollar-quote free text so embedded quotes cannot break the statement (the text must not itself contain `$$`):

```sql
INSERT INTO <DB>._SV_TOOLKIT_META.OPTIMIZATION_LOG
    (ITERATION_ID, SV_FQN, MUTATION_OPERATOR, MUTATION_DESCRIPTION,
     EVAL_SCORE_BEFORE, EVAL_SCORE_AFTER, REGRESSIONS, DECISION, DDL_SNAPSHOT, NOTES)
VALUES (
    CONCAT($$<SV_NAME>$$, '_iter_', TO_CHAR(CURRENT_TIMESTAMP(), 'YYYYMMDD_HH24MISS')),
    $$<SV_FQN>$$,
    $$<OPERATOR>$$,
    $$<description of what was changed>$$,
    <SCORE_BEFORE>,
    <SCORE_AFTER>,
    <REGRESSION_COUNT>,
    $$<ACCEPTED|REJECTED>$$,
    $$<ITER_CAND DDL if accepted, else CURRENT_DDL>$$,
    $$<optional notes: candidate name, metric version v3, repeats, per-run scores>$$
);
```

---

## Step 8: Report and Next Action

```
Iteration Result
────────────────────────────────
Operator:    <OPERATOR>
Score:       <SCORE_BEFORE> → <SCORE_AFTER> (<delta>%)
Regressions: <N>
Decision:    ACCEPTED / REJECTED
────────────────────────────────
```

Check termination conditions (from `SKILL.md`):
- Target reached → celebrate and stop
- 3 consecutive rejections → suggest sv-gepa-optimizer
- Otherwise → offer to run another iteration
