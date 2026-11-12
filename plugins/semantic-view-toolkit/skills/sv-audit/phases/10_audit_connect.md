---
name: sv-audit-phase10-audit-connect
description: Connect to an existing semantic view, describe its structure, and establish the audit scope
---

# Phase 10: Audit Connect & Describe

## Purpose
Connect to an existing semantic view, parse its full definition, measure column coverage against underlying tables, and confirm the user wants to proceed with a usage-based audit.

This phase has **one mandatory stopping point** — user must confirm audit scope before proceeding.

---

## Step 10.1: Get the semantic view FQN

Ask the user:

```
Which semantic view do you want to audit?
Provide the fully qualified name: DB.SCHEMA.SV_NAME
```

Store as `SV_FQN` (e.g., `ANALYTICS_DB.PUBLIC.SALES_SV`).

Parse into components:
- `SV_DB` — database
- `SV_SCHEMA` — schema
- `SV_NAME` — semantic view name

---

## Step 10.2: Confirm access and describe

Run DESCRIBE to verify access and extract the full definition:

```sql
DESCRIBE SEMANTIC VIEW <SV_FQN>;
SET describe_qid = LAST_QUERY_ID();
```

If this fails with an access error, **stop and report**:
```
Cannot access <SV_FQN>.
Check that your role has USAGE on the database/schema and SELECT on the semantic view.
```

---

## Step 10.3: Parse DESCRIBE output

Extract the following from the DESCRIBE result:

**Tables in the SV:**
- Table names (with their database.schema.table references)
- Store as `SV_TABLES` — list of FQNs

**Columns defined:**
- All columns with their classification (FACT, DIMENSION, METRIC, DERIVED_METRIC)
- Column data types
- Which table each column belongs to
- Store as `SV_COLUMNS` — dict keyed by `table.column`

**Relationships defined:**
- FROM table/column → TO table/column
- Relationship type (if specified)
- Store as `SV_RELATIONSHIPS` — list of relationship definitions

**Verified queries:**
DESCRIBE returns one row per property per VQR (`object_kind = 'AI_VERIFIED_QUERY'`). Extract:
- `object_name` — VQR name
- `property = 'QUESTION'` → `property_value` — the natural language question
- `property = 'SQL'` → `property_value` — the SQL query body

Store as `SV_VQRS` — list of `{name, question, sql}` dicts (empty list if none defined).

> Note: All RESULT_SCAN column references use **double-quoted lowercase** identifiers (e.g. `"object_kind"`, `"parent_entity"`, `"property_value"`) because SHOW/DESCRIBE command output columns are lowercase. Unquoted uppercase identifiers will fail to match.

---

## Step 10.4a: VQR Health Check

If `SV_VQRS` is non-empty, validate each VQR's SQL against the SV schema. This is a static check — no ACCOUNT_USAGE queries required.

**Canonical check set:** [../../../references/vqr-eval-health.md](../../../references/vqr-eval-health.md) defines the pre-flight checks (Checks 1–8, with severities, detection code and fix guidance). The audit runs the reference checks listed below, plus one audit-only check (duplicate keys). Headings give the reference check number; use the reference for detection code. Run all eight before launching an eval after this audit.

**Ref Check 1 — Table reference format (HIGH for physical FQN, LOW for bare logical names)**
Physical `DB.SCHEMA.TABLE` references are HIGH. Bare logical names (`FROM orders`) are LOW style
findings: the DDL docs example uses them, the YAML docs prefer `__orders`.

**Ref Check 2 — Columns not in SV (HIGH)**
Every column reference must be a logical dimension, fact or metric name from DESCRIBE.
Skip CTE-defined aliases, SQL keywords and numeric literals.

**Ref Check 3 — CA extension column-drop (CRITICAL, Snowsight-built SVs only)**
Detect with `GET_DDL` and `'with extension' in ddl.lower()`. Before any eval, build a DDL-only
candidate copy as described in the reference.

**Ref Check 4 — GROUP BY alias (MEDIUM)**

**Ref Check 5 — Metric coverage gaps (MEDIUM)**
Route uncovered metrics to `vqr-generator`.

**Ref Check 7 — Aggregation mismatch (HIGH)**

**Ref Check 8 — Nested subqueries (MEDIUM, unverified heuristic; CTEs exempt)**

**Audit-only — Duplicate VQR keys (LOW)**
VQR entries with identical names, including names that differ only by trailing whitespace.

Store findings as `VQR_HEALTH_FINDINGS`:
```
{
  "total_vqrs": <N>,
  "fqn_bypass":        [{"vqr_name": "...", "tables": ["DB.SCHEMA.T1", ...]}],
  "bare_no_prefix":    [{"vqr_name": "...", "tables": ["T1", ...]}],
  "unknown_cols":      [{"vqr_name": "...", "columns": ["COL1", ...]}],
  "ca_extension_drop": [{"present": true}],
  "group_by_alias":    [{"vqr_name": "...", "aliases": ["..."]}],
  "uncovered_metrics": [{"metric": "...", "table": "..."}],
  "agg_mismatch":      [{"vqr_name": "...", "metric": "...", "vqr_agg": "...", "metric_agg": "..."}],
  "nested_subquery":   [{"vqr_name": "..."}],
  "duplicate_keys":    [{"vqr_name": "...", "count": N}]
}
```

Add to the scope summary line in Step 10.5:
```
  VQR Health:       <N> VQRs checked — <X> issues found (<Y> HIGH, <Z> MEDIUM, <W> CRITICAL)
```

---

## Step 10.4b: Topology Check

> **DESCRIBE output structure** (per Snowflake docs): `DESCRIBE SEMANTIC VIEW` returns an EAV-format result with these exact columns (always use double-quoted lowercase in RESULT_SCAN):
> - `"object_kind"` — `TABLE`, `RELATIONSHIP`, `DIMENSION`, `FACT`, `METRIC`, `DERIVED_METRIC`, `CUSTOM_INSTRUCTIONS`, `AI_VERIFIED_QUERY`, `CONSTRAINT` (range joins), or `NULL`
> - `"object_name"` — name of the entity
> - `"parent_entity"` — parent table for dims/facts/metrics and relationships; NULL for tables, VQRs, custom instructions
> - `"property"` — property key (e.g. `TABLE`, `REF_TABLE`, `EXPRESSION`, `DATA_TYPE`, `SYNONYMS`)
> - `"property_value"` — property value
>
> For **relationships**: there is no `left_table` or `right_table` column. Each relationship has multiple rows — use `"property" = 'TABLE'` for the left/source table and `"property" = 'REF_TABLE'` for the right/referenced table.
>
> ⚠️ **Column-name pre-flight**: Run `SELECT * FROM TABLE(RESULT_SCAN($describe_qid)) LIMIT 0;` immediately after DESCRIBE to confirm the actual column names returned by your account version before running the queries below.

Using the DESCRIBE result from Step 10.2 (re-run DESCRIBE and refresh `describe_qid` if needed):

> **No fan/chasm trap checks.** A shared dimension between fact tables is the normal star
> schema, not a defect. Semantic SQL rejects a dimension whose logical table is not related to the
> metric's table or has a coarser grain, with `Invalid dimension specified: … must be related to
> and have an equal or lower level of granularity` (docs: *Querying semantic views*,
> `SHOW SEMANTIC DIMENSIONS FOR METRIC`). Do not report fan or chasm traps from DESCRIBE alone.

**Check 1 — Orphan tables** (table in SV with no RELATIONSHIP entry, MEDIUM → its dimensions cannot be combined with metrics from other tables; single-table queries still work)
```sql
WITH sv_meta AS (SELECT * FROM TABLE(RESULT_SCAN($describe_qid))),
all_tbl AS (
  SELECT DISTINCT "object_name" AS t
  FROM sv_meta WHERE "object_kind" = 'TABLE'
),
rel_tbl AS (
  SELECT "property_value" AS t FROM sv_meta
  WHERE "object_kind" = 'RELATIONSHIP' AND "property" IN ('TABLE', 'REF_TABLE')
)
SELECT 'ORPHAN' AS issue_type, t,
  'Table has no RELATIONSHIP — its fields cannot be combined with other tables' AS detail
FROM all_tbl WHERE t NOT IN (SELECT t FROM rel_tbl);
```
> Single-table SVs are exempt — a lone table needs no relationship.

**Check 2 — USING completeness** (tables with multiple relationship paths to same target → ambiguous routing for metrics)

From the RESULT_SCAN rows: for each pair of tables, count how many distinct relationship names connect them. If any pair has 2+ relationships, verify that metrics on the source table include USING. `DESCRIBE SEMANTIC VIEW` does not expose the USING clause directly — flag as: "Multi-path table pairs detected — verify metrics on `<table>` include `USING (<rel_name>)` by inspecting the DDL: `SELECT GET_DDL('SEMANTIC VIEW', '<SV_FQN>')`."

Store findings as `TOPOLOGY_FINDINGS`:
```
{
  "orphans":     ["TABLE_NAME", ...],
  "missing_using": [{"table": "...", "relationship_paths": N}]
}
```

Add to scope summary line in Step 10.5:
```
  Topology:         <orphans> orphans, <missing_using> multi-path pairs
```

---

## Step 10.4c: Metric Integrity Check

> **What DESCRIBE exposes for FACTs, DIMENSIONs, and METRICs** (per Snowflake docs): For each object, DESCRIBE returns rows with `property` = `TABLE`, `EXPRESSION`, `DATA_TYPE`, and `ACCESS_MODIFIER`. The full SQL expression IS available from DESCRIBE — use it directly for Checks 1 and 2 below.

**Check 1 — Semi-additive metrics (NON ADDITIVE BY)**
From the DESCRIBE RESULT_SCAN, extract all METRIC rows and their EXPRESSION values:
```sql
SELECT "object_name" AS metric_name, "parent_entity" AS table_name, "property_value" AS expression
FROM TABLE(RESULT_SCAN($describe_qid))
WHERE "object_kind" = 'METRIC' AND "property" = 'EXPRESSION';
```
For each metric whose expression starts with `SUM(` or `COUNT(`, also retrieve the parent table's COMMENT. If any of these keywords appear in the metric name, expression, or table COMMENT: `snapshot`, `balance`, `headcount`, `inventory`, `pipeline`, `open`, `active`, `subscriber` — flag as a potential semi-additive metric missing `NON ADDITIVE BY`. Confirm with the SV owner whether the underlying data is a snapshot or a flow.

**Check 2 — LABELS=(FILTER) on non-boolean expressions**
From DESCRIBE, extract all FACT rows with their EXPRESSION and DATA_TYPE:
```sql
SELECT "object_name", "parent_entity", "property", "property_value"
FROM TABLE(RESULT_SCAN($describe_qid))
WHERE "object_kind" = 'FACT' AND "property" IN ('EXPRESSION', 'DATA_TYPE');
```
DESCRIBE does not expose the LABELS=(FILTER) flag directly. Infer filter facts by DATA_TYPE: facts with `DATA_TYPE = 'BOOLEAN'` are likely FILTER-labeled. Verify the expression looks like a boolean predicate (comparison, IN list, IS NULL). For definitive confirmation of which facts carry `LABELS=(FILTER)`, inspect the full DDL:
```sql
SELECT GET_DDL('SEMANTIC VIEW', '<DB>.<SCHEMA>.<SV_NAME>');
```

**Check 3 — PK cardinality (the cardinality lie)**
From DESCRIBE, extract PRIMARY_KEY and FOREIGN_KEY values to find PK columns that also appear as FK columns. Use the pivot pattern to extract the source table from the relationship's `TABLE` property:
```sql
WITH sv_meta AS (SELECT * FROM TABLE(RESULT_SCAN($describe_qid))),
pks AS (
  SELECT "object_name" AS table_name, "property_value" AS pk_col
  FROM sv_meta WHERE "object_kind" = 'TABLE' AND "property" = 'PRIMARY_KEY'
),
fks AS (
  SELECT
    MAX(CASE WHEN "property" = 'TABLE'       THEN "property_value" END) AS source_table,
    MAX(CASE WHEN "property" = 'FOREIGN_KEY' THEN "property_value" END) AS fk_col
  FROM sv_meta
  WHERE "object_kind" = 'RELATIONSHIP'
  GROUP BY "object_name"
  HAVING MAX(CASE WHEN "property" = 'FOREIGN_KEY' THEN "property_value" END) IS NOT NULL
)
SELECT p.table_name, p.pk_col, f.source_table AS also_fk_in
FROM pks p JOIN fks f ON CONTAINS(f.fk_col, TRIM(REPLACE(REPLACE(p.pk_col, '[', ''), ']', ''), '"'))
WHERE f.source_table != p.table_name;
```
> Note: PRIMARY_KEY and FOREIGN_KEY values are JSON arrays (e.g. `["C_CUSTKEY"]`). The CONTAINS check handles single-column keys. For composite keys, inspect manually.
>
> ⚠️ This overlap check compares key column name substrings across different tables, which can
> produce false positives. It also excludes same-table overlaps that may be intentional.
> Verify each flagged overlap manually before acting on it.

Any match means the declared PK column is used as a FK in another table — it may not be unique in the parent table. Present actionable verification SQL:
```sql
SELECT COUNT(*) AS total_rows, COUNT(DISTINCT <pk_col>) AS distinct_pk
FROM <DB>.<SCHEMA>.<TABLE>;
-- If total_rows != distinct_pk, the PK declaration is wrong.
```

Store findings as `METRIC_INTEGRITY_FINDINGS`:
```
{
  "semi_additive_candidates": [{"metric": "...", "table": "...", "keyword_matched": "..."}],
  "non_boolean_filter_facts": [{"fact": "...", "table": "...", "expr": "..."}],
  "pk_cardinality_suspects":  [{"table": "...", "pk_col": "...", "also_fk_in": "..."}]
}
```

Add to scope summary line in Step 10.5:
```
  Metric integrity: <N> issues found
```

---

## Step 10.4d: Metadata Quality Check

**Check 1 — AI_SQL_GENERATION presence**
Verify the SV has SQL generation instructions defined. Per Snowflake docs, DESCRIBE returns `object_kind = 'CUSTOM_INSTRUCTIONS'` rows for these. Query:
```sql
SELECT "property", "property_value"
FROM TABLE(RESULT_SCAN($describe_qid))
WHERE "object_kind" = 'CUSTOM_INSTRUCTIONS';
```
The `property` column will contain `AI_SQL_GENERATION` and/or `AI_QUESTION_CATEGORIZATION`. If no `CUSTOM_INSTRUCTIONS` rows exist, or none have `property = 'AI_SQL_GENERATION'` with a non-empty `property_value`, flag as HIGH — missing `AI_SQL_GENERATION`.

> **YAML models**: Legacy stage-based YAML files use `custom_instructions: <string>` (legacy) or `module_custom_instructions.sql_generation: <string>` (modern). Both map to the same `AI_SQL_GENERATION` instruction when loaded. Check both fields if the SV was created from a YAML file.

**Check 2 — COMMENT coverage**
From DESCRIBE, count tables and columns missing COMMENT. COMMENTs appear as rows with `property = 'COMMENT'`. A missing COMMENT means no row exists for that `object_kind`/`object_name` pair with `property = 'COMMENT'`.

```sql
-- Count objects missing COMMENT by kind
WITH sv_meta AS (SELECT * FROM TABLE(RESULT_SCAN($describe_qid))),
has_comment AS (
  SELECT "object_kind", "object_name", "parent_entity"
  FROM sv_meta WHERE "property" = 'COMMENT' AND "property_value" IS NOT NULL
),
all_objects AS (
  SELECT DISTINCT "object_kind", "object_name", "parent_entity"
  FROM sv_meta WHERE "object_kind" IN ('TABLE','FACT','DIMENSION','METRIC')
)
SELECT a."object_kind", a."parent_entity", COUNT(*) AS missing_comment_count
FROM all_objects a
LEFT JOIN has_comment h
  ON a."object_kind" = h."object_kind"
 AND a."object_name" = h."object_name"
 AND COALESCE(a."parent_entity", '') = COALESCE(h."parent_entity", '')
WHERE h."object_name" IS NULL
GROUP BY a."object_kind", a."parent_entity";
```

| Threshold | Severity |
|---|---|
| > 25% of tables missing COMMENT | HIGH |
| 10–25% of tables missing COMMENT | MEDIUM |
| > 30% of columns (facts/dims/metrics) missing COMMENT | MEDIUM |

**Check 3 — SAMPLE_VALUES and IS_ENUM coverage** *(synonym coverage is not scored by this audit)*
`SAMPLE_VALUES` and `IS_ENUM` are **not exposed in DESCRIBE output** (per Snowflake docs — only `TABLE`, `EXPRESSION`, `DATA_TYPE`, `ACCESS_MODIFIER`, `SYNONYMS`, `COMMENT`, and Cortex Search properties are listed). To check these, retrieve the full DDL:
```sql
SELECT GET_DDL('SEMANTIC VIEW', '<DB>.<SCHEMA>.<SV_NAME>');
-- Or for YAML-based SVs:
SELECT SYSTEM$READ_YAML_FROM_SEMANTIC_VIEW('<DB>.<SCHEMA>.<SV_NAME>');
```
From the DDL or YAML, flag any VARCHAR/TEXT dimension that has no `SAMPLE_VALUES` and no `IS_ENUM` as MEDIUM — missing sample values force the model to guess valid filter values.

**Check 4 — Source object accessibility**
Verify the current role can still SELECT from each underlying source table. Base table names come from DESCRIBE rows where `object_kind = 'TABLE'` and `property = 'BASE_TABLE_NAME'` (with `BASE_TABLE_DATABASE_NAME` and `BASE_TABLE_SCHEMA_NAME` for the full FQN). A logical table defined as a SQL query has a `DEFINITION` property instead; run `SELECT * FROM (<DEFINITION>) LIMIT 0` for it:
```sql
SELECT * FROM <BASE_TABLE_DATABASE_NAME>.<BASE_TABLE_SCHEMA_NAME>.<BASE_TABLE_NAME> LIMIT 0;
```
Run once per source table. A failure means the SV will error at query time even though DESCRIBE succeeds. Flag any inaccessible tables as CRITICAL.

Store findings as `METADATA_QUALITY_FINDINGS`:
```
{
  "ai_sql_generation_missing": true | false,
  "tables_missing_comment": ["TABLE_NAME", ...],
  "columns_missing_comment_count": N,
  "dims_missing_sample_values": [{"table": "...", "dim": "..."}],
  "inaccessible_source_tables": ["DB.SCHEMA.TABLE", ...]
}
```

Add to scope summary line in Step 10.5:
```
  Metadata quality: <N> issues found (<Y> HIGH, <Z> MEDIUM)
```

---

## Step 10.4e: Measure column coverage

For each table in the SV, count total columns in the underlying source table:

```sql
SELECT
    TABLE_CATALOG,
    TABLE_SCHEMA,
    TABLE_NAME,
    COUNT(*) AS TOTAL_COLUMNS
FROM <SV_DB>.INFORMATION_SCHEMA.COLUMNS
WHERE (TABLE_SCHEMA, TABLE_NAME) IN (
    ('<schema1>', '<table1>'),
    ('<schema2>', '<table2>')
    -- repeat for each table in SV_TABLES
)
GROUP BY 1, 2, 3;
```

**Note:** If SV tables span multiple databases, run one query per database using that database's `INFORMATION_SCHEMA.COLUMNS`.

Calculate:
- `TOTAL_SV_COLUMNS` — number of columns defined in the SV
- `TOTAL_SOURCE_COLUMNS` — sum of columns across all underlying tables
- `COVERAGE_PCT` — `TOTAL_SV_COLUMNS / TOTAL_SOURCE_COLUMNS * 100`

---

## Step 10.4f: Relationship join type compatibility — CRITICAL check

For each relationship in `SV_RELATIONSHIPS`, verify that the join columns on both sides have compatible data types. This is a **CRITICAL severity finding** — a type-mismatched relationship passes SV validation and DESCRIBE silently, but causes every SQL generation attempt on that join path to fail at runtime. This check is entirely static and requires no ACCOUNT_USAGE access.

**Why it matters:** Generated SQL joins on those columns. If the join columns have incompatible types (e.g., `NUMBER(38,0)` joined to `VARCHAR(30)`), the join can fail with a conversion error on non-numeric values or match nothing. Verify before relying on the severity: confirm with one test query on the join path.

RELATIONSHIP rows carry **logical** table names and JSON-array keys (`FOREIGN_KEY`, `REF_KEY`). Map each logical table to `BASE_TABLE_DATABASE_NAME.BASE_TABLE_SCHEMA_NAME.BASE_TABLE_NAME` from its TABLE rows, and map logical key names to physical columns via the DIMENSION/FACT `EXPRESSION` rows. Compare composite keys position by position. Then retrieve both join columns' types from `INFORMATION_SCHEMA.COLUMNS`:

```sql
SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, NUMERIC_PRECISION, NUMERIC_SCALE, CHARACTER_MAXIMUM_LENGTH
FROM <DB>.INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = '<schema>'
  AND (
      (TABLE_NAME = '<left_table>'  AND COLUMN_NAME = '<left_col>')
   OR (TABLE_NAME = '<right_table>' AND COLUMN_NAME = '<right_col>')
  );
```

> If the SV spans multiple databases, run one query per database using that database's `INFORMATION_SCHEMA`.
>
> ⚠️ When relationship endpoints span different schemas, query each endpoint's schema separately.
> The current query assumes both sides are in the same schema.

**Severity rules:**

| Mismatch | Severity |
|---|---|
| `NUMBER` / `INT` / `FLOAT` ↔ `VARCHAR` / `TEXT` / `CHAR` | **CRITICAL** — joins on this path can fail or return wrong rows |
| `BOOLEAN` ↔ any non-boolean | **CRITICAL** |
| `VARIANT` / `OBJECT` / `ARRAY` ↔ any structured type | **CRITICAL** |
| `DATE` ↔ `TIMESTAMP_*` | **HIGH** — implicit cast exists but may lose time precision |
| `NUMBER(x,0)` ↔ `NUMBER(y,0)` (different precision) | **MEDIUM** — potential truncation |
| `VARCHAR(x)` ↔ `VARCHAR(y)` (different lengths) | **LOW** — flag if left max length > right |

**On CRITICAL — present to user:**

```
🚫 CRITICAL: TYPE MISMATCH ON RELATIONSHIP JOIN

  Relationship: <rel_name>
  Left:   <left_table>.<left_col>   →  <LEFT_DATA_TYPE>
  Right:  <right_table>.<right_col> →  <RIGHT_DATA_TYPE>

  Queries that traverse this relationship can fail or mis-join.
  Fix the relationship before trusting this SV in production.

  Resolution options:
    A) Find the correct join column — run:
       SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE FROM <DB>.INFORMATION_SCHEMA.COLUMNS
       WHERE (TABLE_SCHEMA, TABLE_NAME) IN (('<left_schema>', '<left>'), ('<right_schema>', '<right>'))
       ORDER BY DATA_TYPE, COLUMN_NAME;
       Look for a column with a matching type on both sides.

    B) Add an indirect bridge — if a third table has compatible keys to both
       sides, replace this direct relationship with two clean hops:
       FCT → (NUMBER key) → BRIDGE → (NUMBER key) → DIM

    C) Fix at source — cast or coerce the mismatched column by pointing the
       SV table entry to a view that applies the cast.
```

Store all findings as `JOIN_TYPE_FINDINGS`:
```
[{
  "rel_name": "...",
  "left_table": "...", "left_col": "...", "left_type": "...",
  "right_table": "...", "right_col": "...", "right_type": "...",
  "severity": "CRITICAL|HIGH|MEDIUM|LOW"
}]
```

---

## Step 10.5: Present audit scope summary

Display the following summary:

```
Semantic View Audit Scope
═════════════════════════

  Semantic View:    <SV_FQN>
  Tables:           <N> tables included
  Columns in SV:    <X> (out of <Y> total in underlying tables)
  Coverage:         <X>/<Y> = <Z>%
  Relationships:    <N> defined
  Verified Queries: <N> defined — VQR Health: <X> issues (<Y> HIGH, <Z> MEDIUM)
  Topology:         <orphans> orphans, <missing_using> multi-path pairs
  Join type safety: <N> relationships checked — <X> CRITICAL, <Y> HIGH, <Z> MEDIUM
  Metric integrity: <N> issues found
  Metadata quality: <N> issues found (<Y> HIGH, <Z> MEDIUM)

  Tables:
    - <DB.SCHEMA.TABLE1>  (<A> of <B> columns included)
    - <DB.SCHEMA.TABLE2>  (<C> of <D> columns included)
    ...
```

---

## MANDATORY STOP — User Confirms Audit

Ask the user:

```
Proceed with usage-based audit?

This will query SNOWFLAKE.ACCOUNT_USAGE views (QUERY_HISTORY, ACCESS_HISTORY)
to analyze the last 30 days of query patterns against these tables.

Requirements:
  - IMPORTED PRIVILEGES on SNOWFLAKE database (for ACCOUNT_USAGE views)
  - ACCESS_HISTORY requires Enterprise Edition or higher

Proceed? (yes / no)
```

**Wait for user confirmation before loading Phase 11 (INTERACTIVE mode). AUTONOMOUS:** proceed
if the privilege requirements above are met; log the decision. If IMPORTED PRIVILEGES
are missing, this is a genuine blocker in both modes (can't be auto-resolved).

If user says no, stop and report: "Audit cancelled. The describe summary above is available for reference."

---

## Step 10.6: Store audit context

After user confirms, store these variables for subsequent phases:

| Variable | Contents |
|----------|----------|
| `SV_FQN` | Fully qualified semantic view name |
| `SV_DB`, `SV_SCHEMA`, `SV_NAME` | Parsed components |
| `SV_TABLES` | List of FQN table references in the SV |
| `SV_COLUMNS` | Dict: table.column → {classification, data_type} |
| `SV_RELATIONSHIPS` | List of relationship definitions |
| `SV_VQRS` | List of verified query representations |
| `VQR_HEALTH_FINDINGS` | Dict keyed as in Step 10.4a |
| `TOPOLOGY_FINDINGS` | Dict: orphans, missing_using |
| `JOIN_TYPE_FINDINGS` | List of {rel_name, left_table, left_col, left_type, right_table, right_col, right_type, severity} |
| `METRIC_INTEGRITY_FINDINGS` | Dict: semi_additive_candidates, non_boolean_filter_facts, pk_cardinality_suspects |
| `METADATA_QUALITY_FINDINGS` | Dict: ai_sql_generation_missing, tables/cols missing comment, sample_values gaps, inaccessible tables |
| `TOTAL_SV_COLUMNS` | Count of columns in the SV |
| `TOTAL_SOURCE_COLUMNS` | Count of columns in underlying tables |
| `COVERAGE_PCT` | Column coverage percentage |
