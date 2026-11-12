---
name: sv-ddl-phase6-execute-validate
description: Execute the DDL, validate with DESCRIBE SEMANTIC VIEW, and run a self-test question loop — iterate until passing
---

# Phase 6: Execute & Validate

## Purpose
Deploy the Phase 5 DDL to a **candidate copy**, confirm it was created correctly, and run a self-test question loop to verify Cortex Analyst can answer business questions from it. Phase 6 never writes to the target name; see `../../../references/candidate-promotion.md`.
This is the **iterative core** of the skill — failures loop back to Phase 5 for DDL fixes.

---

## Step 6.1: Deploy the DDL as a candidate

Each Phase 5 → 6 iteration uses a fresh run id, so a candidate name is never reused
(`<toolkit-root>` is the semantic-view-toolkit directory):

```bash
RUN=$(python3 <toolkit-root>/scripts/candidate.py new-run | jq -r .run)
CAND=$(python3 <toolkit-root>/scripts/candidate.py name --source <SV_FQN> --kind cand --run "$RUN" | jq -r .candidate)
python3 <toolkit-root>/scripts/candidate.py rewrite-ddl --source <SV_FQN> --candidate "$CAND" < phase5.sql > cand.sql
python3 <toolkit-root>/scripts/candidate.py register <manifest.json> --run "$RUN" --source <SV_FQN> --candidate "$CAND" --ddl-file cand.sql
python3 <toolkit-root>/scripts/candidate.py guard --source <SV_FQN> --target "$CAND"
```

Execute `cand.sql` (plain `CREATE SEMANTIC VIEW <CAND>`). If the candidate name already exists,
stop; do not replace it.

**Expected result**: `Semantic view <CAND> successfully created.`

Run every remaining Phase 6 step against `<CAND>`, not `<SV_FQN>`. When an iteration is
abandoned, mark its candidate `failed` with `candidate.py set-status`.

**If DDL fails**, go to Step 6.2 (error handling). Otherwise proceed to Step 6.3.

---

## Step 6.2: Error handling map

| Error message | Root cause | Fix (return to Phase 5) |
|--------------|-----------|------------------------|
| `No queryable expression` | No FACTS or DIMENSIONS defined | Add at least one FACTS clause |
| `invalid identifier '<X>'` | Fact/dim alias doesn't match physical column name | Change `AS <X>` to match exact physical column name from DESCRIBE TABLE |
| `Duplicate identifier '<X>'` | Column `<X>` defined in multiple tables' FACTS/DIMS | Keep it in one table, remove from others |
| `Object '<table>' does not exist or not authorized` | Physical table path wrong or no access | Run `SELECT * FROM <table> LIMIT 1` to verify; fix path |
| `Relationship '<r>' requires a primary key` | Right-hand REFERENCES table has no PK/UNIQUE | Add `PRIMARY KEY (<col>)` to that table in TABLES clause |
| `Ambiguous relationship` | Two paths between same table pair, no USING | Add `USING (<rel_name>)` to the affected metric |
| `PRIVATE not allowed` | PRIVATE on a dimension | Remove PRIVATE modifier |

After identifying the error:
1. Fix the DDL in Phase 5
2. Re-run the self-check (Step 5.8)
3. Return to Step 6.1

---

## Step 6.3: Structural validation with DESCRIBE

> ⚠️ **FQN required** — `DESCRIBE SEMANTIC VIEW` requires a fully-qualified three-part name.
> A bare name or two-part name will not match the object and produces a misleading error.
> Always use `<DATABASE>.<SCHEMA>.<SV_NAME>`.

```sql
DESCRIBE SEMANTIC VIEW <SV_DB>.<SV_SCHEMA>.<SV_NAME>;
```

Verify the output contains:
- ✅ All expected tables (rows with `object_kind = 'TABLE'`)
- ✅ All expected facts (rows with `object_kind = 'FACT'`)
- ✅ All expected dimensions (rows with `object_kind = 'DIMENSION'`)
- ✅ All expected metrics (rows with `object_kind = 'METRIC'`)
- ✅ All relationships (rows with `object_kind = 'RELATIONSHIP'`)

Report a summary:
```
DESCRIBE results:
  Tables:        N ✓
  Facts:         N ✓ / N expected
  Dimensions:    N ✓ / N expected
  Metrics:       N ✓ / N expected
  Relationships: N ✓
```

If any counts are lower than expected, find the missing element and fix.

> **Time dimensions in DDL:** There is no `TIME DIMENSIONS` clause, no `IS TIME` modifier,
> and no `ALTER ... SET IS_TIME_DIMENSION` in DDL authoring. `IS_TIME_DIMENSION` is a YAML-only
> concept. In DDL, time dimensions are declared as regular dimensions in the DIMENSIONS clause —
> Snowflake automatically infers time semantics from the DATE/TIMESTAMP data type. No post-CREATE
> ALTER step is needed.

---

## Step 6.3.1: Post-deploy structural validation

Run these SQL checks immediately after the DESCRIBE in Step 6.3.

> ⚠️ **Capture the DESCRIBE query ID first.** Each `RESULT_SCAN(LAST_QUERY_ID())` reads
> the most recent query result. If you run multiple checks in sequence, the second check
> reads the first check's result, not the DESCRIBE output. Always capture the DESCRIBE
> query ID once and reuse it:
>
> ```sql
> -- Run DESCRIBE and immediately capture its query ID:
> DESCRIBE SEMANTIC VIEW <SV_DB>.<SV_SCHEMA>.<SV_NAME>;
> SET describe_qid = LAST_QUERY_ID();
> ```
>
> Then use `$describe_qid` in all three trap checks below instead of `LAST_QUERY_ID()`.

> ⚠️ **Column-name pre-flight required** — the RESULT_SCAN queries below reference column names
> from the DESCRIBE output. These names vary by account version and must be verified before
> running the trap checks. Run:
> ```sql
> SELECT * FROM TABLE(RESULT_SCAN($describe_qid)) LIMIT 0;
> ```
> The DESCRIBE output typically uses these columns (confirm with the `LIMIT 0` query above):
> - `"object_kind"` — the type of object (TABLE, FACT, DIMENSION, METRIC, RELATIONSHIP)
> - `"object_name"` — name of the object
> - `"parent_entity"` — which logical table the object belongs to
> - `"property"` — property name (e.g. TABLE, REF_TABLE, FOREIGN_KEY, REF_KEY)
> - `"property_value"` — property value
>
> **Column names are lowercase** — you MUST use double-quoted lowercase identifiers
> (e.g. `"object_kind"`, not `object_kind` or `OBJECT_KIND`) when querying via RESULT_SCAN.
> Unquoted identifiers resolve to uppercase and produce "invalid identifier" errors.
>
> Relationships are stored as property rows with `object_kind = 'RELATIONSHIP'` and
> properties `TABLE` (left table) and `REF_TABLE` (right table). Adjust the queries
> below if your account uses different column names.

**Check 1: Reverse fanout risk** — topology is a warning, not measured inflation. Forward many-to-one REFERENCES chains preserve fact grain when declared keys are actually unique. Check reverse or sibling traversal with independently computed aggregates.

> ⚠️ **Star-topology fan trap** (not auto-detected): if two tables W and C are both children of a
> shared parent A (W→A and C→A), queries crossing W↔C via A are a theoretical fan trap. The check
> below only catches one-hop bridge paths (M→bridge→dim). Verify star topologies manually: "Can
> a metric in W be joined to a dimension in C through A? If so, does that inflate results?"

```sql
WITH sv_meta AS (SELECT * FROM TABLE(RESULT_SCAN($describe_qid))),
metric_tbl AS (
  SELECT DISTINCT "parent_entity" AS t FROM sv_meta WHERE "object_kind" = 'METRIC'
),
dim_tbl AS (
  SELECT DISTINCT "parent_entity" AS t FROM sv_meta WHERE "object_kind" = 'DIMENSION'
),
rels AS (
  SELECT "property_value" AS lt, NULL AS rt, "object_name" AS rel_name
  FROM sv_meta
  WHERE "object_kind" = 'RELATIONSHIP' AND "property" = 'TABLE'
),
rel_refs AS (
  SELECT "object_name" AS rel_name, "property_value" AS rt
  FROM sv_meta
  WHERE "object_kind" = 'RELATIONSHIP' AND "property" = 'REF_TABLE'
),
rel_pairs AS (
  SELECT r.lt, rr.rt FROM rels r JOIN rel_refs rr ON r.rel_name = rr.rel_name
)
SELECT 'FAN_TRAP' AS issue_type, m.t AS metric_table, d.t AS dim_table, r1.rt AS bridge_table,
       'Potential reverse fanout on ' || m.t || ' grouped by ' || d.t || ' through ' || r1.lt AS detail
FROM metric_tbl m JOIN rel_pairs r1 ON r1.rt = m.t JOIN rel_pairs r2 ON r2.rt = r1.lt
JOIN dim_tbl d ON d.t = r2.lt WHERE d.t != m.t;
```

**Check 2: Chasm trap** — two fact tables converging on shared dimension (double counting)
```sql
WITH sv_meta AS (SELECT * FROM TABLE(RESULT_SCAN($describe_qid))),
metric_tbl AS (
  SELECT DISTINCT "parent_entity" AS t FROM sv_meta WHERE "object_kind" = 'METRIC'
),
rels AS (
  SELECT "property_value" AS lt, NULL AS rt, "object_name" AS rel_name
  FROM sv_meta
  WHERE "object_kind" = 'RELATIONSHIP' AND "property" = 'TABLE'
),
rel_refs AS (
  SELECT "object_name" AS rel_name, "property_value" AS rt
  FROM sv_meta
  WHERE "object_kind" = 'RELATIONSHIP' AND "property" = 'REF_TABLE'
),
rel_pairs AS (
  SELECT r.lt, rr.rt FROM rels r JOIN rel_refs rr ON r.rel_name = rr.rel_name
)
SELECT 'CHASM_TRAP' AS issue_type, m1.t AS metric_1, m2.t AS metric_2, r1.rt AS shared_table,
       'Pre-aggregate both ' || m1.t || ' and ' || m2.t || ' to ' || r1.rt || ' grain separately' AS detail
FROM metric_tbl m1 JOIN rel_pairs r1 ON r1.lt = m1.t
JOIN metric_tbl m2 ON m2.t != m1.t AND m2.t > m1.t
JOIN rel_pairs r2 ON r2.lt = m2.t AND r2.rt = r1.rt;
```

**Check 3: Orphan tables** — tables with no RELATIONSHIP entry
```sql
WITH sv_meta AS (SELECT * FROM TABLE(RESULT_SCAN($describe_qid))),
all_tbl AS (
  SELECT DISTINCT "object_name" AS t FROM sv_meta WHERE "object_kind" = 'TABLE'
),
rel_tbl AS (
  SELECT "property_value" AS t FROM sv_meta
  WHERE "object_kind" = 'RELATIONSHIP' AND "property" = 'TABLE'
  UNION
  SELECT "property_value" FROM sv_meta
  WHERE "object_kind" = 'RELATIONSHIP' AND "property" = 'REF_TABLE'
)
SELECT 'ORPHAN' AS issue_type, t, 'Table has no RELATIONSHIP — queries using its columns will fail' AS detail
FROM all_tbl WHERE t NOT IN (SELECT t FROM rel_tbl);
```

| Result | Action |
|---|---|
| FAN_TRAP row returned | **STOP** (both modes — structural defect, not a judgment call) — return to Phase 4/5, move metric to bridge-table grain |
| CHASM_TRAP row returned | **STOP** (both modes) — return to Phase 4/5, aggregate each fact to shared dimension grain in separate CTEs |
| ORPHAN row returned | **WARN** — surface to user; add missing RELATIONSHIP or remove orphaned table |
| All return 0 rows | ✓ Proceed to Step 6.4 — but also verify star-topology paths manually (see fan-trap note above) |
| Any query errors with "invalid identifier" | Column names in the pre-flight didn't match; re-read Step 6.3.1 preamble and remap column names |

---

## Step 6.4: Self-test question loop

Test the semantic view by constructing and executing SQL against the source objects for 3-5 sample questions.

> **Note**: There is no `SNOWFLAKE.CORTEX.ANALYST()` SQL UDF — that function does not exist. Cortex Analyst is accessible via the REST API or the Snowflake UI. However, semantic views **are directly queryable via SQL** using two approaches:
>
> **Approach A — SEMANTIC_VIEW clause (explicit):**
> ```sql
> SELECT * FROM SEMANTIC_VIEW(
>   <sv_name>
>   DIMENSIONS <table_alias>.<dimension_name>
>   METRICS <table_alias>.<metric_name>
> ) ORDER BY <dimension_name>;
> ```
> ⚠️ **ORDER BY must use unqualified column names.** SEMANTIC_VIEW() output columns are always unqualified (`M_TOTAL_SPEND`, not `DELIVERIES.M_TOTAL_SPEND`). The METRICS input clause accepts `entity.metric_name` (both forms work), but the resulting output column strips the entity prefix. `ORDER BY entity.metric_name` will fail with `invalid identifier` — use `ORDER BY metric_name` instead.
>
> **Approach B — Direct FROM (implicit rewrite):**
> ```sql
> SELECT <dimension>, AGG(<metric>)
> FROM <sv_name>
> GROUP BY <dimension>
> ORDER BY <dimension>;
> ```
>
> Self-tests in this phase validate the SV's logic by running SQL directly against the underlying source objects (tables, views, or dynamic tables), using the SV's relationships, facts, and dimensions as the query blueprint. This confirms the physical layer is correct before relying on the semantic query engine.

Generate test questions from `BUSINESS_CONTEXT` and `COLUMN_CLASSES`:
- One aggregate question (SUM or COUNT a METRIC)
- One filter question (filter on a DIMENSION value)
- One time-series question (GROUP BY a TIME_DIMENSION)
- One join question (metric from one table, filter from another)
- One from `PROPOSED_METRICS` if available

For each question, write and execute SQL against the source objects (tables, views, or dynamic tables):

```sql
-- Aggregate test:
SELECT SUM(<fact_col>) AS metric_value
FROM <source_object>;

-- Filter test:
SELECT <dim_col>, COUNT(*) AS count
FROM <source_object>
WHERE <dim_col> = '<filter_value>'
GROUP BY <dim_col>;

-- Join test (validates the SV relationship is correct):
SELECT t1.<dim_col>, SUM(t2.<fact_col>) AS total
FROM <source_object_1> t1
JOIN <source_object_2> t2 ON t1.<pk_col> = t2.<fk_col>
GROUP BY t1.<dim_col>
ORDER BY total DESC
LIMIT 10;
```

For each question, capture:
- The SQL you constructed
- Whether it executed without error
- Whether the result is semantically correct for the question

---

## Step 6.4.1: Direct semantic view query validation (mandatory)

For mixed detail/rollup sources, identify row-level markers and documented grains before selecting a filter; never guess that NULL means total. Compute independent base-detail SUM, COUNT, and AVG (SUM/count of non-null values, not average of group averages), then compare SV results at identical filters, null policy, date boundaries, units and snapshot. Repeat grouped and ungrouped tests; inspect referenced-key uniqueness and each join's row multiplicity. Do not use generated Analyst SQL as the reference answer.

Persist expected/observed JSON objects with `scope`, `sum`, `count`, `avg` plus source queries and snapshot evidence. Run `python3 <toolkit-root>/scripts/sv_validator.py <ddl.sql> <aggregate-evidence.json>`; the existing validator calls `validate_aggregate_evidence`. Missing evidence, scope differences, or numeric mismatches block acceptance. Exact comparison requires normalized numeric values; record any approved rounding before comparison. Topology warnings alone neither prove nor disprove inflation.

**Mandatory semantic validation** — before marking Phase 6 complete, run at least one query
through the semantic view for each entity that has metrics defined:

```sql
-- Verify each metric entity is queryable
SELECT <metric_name>
FROM <SV_DATABASE>.<SV_SCHEMA>.<SV_NAME>
LIMIT 5;
```

Physical SQL passing (source table queries) does not guarantee the semantic view is correctly
configured. Granularity constraints, relationship accessibility, and AGG() behavior can only
be validated by querying through the semantic view layer. This step is not optional.

After confirming the physical-layer SQL works, validate the SV's semantic query interface directly:

```sql
SELECT * FROM SEMANTIC_VIEW(
  <SV_DB>.<SV_SCHEMA>.<SV_NAME>
  DIMENSIONS <first_dim_table_alias>.<first_dim_name>
  METRICS <first_metric_table_alias>.<first_metric_name>
) LIMIT 10;
```

If this returns results, the SV's semantic engine is functioning correctly. If it errors, check:
- Relationship definitions (missing or incorrect PKs)
- Dimension/metric granularity mismatches (dimension entity must have equal or lower granularity than metric entity)
- Use `SHOW SEMANTIC DIMENSIONS FOR METRIC <sv_name>.<metric_name>` to see which dimensions are valid for each metric

---

## Step 6.5: Self-evaluate test results

For each test question, score:

| Result | Score | Action |
|--------|-------|--------|
| Valid SQL returned, uses expected tables/columns | PASS ✓ | Continue |
| Valid SQL but uses unexpected join path or wrong column | WARN ⚠️ | Note for Phase 7 iteration |
| "I cannot answer" or empty response | FAIL ✗ | Identify root cause |
| SQL error when executed | FAIL ✗ | Fix DDL or add description clarity |

**Common FAIL root causes**:

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Metric not found | Column classified wrong (FACT should be METRIC) | Move from FACTS to METRICS as aggregate expression |
| Wrong table joined | Relationship missing | Add relationship in Phase 4, regenerate DDL |
| Filter not working | DIMENSION missing or misnamed | Check DIMENSION alias matches user's expected filter language |
| Date truncation wrong | No AI_SQL_GENERATION instruction for date handling | Add date format instruction to AI_SQL_GENERATION |
| Wrong aggregation | Ambiguous metric direction | Add description to METRIC with explicit aggregation note |

---

## Step 6.6: Present validation results

```
Validation Results for <SV_NAME>

  DDL execution:    ✓ Success
  DESCRIBE check:   ✓ 4 tables, 18 facts, 22 dimensions, 6 metrics, 3 relationships

  Self-test questions:
    ✓ "What is total inventory value by dealer?"   → SUM(LIST_PRICE) GROUP BY DEALER_NAME
    ✓ "How many vehicles are active?"              → COUNT(*) WHERE LISTING_STATUS = 'ACTIVE'
    ✓ "Show vehicles by month of acquisition"     → GROUP BY DATE_TRUNC('month', ACQUISITION_DATE)
    ✗ "Which dealers have the most aged inventory?" → failed: DAYS_IN_INVENTORY not found
    ⚠️ "Average list price by market segment"     → joined on wrong table

  Issues found: 2
  Recommendation: Fix DAYS_IN_INVENTORY classification + add market segment relationship
```

---

## Step 6.7: Decide — iterate or proceed

If **0 failures**: mark the candidate `evaluated` and proceed to Phase 7 (enrichment / verified queries). The target SV is created (new SV) or promoted (existing SV) at the end of Phase 7.

If **any failures**: return to Phase 5 with the specific fixes identified. Increment iteration counter.

**Iteration limit**: after 3 rounds without progress, stop and present the issues to the user for manual input.

⚠️ **STOPPING POINT (INTERACTIVE mode)** — Present validation results. Ask:
```
Validation complete.
  Passed: N/N questions
  Issues: N

Options:
  1. Fix and iterate → return to Phase 5
  2. Accept as-is → proceed to Phase 7 (add verified queries, export)
  3. Show me the failing SQL so I can debug it manually
```

**AUTONOMOUS:** if 0 issues, proceed to Phase 7. If issues > 0, take option 1 (fix and
iterate) up to the existing 3-round iteration limit above; if still failing after 3
rounds, that limit already converts this into a genuine stop — present the issues
(matches the existing "stop and present to user for manual input" behavior).
