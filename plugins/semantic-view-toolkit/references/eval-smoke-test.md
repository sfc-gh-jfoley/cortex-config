# Evaluation Smoke Test

Short end-to-end check that the Analyst evaluation pipeline works for one semantic view before a long
run. Uses the contract in `eval-polling.md` (config, pinned `v3`, results function). Run it against a
non-production or candidate view where possible; it only reads the view.

1. **Access and VQRs.** `DESCRIBE SEMANTIC VIEW <fqn>`; require at least 1 row with `"object_kind" = 'AI_VERIFIED_QUERY'` (use 3-5 for a meaningful check).
2. **Privileges.** `SHOW GRANTS TO ROLE <role>` against the table in `eval-polling.md`.
3. **Config.** Write the YAML from `eval-polling.md` with `verified_queries:` limited to 1-3 questions, `metrics: [{name: sql_correctness, version: v3}]`.
4. **Stage and upload.** `CREATE STAGE IF NOT EXISTS <DB>.<SCHEMA>.SV_EVAL_CONFIGS`, then `PUT` the file with `snow sql`.
5. **Start.** `CALL EXECUTE_AI_EVALUATION('START', OBJECT_CONSTRUCT('run_name', 'smoke_<timestamp>'), '@<DB>.<SCHEMA>.SV_EVAL_CONFIGS/<file>.yaml')`.
6. **Poll.** `'STATUS'` every 30 s until `COMPLETED` (15 min cap).
7. **Read.** Query `SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA(db, schema, sv, 'SEMANTIC VIEW', run)` filtered to `METRIC_NAME = 'sql_correctness'`; expect one row per selected question with a non-NULL `EVAL_AGG_SCORE`.
8. **Clean up.** `CALL EXECUTE_AI_EVALUATION('DELETE', OBJECT_CONSTRUCT('run_name', 'smoke_<timestamp>'), '<same config path>')`.

| Failure | Likely cause |
|---|---|
| Step 5 error about config | YAML does not match the Analyst schema (see `eval-polling.md`) |
| Step 5 permission error | Missing privilege or secondary role |
| Step 6 `FAILED` | Invalid SV, or judge model unavailable for the pinned version |
| Step 7 zero rows | Run not `COMPLETED`, wrong view name or run name |

A passing smoke test shows the pipeline works. It says nothing about accuracy: one run is not enough
to gate on a score (run the real question list at least twice).
