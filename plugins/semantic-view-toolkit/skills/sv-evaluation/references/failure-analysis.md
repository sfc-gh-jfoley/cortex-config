# Failure Analysis Guide

Diagnose why VQRs scored below 1.0 in a Cortex Analyst evaluation and choose a fix. Analyse only
rows from runs that used one pinned metric version and a completed run.

**All fixes go to a candidate copy, never production.** Create it with `candidate.py` (kind `cand`),
edit the full `GET_DDL` text of the candidate, deploy it with plain `CREATE SEMANTIC VIEW`, re-evaluate
(>= 2 runs, see `../../../references/eval-polling.md`), and promote only through gate `SV-PROMOTE`
(`../../../references/candidate-promotion.md`). The clause fragments below show what to change inside
that candidate DDL.

## Categories

| # | Category | Diagnosis | Fix (mutation operator) |
|---|---|---|---|
| 1 | WRONG_TABLE | Missing/wrong relationship | `change_relationship` |
| 2 | Wrong column | Vague descriptions, missing synonyms | `improve_description`, `add_synonym` |
| 3 | Wrong aggregation | Missing metric or wrong expression | `add_metric`, `refine_metric_expr` |
| 4 | Wrong time handling | No clear business date dimension / wrong granularity | `add_time_dimension` |
| 5 | SQL error | Bad expression or alias in the SV | Manual DDL fix |
| 6 | Empty result | Over-restrictive filter, case mismatch, wrong keys | `change_relationship`, `add_filter` |
| 7 | Analyst refuses | Out of scope or no example | `add_vqr` |
| 8 | Reference contaminated | Model applies the metric filter; reference SQL does not | Read-only: exclude or flag, do not modify the VQR |
| - | FAN_TRAP | Additive aggregate above a many-to-one join; reference pre-aggregates | Move metric to the right grain |
| - | CHASM_TRAP | Two fact tables joined on a shared dimension without per-fact CTEs | Pre-aggregate each fact to the shared grain |
| - | JOIN_HALLUCINATION | Joins on fewer/different columns than reference | `change_relationship` |
| - | GRANULARITY_MISMATCH | GROUP BY coarser or finer than reference | Add dimension at the right grain, or add a guiding VQR |

`add_filter` and `add_time_dimension` are YAML-model operator names. In DDL a filter is a boolean
dimension or an `AI_SQL_GENERATION` instruction, and a time dimension is a normal date/timestamp
dimension with a clear comment and synonyms; there is no separate DDL clause for either.

## Automated structural analysis

Run this first. Pull the failures:

```sql
SELECT INPUT AS question, OUTPUT AS generated_sql, GROUND_TRUTH AS reference_sql,
       EVAL_AGG_SCORE AS sql_correctness, ERROR AS error_message
FROM TABLE(SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA(
       '<DB>', '<SCHEMA>', '<SV_NAME>', 'SEMANTIC VIEW', '<run_name>'))
WHERE METRIC_NAME = 'sql_correctness' AND (EVAL_AGG_SCORE < 1.0 OR ERROR IS NOT NULL);
```

For each pair run `EXPLAIN USING TABULAR` on the generated and the reference SQL (the reference SQL may
use logical names; see the VQR dry-run in `../SKILL.md` before explaining it), then classify:

| EXPLAIN signal | Category |
|---|---|
| Different `objects` in TableScan rows | WRONG_TABLE |
| Join predicates differ | JOIN_HALLUCINATION |
| SUM/COUNT above a Join that the reference does not have | FAN_TRAP |
| Two Aggregate→TableScan paths converge at a Join; reference uses CTEs | CHASM_TRAP |
| Same tables/joins, different GROUP BY columns | GRANULARITY_MISMATCH |
| Identical plans, different results | data/filter error or reference contamination |
| EXPLAIN fails on the generated SQL | SQL error |

Fall back to manual comparison only when EXPLAIN fails.

## 1. Wrong table / join

Signals: different FROM/JOIN tables, extra or missing joins, wrong join columns, row counts off by 10x.
Causes: missing relationship, ambiguous join path, wrong keys, wrong join type.
Investigate with `DESCRIBE SEMANTIC VIEW <candidate>` (RELATIONSHIP rows).
Fix fragment:

```sql
orders (customer_id) REFERENCES customers
```

## 2. Wrong column

Signals: right tables, similar column chosen (`created_date` vs `order_date`).
Causes: empty/similar descriptions, user phrasing not in synonyms, many similar columns.
Fix fragments:

```sql
orders.created_date AS created_date WITH SYNONYMS = ('record creation timestamp') COMMENT = 'Internal record creation time. Not the business order date; use ORDER_DATE.'
orders.order_placed_at AS order_placed_at WITH SYNONYMS = ('order date', 'purchase date') COMMENT = 'Business date the customer placed the order.'
```

If many columns confuse selection, remove the unneeded ones from the candidate.

## 3. Wrong aggregation

Signals: right columns, wrong function (`SUM/COUNT(*)` vs `AVG`, missing `DISTINCT`).
Causes: no pre-defined metric, wrong expression, NULL/fan-out not handled.
Fix fragments:

```sql
orders.average_order_value AS AVG(orders.amount) COMMENT = 'Average order value'
orders.total_unique_customers AS COUNT(DISTINCT orders.customer_id) COMMENT = 'Unique customers who ordered'
```

## 4. Wrong time handling

Signals: no date filter, wrong date column, wrong `DATE_TRUNC` granularity.
Causes: several date columns, the technical one chosen over the business one.
Fix: give the business date a clear comment and synonyms (fragment as in category 2); with several tables, do this for the primary date of each.

## 5. SQL error

Signals: `error_message` set (`invalid identifier ...`), score 0.0.
Causes: typo in a metric/filter expression, type mismatch (for example aggregating a VARCHAR that holds numbers: use `TRY_CAST(col AS NUMBER)`), alias conflict.
Fix: edit the failing expression in the candidate DDL.

## 6. Empty result

Signals: SQL runs but returns 0 rows while the reference returns rows.
Causes: case mismatch in filter values, over-filtering, relationship with no matching keys.
Check actual values (`SELECT DISTINCT region FROM ... LIMIT 20`) and join counts. Fix with corrected relationship keys, or a boolean dimension / AI_SQL_GENERATION guidance that encodes the correct filter values.

## 7. Analyst refuses

Signals: empty `generated_sql`, error such as "cannot answer".
First decide whether the SV holds the data. If not, the question is out of scope (not a defect). If yes, add a verified query as an example: append to `AI_VERIFIED_QUERIES` in the candidate DDL (see `vqr-generator`). `ALTER SEMANTIC VIEW ... ADD VERIFIED QUERY` is not available; verify before relying on any in-place alternative.

## 8. Reference-contaminated baseline

Signals: the model's SQL applies a filter the SV's metric definition requires; the reference SQL omits it; results differ slightly; score < 1.0 although the model SQL matches the metric.
Confirm by running both forms for one bounded period and comparing the totals.
Handling is read-only: do not mutate the VQR or the SV in response. Exclude or flag the VQR, and compute a clean score on the remaining questions.

## Decision order

1. `error_message` set: refuses or empty SQL → 7; compile error → 5.
2. Zero rows → 6.
3. Wrong tables → 1; wrong columns → 2; wrong aggregate/GROUP BY → 3; date issues → 4.
4. Metric filter in generated SQL but not in the reference → 8.

## Severity

| Severity | Categories | Action |
|---|---|---|
| CRITICAL | 5 | Fix first; the SV is broken |
| HIGH | 1, FAN_TRAP, CHASM_TRAP, 7 on answerable questions | Before the rest |
| MEDIUM | 3, 4, GRANULARITY_MISMATCH | After HIGH |
| LOW | 2, 6 | Last, or via GEPA |
| INFO | 8 | Exclude/flag, no mutation |

## Batch view

Group failures by category; if one category exceeds 50% of failures, treat it as a systemic design
issue and fix it first. Classify with EXPLAIN as above, then count by category in your own query over the
failures set; categories need human or structural judgement, not a SQL `CASE` on the error text alone.
