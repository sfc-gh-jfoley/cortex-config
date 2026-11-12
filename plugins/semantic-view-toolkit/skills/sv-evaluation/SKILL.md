---
name: sv-evaluation
description: >
  Evaluate semantic view accuracy with Cortex Analyst evaluation (EXECUTE_AI_EVALUATION).
  Measures sql_correctness by regenerating SQL for the view's verified queries (VQRs) and
  comparing results with the verified SQL. Use for baselines, regression checks, and failure analysis.
triggers:
  - evaluate semantic view
  - eval sv
  - run evaluation
  - check accuracy
  - test sv
  - score sv
  - how accurate is my semantic view
  - sv correctness
  - run sql_correctness
  - benchmark sv
---

# sv-evaluation

Config, polling, results, privileges and known errors live in `../../references/eval-polling.md`
(canonical). A quick end-to-end check is in `../../references/eval-smoke-test.md`. VQR pre-flight checks
are in `../../references/vqr-eval-health.md`.

**Evaluation contract (all runs):**
- Config uses `analyst_params` + `source_metadata.type: verified_queries`; metric `sql_correctness` with `version: "v3"` pinned. Unversioned resolves to `v1`, whose judge is legacy since 2026-08-12.
- Scores from different metric versions are not comparable. Record `metric_version` with every run.
- SQL generation is non-deterministic: run the **same question list at least twice** before gating on a threshold, and compare only runs with the same question list and metric version.
- Never modify the production view to evaluate or to fix it. Fixes happen on a candidate copy (`../../references/candidate-promotion.md`) and reach production only through gate `SV-PROMOTE`.

**Prerequisites:** the privileges in the table in `eval-polling.md` (all on one primary role) and at least one VQR embedded in the SV.

## Execution Mode

Inherits the session mode from the toolkit router (root `SKILL.md`). Never re-asks.

- **INTERACTIVE**: `STOP Gate (INTERACTIVE mode)` labels block for user input.
- **AUTONOMOUS**: judgment gates resolve to their documented defaults and log the resolution. Permanent blockers (missing grants, zero VQRs) terminate in both modes. SV-PROMOTE is never auto-resolved.

## Workflow

### Phase 1: Connect and validate

**Step 1: Identify the SV.** Ask for the fully qualified name (or take it from prior skill output).
Size check: if the serialized `GET_DDL('SEMANTIC_VIEW', '<fqn>')` is very large (roughly > 100,000 tokens; estimate by character count, treat as approximate), warn that results on an oversized SV may not reflect production behaviour and suggest splitting it first (`sv-discovery` / `sv-rearchitect`). Guideline, not a block.

**Step 2: Validate access.** `DESCRIBE SEMANTIC VIEW <fqn>`; on permission error report missing grants and stop.

**Step 3: Count VQRs.** Count distinct `object_name` where `"object_kind" = 'AI_VERIFIED_QUERY'` in the DESCRIBE output. If 0: report that evaluation needs VQRs, offer `vqr-generator`, and stop.

**Step 4: VQR health pre-check (read-only).** Run Checks 1-8 from `../../references/vqr-eval-health.md` (table reference format, column existence, CA-extension completeness, GROUP BY alias, coverage, aggregation mismatch, subquery SQL). For each metric with a conditional filter, flag VQRs that aggregate the same source column without that filter as **CONTAMINATED** (see `references/failure-analysis.md` category 8).
- INTERACTIVE (STOP Gate): offer (A) proceed and flag contaminated failures as REFERENCE_CONTAMINATED, (B) exclude them from this run.
- AUTONOMOUS default: A. Log `[AUTO-RESOLVED: EVAL-CONTAMINATED-VQR -> A]`.

If Check 3 finds a `with extension (CA='...')` block (column-drop risk): (A) evaluate a DDL-only **candidate** built by the Check 3 procedure, created and named through `candidate.py` (kind `cand`) and deployed with plain `CREATE SEMANTIC VIEW`; (B) proceed and mark results RESULTS_MAY_BE_UNRELIABLE; (C) abort. AUTONOMOUS default: A. Evaluation history is keyed by the evaluated view's name, so record both the candidate name and the source view.

**Step 5: VQR SQL dry-run.** VQR SQL is written against **logical** names, so it cannot run directly against physical tables. Never wrap the raw VQR SQL in a CTE and run it; that fails for valid VQRs.

Logical-name rule (per the CREATE SEMANTIC VIEW docs example): VQR SQL selects from the logical table (`FROM orders AS o`) and references logical dimension/fact names (`o.order_year`), not the physical column behind them. A physical column name appearing in VQR SQL is the defect. Whether to prefix logical tables with `__`: the DDL docs example uses bare names and the YAML form uses `__`; treat bare logical names as acceptable (style at most) and flag FQN/physical table references. This is the canonical statement; `vqr-eval-health.md` Checks 1-2 must agree with it. Verify against current docs before changing severity.

Recipe: run the shared **VQR Dry-Run** procedure in `../../references/vqr-eval-health.md` (it translates logical names through `DESCRIBE SEMANTIC VIEW`, then compiles and counts rows). Outcomes `PASS`, `EMPTY` and `FAIL` map to executes, empty result and review.
- Gate `EVAL-COMPILE-ERROR-VQR`: a dry-run failure is evidence, not a verdict: never auto-skip. If more than half of the VQRs fail, the translation is probably wrong; stop and report instead of excluding them.
- INTERACTIVE (STOP Gate): confirm when any VQR fails. AUTONOMOUS: continue with all VQRs, log the list, and flag the failures in the report.

**Step 6: Confirm prerequisites** (gate `EVAL-NO-PERMISSION` terminates when a required privilege is missing). Check the privileges listed in `eval-polling.md` with `SHOW GRANTS TO ROLE <role>` (direct-grant checks miss inherited and PUBLIC grants, such as the default `USE AI FUNCTIONS`). The session must run on a single primary role that holds all of them. Show remediation `GRANT` statements for gaps; do not run them without confirmation.

Summarise (view, source tables, VQR count, health, dry-run results) and, in INTERACTIVE mode, wait for confirmation.

### Phase 2: Configure

**Step 7: Choose VQR scope.** All VQRs (recommended baseline), a subset, or exclude some. Fix the list: you will reuse the same list for repeat runs and for any later comparison.

**Step 8: Write the config** exactly as in `eval-polling.md` (`analyst_params`, `verified_queries`, pinned `v3`), then create the stage with `CREATE STAGE IF NOT EXISTS` and `PUT` the file with `snow sql`. Use one uniquely named file per run.

### Phase 3: Execute

**Step 9: Run name.** `<SV_NAME>_eval_<YYYYMMDD_HHMMSS>_r<k>` where `<k>` is the repeat number. Names must be unique per view; use `EXECUTE_AI_EVALUATION('DELETE', ...)` to clear a collision.

**Step 10: Launch** with `EXECUTE_AI_EVALUATION('START', ...)`.

**Step 11: Poll** with `'STATUS'` every ~30 s, up to 15 minutes (details and failure states in `eval-polling.md`). On timeout report the status and stop; do not use partial rows as a result.

**Step 12: Repeat.** Run the same config at least a second time (new run name). Report each run and the spread between them; a pass/fail threshold is meaningful only once the normal range is known.

### Phase 4: Analyse

**Step 13: Read results and compute metrics** with the queries in `eval-polling.md`: mean `EVAL_AGG_SCORE`, counts at 1.0 / partial / 0.0, per-run and averaged over repeats.

**Step 14: Regression detection.** Compare a current run with a previous run only when both used the same `metric_version` and the same question list. Join on question text with a FULL OUTER JOIN so renamed, added or removed questions are reported as such rather than as unchanged:

```sql
WITH cur AS (
  SELECT INPUT AS question, EVAL_AGG_SCORE AS cur_score
  FROM TABLE(SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA('<DB>','<SCHEMA>','<SV_NAME>','SEMANTIC VIEW','<current_run>'))
  WHERE METRIC_NAME = 'sql_correctness'),
prev AS (
  SELECT INPUT AS question, EVAL_AGG_SCORE AS prev_score
  FROM TABLE(SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA('<DB>','<SCHEMA>','<SV_NAME>','SEMANTIC VIEW','<previous_run>'))
  WHERE METRIC_NAME = 'sql_correctness')
SELECT * FROM (
  SELECT COALESCE(c.question, p.question) AS question, p.prev_score, c.cur_score,
         CASE WHEN p.question IS NULL THEN 'NEW_QUESTION'
              WHEN c.question IS NULL THEN 'MISSING_NOW'
              WHEN p.prev_score = 1.0 AND c.cur_score < 1.0 THEN 'REGRESSION'
              WHEN p.prev_score < 1.0 AND c.cur_score = 1.0 THEN 'IMPROVEMENT'
              ELSE 'UNCHANGED' END AS change_type
  FROM cur c FULL OUTER JOIN prev p ON c.question = p.question)
WHERE change_type <> 'UNCHANGED';
```

If the evaluated view is a candidate, its results are stored under the candidate's name; query that name. Treat a single-run flip as noise unless it repeats.

**Step 15: Categorise failures** for each question with `sql_correctness < 1.0`: structural EXPLAIN diff first, then the categories and fixes in `references/failure-analysis.md`.

### Phase 5: Report and persist

**Step 16: Summary report.** Run name(s), metric version, accuracy and mean score per run and across repeats, perfect/partial/failed counts, regressions against the previous comparable run, failing questions with category, and ranked recommendations.

**Step 17: Next steps.** Offer: optimise (`sv-iterative-optimizer` for 1-3 specific failures, `sv-gepa-optimizer` for broad issues, below ~70%), fix failures on a candidate (`failure-analysis.md`), re-run with a different subset, export, or stop. Fixes always go to a candidate; promotion only through `SV-PROMOTE`.

**Step 18: Persist (optional).** If `_SV_TOOLKIT_META` exists (or the user wants it), confirm once with the user that you may create two metadata tables in that schema, then:

```sql
-- gate EVAL-METADATA-CREATE: additive, no prompt in any mode
CREATE TABLE IF NOT EXISTS <DB>._SV_TOOLKIT_META.EVAL_HISTORY (
    run_name VARCHAR, sv_fqn VARCHAR, source_sv_fqn VARCHAR,
    metric_name VARCHAR, metric_version VARCHAR,
    run_timestamp TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    total_vqrs INTEGER, mean_score FLOAT, perfect_count INTEGER, failed_count INTEGER,
    regressions INTEGER, repeat_index INTEGER, config_yaml VARCHAR);

CREATE TABLE IF NOT EXISTS <DB>._SV_TOOLKIT_META.EVAL_RESULTS (
    run_name VARCHAR, metric_version VARCHAR, question VARCHAR,
    generated_output VARCHAR, reference_output VARCHAR,
    sql_correctness FLOAT, failure_category VARCHAR, error_message VARCHAR,
    metric_status VARIANT, metric_calls ARRAY);

INSERT INTO <DB>._SV_TOOLKIT_META.EVAL_RESULTS
SELECT '<run_name>', '<metric_version>', INPUT, OUTPUT, GROUND_TRUTH,
       EVAL_AGG_SCORE, NULL, ERROR, METRIC_STATUS, METRIC_CALLS
FROM TABLE(SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA('<DB>','<SCHEMA>','<SV_NAME>','SEMANTIC VIEW','<run_name>'))
WHERE METRIC_NAME = 'sql_correctness';
```

`sv_fqn` is the evaluated view (a candidate name for candidate runs); `source_sv_fqn` is the production view it derives from. Primary keys are not enforced in Snowflake, so none are declared; deduplicate on `(run_name, question)` when reading. Insert the EVAL_HISTORY row with the aggregates from Step 13.

## Error handling

| Error | Cause | Recovery |
|---|---|---|
| Semantic view not found | Wrong FQN or no access | Verify name and grants |
| No verified queries (gate `EVAL-NO-VQR`) | SV has no VQRs | Terminate and route to `vqr-generator` |
| Run FAILED | Invalid SV DDL, config, or judge model unavailable | Check DDL compiles, config, pinned version |
| Run CANCELLED | System issue or manual cancel | Retry once |
| Permission denied on EXECUTE_AI_EVALUATION | Missing grants or secondary role | Table in `eval-polling.md` |
| Timeout (> 15 min) | Many VQRs or load | Use a subset, retry later |
| Near-zero mean score | VQR SQL not executable, CA-extension column drop, or wrong target | `vqr-eval-health.md` Patterns A-C |
| `invalid identifier` in ground-truth errors | CA extension drops columns | Check 3: candidate without the extension |
| Large score asymmetry between VQR styles | Pre-scoring failures, not model quality | Do not read it as accuracy; see `vqr-eval-health.md` |

## Routing

| Scenario | Route |
|---|---|
| No VQRs | `vqr-generator` |
| Broad accuracy problems | `sv-gepa-optimizer` |
| 1-3 specific failures | `sv-iterative-optimizer` |
| Missing relationships | `sv-discovery` |
| Monitor over time | Persist to EVAL_HISTORY and re-run on a schedule with the same question list and metric version |

## Notes

- Holdout: the evaluation copies the view without the selected VQRs, so selected questions cannot be looked up; unselected VQRs still guide generation.
- Cost: one Analyst generation plus one judge call per VQR per run; repeats multiply it.
- Only one evaluation per view at a time (observed; see `eval-polling.md`).
