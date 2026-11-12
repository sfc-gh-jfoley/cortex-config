# Eval Polling and Results (canonical)

Config, launch, polling and result retrieval for Cortex Analyst evaluation of a semantic view.
Authoritative docs: "Cortex Analyst evaluations" (`EXECUTE_AI_EVALUATION`, `GET_ANALYST_AI_EVALUATION_DATA`).
Consumers: `skills/sv-evaluation/SKILL.md`, `skills/sv-gepa-optimizer/SKILL.md`.

Evaluations always target a **candidate** or the production view read-only; never edit production
to evaluate (see `candidate-promotion.md`).

## Config YAML

```yaml
evaluation:
  analyst_params:
    analyst_name: "<DB>.<SCHEMA>.<SV_NAME>"   # 3-part name
    analyst_type: "SEMANTIC VIEW"
  source_metadata:
    type: "verified_queries"                  # only supported source type
    # Optional subset, matched on each VQR's question text. Omit to use all VQRs.
    verified_queries:
      - "<question text>"

metrics:
  - name: "sql_correctness"
    version: "v3"                             # always pin
```

- Do not use `agent_params`, `dataset_name` or `source_metadata.type: dataset`; those are the Cortex Agent schema.
- **Pin the metric version.** An unversioned metric (or `auto`) resolves to `v1`, whose judge model
  went legacy on 2026-08-12; accounts that never used it cannot run it. Scores from different
  versions are not comparable, so keep one version across all runs you compare, and record it
  (`EVAL_HISTORY.metric_version`).
- Naming only `v3` tracks later minor releases; use `v3_0` to freeze exactly.

## Stage and upload

```sql
CREATE STAGE IF NOT EXISTS <DB>.<SCHEMA>.SV_EVAL_CONFIGS ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');
```

`CREATE STAGE IF NOT EXISTS` keeps earlier configs. Upload with `snow sql` (PUT is not available through
`sql_execute`); use a unique file name per run and `OVERWRITE = TRUE` only to re-upload the same run's file:

```bash
snow sql -c <conn> -q "PUT file:///tmp/<run_name>.yaml @<DB>.<SCHEMA>.SV_EVAL_CONFIGS AUTO_COMPRESS=FALSE OVERWRITE=TRUE"
```

Keep the YAML uncompressed. Do not put `FILE_FORMAT = (TYPE = 'YAML')` inline on `CREATE STAGE`.

## Launch and poll

```sql
CALL EXECUTE_AI_EVALUATION('START',  OBJECT_CONSTRUCT('run_name', '<run_name>'), '@<DB>.<SCHEMA>.SV_EVAL_CONFIGS/<run_name>.yaml');
CALL EXECUTE_AI_EVALUATION('STATUS', OBJECT_CONSTRUCT('run_name', '<run_name>'), '@<DB>.<SCHEMA>.SV_EVAL_CONFIGS/<run_name>.yaml');
-- also: 'CANCEL' and 'DELETE' (delete a finished run and its results; use it for run-name collisions)
```

Run names must be unique per semantic view. Poll `STATUS` about every 30 s. Observed status
progression (not documented; treat as informational):
`CREATED → INVOCATION_IN_PROGRESS → INVOCATION_COMPLETED → COMPUTATION_IN_PROGRESS → COMPLETED`.
Terminal failure states: `FAILED`, `CANCELLED`.

Timeout policy: 15 minutes of polling, then report the current status and stop. Do not retry
automatically and do not treat partial rows as a finished run; results are valid only after `COMPLETED`.

## Results

Results are keyed by the evaluated semantic view name and run name.

```sql
SELECT INPUT AS question, OUTPUT AS generated_output, GROUND_TRUTH AS reference_output,
       EVAL_AGG_SCORE AS sql_correctness, ERROR AS error_message, METRIC_STATUS, METRIC_CALLS
FROM TABLE(SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA(
       '<DB>', '<SCHEMA>', '<SV_NAME>', 'SEMANTIC VIEW', '<run_name>'))
WHERE METRIC_NAME = 'sql_correctness';
```

Columns: RECORD_ID, INPUT_ID, REQUEST_ID, TIMESTAMP (TIMESTAMP_LTZ), DURATION_MS, INPUT, OUTPUT, ERROR,
GROUND_TRUTH, METRIC_NAME, EVAL_AGG_SCORE, METRIC_TYPE (`system`/`custom`), METRIC_STATUS (VARIANT),
METRIC_CALLS (ARRAY of `{criteria, explanation}`).

Summary: `AVG(EVAL_AGG_SCORE)`, `COUNT(*)`, and counts where the score is `1.0`, between, and `0.0`.

## Repeat runs

SQL generation is non-deterministic, so the same pinned metric can score the same question set
differently between runs. Run the identical question list **at least twice** before gating on a
threshold, record each run, and use the spread to decide whether a change is real. Compare runs only
when they use the same question list and the same metric version.

## Concurrency and batching

- Do not start a second run against the same semantic view while one is running. This is observed
  behaviour (the second run reports `FAILED` / `Invocation failed`), not documented; verify before relying on it.
- Optimizer candidates are different semantic views, so runs for different candidates can be launched
  together; poll them one at a time.
- For large VQR sets use the `verified_queries` subset list and run batches sequentially (about 10 per
  batch by default). Aggregate scores over all batches afterwards.
- Name runs uniquely and traceably, e.g. `<SV>__<RUN>__g<gen>_c<n>` using the run id from `candidate.py new-run`.

## Required privileges

Held by a **single primary role** (evaluation tasks ignore secondary roles).

| Privilege | Object |
|---|---|
| `SNOWFLAKE.CORTEX_USER` database role | account |
| `USE AI FUNCTIONS` | account (granted to PUBLIC by default; revoked in some accounts) |
| `EXECUTE TASK` | account |
| `CREATE TASK`, `CREATE DATASET` | schema of the semantic view |
| `SELECT`, `MONITOR` | semantic view (and `SELECT` on its tables) |

Check with `SHOW GRANTS TO ROLE <role>`; direct-grant checks miss inherited and PUBLIC grants.

## Known errors

| Error | Cause | Fix |
|---|---|---|
| "Evaluation must contain 'source_metadata'" | Missing block | Add `source_metadata: {type: verified_queries}` inside `evaluation:` |
| "Model X does not exist or not authorized" | Bare SV name | Use the 3-part `DB.SCHEMA.SV` in `analyst_name` |
| Metric version unavailable | Judge model legacy / not allowed | Pin `v2` or `v3` |
| "Dataset version already exists" | Earlier run lock not released | Observed; `DELETE` the earlier run first, verify before dropping dataset versions manually |
| Stuck in `CREATED` | Unknown | Observed, undocumented. Check task history for the evaluation tasks; verify before relying on any workaround |
| Near-zero scores everywhere | VQR SQL does not run (see `vqr-eval-health.md`) or wrong SV | Run the VQR pre-flight checks first |

## SQL authoring caveat

The eval framework rewrites VQR SQL internally. Use the full expression in `GROUP BY` rather than a
SELECT alias (observed to fail after rewriting).
