---
name: sv-coverage-checker
description: >
  GT SQL vs Semantic View coverage checker. Diffs a workload manifest (from EXPLAIN
  plans on Ground Truth SQL) against the SV definition to produce a structural gap
  report and per-question ANSWERABLE / NOT_ANSWERABLE verdicts. Runs as a parallel
  thread alongside EXECUTE_AI_EVALUATION — same GT SQL input, non-blocking.
  Three failure modes: TABLE_NOT_REGISTERED, COLUMN_NOT_EXPOSED, RELATIONSHIP_MISSING.
triggers:
  - coverage check
  - SV coverage
  - GT SQL coverage
  - which GT questions are answerable
  - explain plan manifest
  - structural gap report
  - SV gap analysis
  - validate SV against eval set
  - answerable questions
  - check SV gaps
---

# sv-coverage-checker

Check whether your Semantic View can structurally answer all your Ground Truth SQL questions
before running an eval. Runs in parallel with `EXECUTE_AI_EVALUATION` — same input, no blocking.

## Prerequisites

1. A GT eval table with columns `(QUESTION_ID VARCHAR, SQL_TEXT VARCHAR)`.
   If your eval table stores SQL inside JSON (e.g. `EXPECTED_TOOLS` VARIANT), create an extraction view first:
   ```sql
   CREATE OR REPLACE VIEW <db>.<schema>.GT_SQL_VIEW AS
   SELECT
       ROW_NUMBER() OVER (ORDER BY INPUT_QUERY) AS QUESTION_ID,
       PARSE_JSON(EXPECTED_TOOLS):ground_truth_invocations[0]:tool_output:SQL::STRING AS SQL_TEXT
   FROM <db>.<schema>.<eval_table>;
   ```

2. The `SV_COVERAGE_CHECKER` procedure deployed to your schema.
   See `sv_coverage_checker_deploy.sql` for the one-time setup.

## Workflow

### Phase 1: Deploy (once per schema)

```bash
# Upload procedure to stage
snow sql -q "PUT file:///.../sv_coverage_checker.py @<DB>.<SCHEMA>.SV_TOOLKIT_STAGE/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE" -c <connection>

# Deploy procedure
snow sql -f sv_coverage_checker_deploy.sql -c <connection> --database <DB> --schema <SCHEMA>
```

### Phase 2: Run the checker

```sql
-- Run standalone (or kick off in a parallel worksheet alongside EXECUTE_AI_EVALUATION)
CALL <DB>.<SCHEMA>.SV_COVERAGE_CHECKER(
    '<DB>.<SCHEMA>.GT_SQL_VIEW',       -- extraction view or plain SQL table
    '<DB>.<SCHEMA>.<YOUR_SV_NAME>'     -- semantic view to check
);
```

### Phase 3: Interpret output

The result is a VARIANT with three keys:

**`gaps[]`** — structural holes in the SV (primary output):
```json
[
  {"gap_type": "TABLE_NOT_REGISTERED", "physical_table": "DB.S.DIM_DEVICE_TYPE", "element": null,
   "detail": "DB.S.DIM_DEVICE_TYPE used in GT SQL but not registered in SV TABLES block"},
  {"gap_type": "COLUMN_NOT_EXPOSED", "physical_table": "DB.S.FCT_TXN", "element": "DISCOUNT_AMT",
   "detail": "DB.S.FCT_TXN.DISCOUNT_AMT referenced in GT SQL but not exposed in SV"},
  {"gap_type": "RELATIONSHIP_MISSING", "physical_table": null, "element": "FCT.TXN_ID = DIM.TXN_ID",
   "detail": "JOIN condition in GT SQL has no corresponding RELATIONSHIPS entry in SV"}
]
```

**`verdicts[]`** — per-question ANSWERABLE / NOT_ANSWERABLE:
```json
[
  {"question_id": "1", "status": "ANSWERABLE",     "failure_mode": null, "gap_detail": null},
  {"question_id": "3", "status": "NOT_ANSWERABLE", "failure_mode": "TABLE_NOT_REGISTERED",
   "gap_detail": "DB.S.DIM_DEVICE_TYPE used in GT SQL but not registered in SV TABLES block"}
]
```

**`summary{}`**:
```json
{"total_questions": 20, "answerable": 14, "not_answerable": 6, "unique_gaps": 4}
```

### Phase 4: Fix and iterate

For each gap in `gaps[]`:
- `TABLE_NOT_REGISTERED` → add the table to the SV `TABLES` block
- `COLUMN_NOT_EXPOSED` → add the column as a `DIMENSION`, `FACT`, or `METRIC`
- `RELATIONSHIP_MISSING` → add a `RELATIONSHIPS` entry

Re-run the checker. Repeat until `summary.not_answerable = 0`.

## Notes

- **Parallel execution**: kick off this CALL in a separate Snowsight worksheet at the same
  time as `EXECUTE_AI_EVALUATION`. Both consume the same GT SQL input; neither blocks the other.
- **Computed columns**: the checker indexes physical column tokens from metric/fact/dimension
  expressions (e.g. `SUM(SALES_USD)` → tracks `SALES_USD`). This prevents false
  COLUMN_NOT_EXPOSED errors for metric-covered columns.
- **All join types**: LEFT OUTER, FULL OUTER, CROSS and other join variants are all detected,
  not just INNER JOINs.
- **2-hop joins**: correctly handled — each join pair is checked independently against
  the SV RELATIONSHIPS entries.
- **CTEs and subqueries**: `EXPLAIN USING TABULAR` flattens these; TableScan rows appear
  for all physical tables regardless of nesting depth.
- **Unaliased tables**: tables without an explicit alias in the SV TABLES block use the
  last segment of the FQN as their logical name (e.g. `DB.SCHEMA.ORDERS` → `ORDERS`).
