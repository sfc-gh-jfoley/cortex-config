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
- All columns with their classification (FACT, DIMENSION, MEASURE/METRIC, TIME_DIMENSION)
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

**Canonical check set:** `references/vqr-eval-health.md` defines the full pre-flight check set (Checks 1–7, with severities, detection code, and fix guidance). The checks below are the subset most relevant to an *audit* (structural, no eval launch). For the full set including CA-extension column-drop (CRITICAL, Snowsight-built SVs only) and GROUP BY alias, see the reference. Run all 7 if you intend to launch an eval after this audit; run the subset below for a structural audit only.

**Check 1 — FQN Table References (HIGH)**
Scan each VQR SQL for fully qualified table references (e.g., `DB.SCHEMA.table_name`).
Per the [Snowflake VQR specification](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst/verified-query-repository), VQR SQL **must** use logical table names prefixed with `__` (e.g., `__FCT_TRANSACTIONS`). Raw FQN references are invalid and can cause Cortex Analyst to generate SQL that bypasses the SV relationship graph.

Detection pattern: any `WORD.WORD.WORD` or `WORD.WORD.table_name` reference in VQR SQL where the final segment matches an SV table's physical name.

**Check 2 — Bare Physical / Logical Table Names Without `__` (MEDIUM)**
Scan for bare table names in FROM/JOIN position that match an SV physical or logical table name but are **not** prefixed with `__`.
These must become `__TABLE_NAME` references. A bare logical name appears to work when logical and physical names coincide, but is not portable and orphans the VQR when they diverge.

Detection pattern: `\bFROM\s+<table_name>\b` or `\bJOIN\s+<table_name>\b` where `<table_name>` (case-insensitive) is in the SV's physical or logical table list and is NOT a CTE defined in the same SQL.

**Check 3 — Columns Not In SV (MEDIUM)**
For each `alias.column_name` reference in VQR SQL, verify `column_name` exists as a dimension, fact, or metric in the SV.
Skip: CTE-defined aliases, SQL keywords, and numeric literals.

**Check 4 — Duplicate VQR Keys (LOW)**
Check for VQR entries with identical `name` field values. Near-duplicates that differ only by trailing whitespace or newlines count as duplicates.

**Check 5 — Aggregation Mismatch (HIGH)**
For each VQR that aggregates a metric's source column, compare the aggregation function against the metric's EXPRESSION from DESCRIBE. A VQR using `SUM(amount)` where the metric is `AVG(amount)` scores 0 every time regardless of model quality. See `references/vqr-eval-health.md` Check 7 for detection SQL and fix guidance.

**Check 6 — Metric Coverage Gaps (MEDIUM)**
SV metrics with no VQR have zero eval signal — if the model generates wrong SQL for them, you'll never know. Cross-reference VQR SQL against metrics from DESCRIBE; route uncovered metrics to `vqr-generator`. See `references/vqr-eval-health.md` Check 5.

**Check 7 — CA Extension Column-Drop (CRITICAL, Snowsight-built SVs only)**
If the SV was built in Snowsight and contains a `with extension (CA='...')` block, the eval framework drops columns not in the CA extension's declared list, causing `invalid identifier` errors before scoring. Detect with `GET_DDL` and `'with extension' in ddl.lower()`; create a DDL-only eval copy before launching an eval. See `references/vqr-eval-health.md` Check 3 for the full strip procedure.

Store findings as `VQR_HEALTH_FINDINGS`:
```
{
  "total_vqrs": <N>,
  "fqn_bypass":        [{"vqr_name": "...", "tables": ["DB.SCHEMA.T1", ...]}],
  "bare_no_prefix":    [{"vqr_name": "...", "tables": ["T1", ...]}],
  "unknown_cols":      [{"vqr_name": "...", "columns": ["COL1", ...]}],
  "duplicate_keys":    [{"vqr_name": "...", "count": N}],
  "agg_mismatch":      [{"vqr_name": "...", "metric": "...", "vqr_agg": "...", "metric_agg": "..."}],
  "uncovered_metrics": [{"metric": "...", "table": "..."}],
  "ca_extension_drop": [{"present": true, "stripped_copy_fqn": "..."}]
}
```

Add to the scope summary line in Step 10.5:
```
  VQR Health:       <N> VQRs checked — <X> issues found (<Y> HIGH, <Z> MEDIUM, <W> CRITICAL)
```

---

## Step 10.4b: Topology Check

> **DESCRIBE output structure** (per Snowflake docs): `DESCRIBE SEMANTIC VIEW` returns an EAV-format result with these exact columns (always use double-quoted lowercase in RESULT_SCAN):
> - `"object_kind"` — `TABLE`, `RELATIONSHIP`, `DIMENSION`, `FACT`, `METRIC`, `DERIVED_METRIC`, `CUSTOM_INSTRUCTIONS`, `AI_VERIFIED_QUERY`, or `NULL`
> - `"object_name"` — name of the entity
> - `"parent_entity"` — parent table for dims/facts/metrics; NULL for tables, VQRs, custom instructions
> - `"property"` — property key (e.g. `TABLE`, `REF_TABLE`, `EXPRESSION`, `DATA_TYPE`, `SYNONYMS`)
> - `"property_value"` — property value
>
> For **relationships**: there is no `left_table` or `right_table` column. Each relationship has multiple rows — use `"property" = 'TABLE'` for the left/source table and `"property" = 'REF_TABLE'` for the right/referenced table.
>
> ⚠️ **Column-name pre-flight**: Run `SELECT * FROM TABLE(RESULT_SCAN(LAST_QUERY_ID())) LIMIT 0;` immediately after DESCRIBE to confirm the actual column names returned by your account version before running the queries below.

Using the DESCRIBE result from Step 10.2 (re-run if needed so `LAST_QUERY_ID()` is current):

**Check 1 — Fan trap** (metric at coarser grain than a dimension only reachable via bridge table → inflated numbers)
```sql
WITH sv_meta AS (SELECT * FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))),
metric_tbl AS (
  SELECT DISTINCT "parent_entity" AS t
  FROM sv_meta WHERE "object_kind" = 'METRIC'
),
dim_tbl AS (
  SELECT DISTINCT "parent_entity" AS t
  FROM sv_meta WHERE "object_kind" = 'DIMENSION'
),
rels AS (
  SELECT "object_name" AS rel_name,
         MAX(CASE WHEN "property" = 'TABLE'     THEN "property_value" END) AS lt,
         MAX(CASE WHEN "property" = 'REF_TABLE' THEN "property_value" END) AS rt
  FROM sv_meta WHERE "object_kind" = 'RELATIONSHIP'
  GROUP BY "object_name"
)
SELECT 'FAN_TRAP' AS issue_type, m.t AS metric_table, d.t AS dim_table, r2.lt AS bridge_table,
  'SUM/COUNT on ' || m.t || ' inflated when grouped by ' || d.t || ' dims (bridge: ' || r2.lt || ')' AS detail
FROM metric_tbl m
JOIN rels r1 ON r1.lt = m.t
JOIN rels r2 ON r2.rt = r1.rt AND r2.lt != m.t
JOIN dim_tbl d ON d.t = r2.lt
WHERE d.t != m.t;
```

**Check 2 — Chasm trap** (two metric tables converging on shared dimension table → double counting)
```sql
WITH sv_meta AS (SELECT * FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))),
metric_tbl AS (
  SELECT DISTINCT "parent_entity" AS t FROM sv_meta WHERE "object_kind" = 'METRIC'
),
rels AS (
  SELECT "object_name" AS rel_name,
         MAX(CASE WHEN "property" = 'TABLE'     THEN "property_value" END) AS lt,
         MAX(CASE WHEN "property" = 'REF_TABLE' THEN "property_value" END) AS rt
  FROM sv_meta WHERE "object_kind" = 'RELATIONSHIP' GROUP BY "object_name"
)
SELECT 'CHASM_TRAP' AS issue_type, m1.t AS metric_1, m2.t AS metric_2, r1.rt AS shared_table,
  'Metrics on ' || m1.t || ' and ' || m2.t || ' both reference ' || r1.rt || ' — double-count risk' AS detail
FROM metric_tbl m1
JOIN rels r1 ON r1.lt = m1.t
JOIN metric_tbl m2 ON m2.t != m1.t AND m2.t > m1.t
JOIN rels r2 ON r2.lt = m2.t AND r2.rt = r1.rt;
```

**Check 3 — Orphan tables** (table in SV with no RELATIONSHIP entry → queries against its columns will error at runtime)
```sql
WITH sv_meta AS (SELECT * FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))),
all_tbl AS (
  SELECT DISTINCT "object_name" AS t
  FROM sv_meta WHERE "object_kind" = 'TABLE'
),
rel_tbl AS (
  SELECT "property_value" AS t FROM sv_meta
  WHERE "object_kind" = 'RELATIONSHIP' AND "property" IN ('TABLE', 'REF_TABLE')
)
SELECT 'ORPHAN' AS issue_type, t,
  'Table has no RELATIONSHIP — queries using its dimensions/facts will fail at runtime' AS detail
FROM all_tbl WHERE t NOT IN (SELECT t FROM rel_tbl);
```
> Single-table SVs are exempt — a lone table needs no relationship.

**Check 4 — USING completeness** (tables with multiple relationship paths to same target → ambiguous routing for metrics)

From the RESULT_SCAN rows: for each pair of tables, count how many distinct relationship names connect them. If any pair has 2+ relationships, verify that metrics on the source table include USING. `DESCRIBE SEMANTIC VIEW` does not expose the USING clause directly — flag as: "Multi-path table pairs detected — verify metrics on `<table>` include `USING (<rel_name>)` by inspecting the DDL: `SELECT GET_DDL('SEMANTIC VIEW', '<SV_FQN>')`."

Store findings as `TOPOLOGY_FINDINGS`:
```
{
  "fan_traps":   [{"metric_table": "...", "dim_table": "...", "bridge": "..."}],
  "chasm_traps": [{"metric_1": "...", "metric_2": "...", "shared_table": "..."}],
  "orphans":     ["TABLE_NAME", ...],
  "missing_using": [{"table": "...", "relationship_paths": N}]
}
```

Add to scope summary line in Step 10.5:
```
  Topology:         <fan_traps> fan traps, <chasm_traps> chasm traps, <orphans> orphans
```

---

## Step 10.4c: Metric Integrity Check

> **What DESCRIBE exposes for FACTs, DIMENSIONs, and METRICs** (per Snowflake docs): For each object, DESCRIBE returns rows with `property` = `TABLE`, `EXPRESSION`, `DATA_TYPE`, and `ACCESS_MODIFIER`. The full SQL expression IS available from DESCRIBE — use it directly for Checks 1 and 2 below.

**Check 1 — Semi-additive metrics (NON ADDITIVE BY)**
From the DESCRIBE RESULT_SCAN, extract all METRIC rows and their EXPRESSION values:
```sql
SELECT "object_name" AS metric_name, "parent_entity" AS table_name, "property_value" AS expression
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE "object_kind" = 'METRIC' AND "property" = 'EXPRESSION';
```
For each metric whose expression starts with `SUM(` or `COUNT(`, also retrieve the parent table's COMMENT. If any of these keywords appear in the metric name, expression, or table COMMENT: `snapshot`, `balance`, `headcount`, `inventory`, `pipeline`, `open`, `active`, `subscriber` — flag as a potential semi-additive metric missing `NON ADDITIVE BY`. Confirm with the SV owner whether the underlying data is a snapshot or a flow.

**Check 2 — LABELS=(FILTER) on non-boolean expressions**
From DESCRIBE, extract all FACT rows with their EXPRESSION and DATA_TYPE:
```sql
SELECT "object_name", "parent_entity", "property", "property_value"
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE "object_kind" = 'FACT' AND "property" IN ('EXPRESSION', 'DATA_TYPE');
```
DESCRIBE does not expose the LABELS=(FILTER) flag directly. Infer filter facts by DATA_TYPE: facts with `DATA_TYPE = 'BOOLEAN'` are likely FILTER-labeled. Verify the expression looks like a boolean predicate (comparison, IN list, IS NULL). For definitive confirmation of which facts carry `LABELS=(FILTER)`, inspect the full DDL:
```sql
SELECT GET_DDL('SEMANTIC VIEW', '<DB>.<SCHEMA>.<SV_NAME>');
```

**Check 3 — PK cardinality (the cardinality lie)**
From DESCRIBE, extract PRIMARY_KEY and FOREIGN_KEY values to find PK columns that also appear as FK columns. `"parent_entity"` is NULL for RELATIONSHIP rows — use the pivot pattern to extract the source table from the `TABLE` property:
```sql
WITH sv_meta AS (SELECT * FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))),
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
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE "object_kind" = 'CUSTOM_INSTRUCTIONS';
```
The `property` column will contain `AI_SQL_GENERATION` and/or `AI_QUESTION_CATEGORIZATION`. If no `CUSTOM_INSTRUCTIONS` rows exist, or none have `property = 'AI_SQL_GENERATION'` with a non-empty `property_value`, flag as HIGH — missing `AI_SQL_GENERATION`.

> **YAML models**: Legacy stage-based YAML files use `custom_instructions: <string>` (legacy) or `module_custom_instructions.sql_generation: <string>` (modern). Both map to the same `AI_SQL_GENERATION` instruction when loaded. Check both fields if the SV was created from a YAML file.

**Check 2 — COMMENT coverage**
From DESCRIBE, count tables and columns missing COMMENT. COMMENTs appear as rows with `property = 'COMMENT'`. A missing COMMENT means no row exists for that `object_kind`/`object_name` pair with `property = 'COMMENT'`.

```sql
-- Count objects missing COMMENT by kind
WITH sv_meta AS (SELECT * FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))),
has_comment AS (
  SELECT "object_kind", "object_name"
  FROM sv_meta WHERE "property" = 'COMMENT' AND "property_value" IS NOT NULL
),
all_objects AS (
  SELECT DISTINCT "object_kind", "object_name"
  FROM sv_meta WHERE "object_kind" IN ('TABLE','FACT','DIMENSION','METRIC')
)
SELECT a."object_kind", COUNT(*) AS missing_comment_count
FROM all_objects a
LEFT JOIN has_comment h ON a."object_kind" = h."object_kind" AND a."object_name" = h."object_name"
WHERE h."object_name" IS NULL
GROUP BY a."object_kind";
```

| Threshold | Severity |
|---|---|
| > 25% of tables missing COMMENT | HIGH |
| 10–25% of tables missing COMMENT | MEDIUM |
| > 30% of columns (facts/dims/metrics) missing COMMENT | MEDIUM |

**Check 3 — WITH SYNONYMS coverage**
From DESCRIBE, SYNONYMS appear as `property = 'SYNONYMS'` rows. Count tables and key columns with no synonyms entry, or where `property_value` = `'[]'` (empty array).

**Check 4 — SAMPLE_VALUES and IS_ENUM coverage**
`SAMPLE_VALUES` and `IS_ENUM` are **not exposed in DESCRIBE output** (per Snowflake docs — only `TABLE`, `EXPRESSION`, `DATA_TYPE`, `ACCESS_MODIFIER`, `SYNONYMS`, `COMMENT`, and Cortex Search properties are listed). To check these, retrieve the full DDL:
```sql
SELECT GET_DDL('SEMANTIC VIEW', '<DB>.<SCHEMA>.<SV_NAME>');
-- Or for YAML-based SVs:
SELECT SYSTEM$READ_YAML_FROM_SEMANTIC_VIEW('<DB>.<SCHEMA>.<SV_NAME>');
```
From the DDL or YAML, flag any VARCHAR/TEXT dimension that has no `SAMPLE_VALUES` and no `IS_ENUM` as MEDIUM — missing sample values force the model to guess valid filter values.

**Check 5 — Source object accessibility**
Verify the current role can still SELECT from each underlying source table. Base table names come from DESCRIBE rows where `object_kind = 'TABLE'` and `property = 'BASE_TABLE_NAME'` (with `BASE_TABLE_DATABASE_NAME` and `BASE_TABLE_SCHEMA_NAME` for the full FQN):
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
  "tables_missing_synonyms": ["TABLE_NAME", ...],
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
  Topology:         <fan_traps> fan traps, <chasm_traps> chasm traps, <orphans> orphans
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

**Wait for user confirmation before loading Phase 11.**

If user says no, stop and report: "Audit cancelled. The describe summary above is available for reference."

---

## Step 10.6: Store audit context

After user confirms, store these variables for subsequent phases:

## Output variables

| Variable | Contents |
|----------|----------|
| `SV_FQN` | Fully qualified semantic view name |
| `SV_DB`, `SV_SCHEMA`, `SV_NAME` | Parsed components |
| `SV_TABLES` | List of FQN table references in the SV |
| `SV_COLUMNS` | Dict: table.column → {classification, data_type} |
| `SV_RELATIONSHIPS` | List of relationship definitions |
| `SV_VQRS` | List of verified query representations |
| `VQR_HEALTH_FINDINGS` | Dict: fqn_bypass, bare_physical, unknown_cols, duplicate_keys |
| `TOPOLOGY_FINDINGS` | Dict: fan_traps, chasm_traps, orphans, missing_using |
| `METRIC_INTEGRITY_FINDINGS` | Dict: semi_additive_candidates, non_boolean_filter_facts, pk_cardinality_suspects |
| `METADATA_QUALITY_FINDINGS` | Dict: ai_sql_generation_missing, tables/cols missing comment/synonyms, sample_values gaps, inaccessible tables |
| `TOTAL_SV_COLUMNS` | Count of columns in the SV |
| `TOTAL_SOURCE_COLUMNS` | Count of columns in underlying tables |
| `COVERAGE_PCT` | Column coverage percentage |
