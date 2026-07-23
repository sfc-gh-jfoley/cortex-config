---
name: sv-audit-phase12-audit-recommend
description: Present prioritized audit findings with improvement recommendations and user approval gate before any changes
---

# Phase 12: Audit Recommend

## Purpose
Compile all findings from Phase 11 into a structured audit report, rank recommendations by impact, and present to the user for approval before any modifications are made.

**Inputs required from Phase 10:** `SV_FQN`, `SV_TABLES`, `SV_COLUMNS`, `SV_RELATIONSHIPS`, `TOTAL_SV_COLUMNS`, `TOTAL_SOURCE_COLUMNS`, `VQR_HEALTH_FINDINGS`, `TOPOLOGY_FINDINGS`, `METRIC_INTEGRITY_FINDINGS`, `METADATA_QUALITY_FINDINGS`
**Inputs required from Phase 11:** `MISSING_TABLE_CANDIDATES`, `MISSING_COLUMNS`, `UNUSED_COLUMNS`, `RELATIONSHIP_GAPS`, `FILTER_COLUMNS`, `GROUPBY_COLUMNS`, `AGGREGATE_COLUMNS`, `NEIGHBORING_TABLES`, `ACCESS_HISTORY_AVAILABLE`, `QUERY_COUNT`, `DISTINCT_USERS`

---

## Step 12A: Compile findings into report

Build the full audit report. Use the exact structure below, omitting any section that has zero findings.

```markdown
# Semantic View Audit Report: <SV_FQN>

> Analyzed <QUERY_COUNT> queries from <DISTINCT_USERS> users over the last 30 days.
> ACCESS_HISTORY: <available / not available (Standard Edition)>

---

## 1. Structural Topology

**Only include this section if `TOPOLOGY_FINDINGS` contains issues.**

| Issue Type | Severity | Details |
|---|---|---|
| Fan trap | CRITICAL | Metric `<table>` inflated when grouped by `<dim_table>` dims (bridge: `<bridge>`) |
| Chasm trap | CRITICAL | Metrics `<m1>` and `<m2>` double-count when joined through `<shared_table>` |
| Orphan table | HIGH | `<table>` has no RELATIONSHIP — queries against its columns will fail at runtime |
| Missing USING | HIGH | Table pair `<A>↔<B>` has 2+ relationship paths — metrics need USING clause |

**Fan trap fix:** Move the metric to the bridge-table grain, or pre-aggregate.
**Chasm trap fix:** Pre-aggregate each fact to the shared dimension grain separately in CTEs before joining.
**Orphan fix:** Add the missing RELATIONSHIP or remove the orphaned table.
**USING fix:** Add `USING (<rel_name>)` to every metric on the ambiguous table.

---

## 2. Source Object Accessibility

**Only include this section if `METADATA_QUALITY_FINDINGS.inaccessible_source_tables` is non-empty.**

The current role cannot SELECT from one or more source tables. The SV will fail at query time.

| # | Table FQN | Error |
|---|---|---|
| 1 | `<TABLE>` | `<error message>` |

**Fix:** Grant `SELECT` on the inaccessible table(s) to the role that owns or queries the SV, or update the SV definition to remove/replace the inaccessible source.

---

## 3. VQR Health

**Only include this section if `VQR_HEALTH_FINDINGS` contains at least one issue.**

Checked <N> verified queries for structural compliance with the [Snowflake VQR specification](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst/verified-query-repository).

| Issue Type | Severity | Count | VQRs Affected |
|---|---|---|---|
| FQN table references (use `__logical_name` instead) | HIGH | <N> | <list> |
| Bare physical table names (use `__logical_name` instead) | MEDIUM | <N> | <list> |
| Columns not in SV | MEDIUM | <N> | <list> |
| Duplicate VQR name keys | LOW | <N> | <list> |

**Why this matters:**  
Per the Snowflake VQR spec, SQL in verified queries must reference logical table names with the `__` prefix (e.g., `__FCT_TRANSACTIONS`), not physical FQNs (`DB.SCHEMA.FCT_TRANSACTIONS`) or bare table names. Non-compliant VQR SQL can cause Cortex Analyst to generate SQL that bypasses the SV's defined relationships, leading to incorrect joins or missing filter logic.

**Fix:**  
Replace every `DB.SCHEMA.table_name` or bare `table_name` table reference in VQR SQL with `__TABLE_LOGICAL_NAME`, where `TABLE_LOGICAL_NAME` is the `name:` field defined for that table in the semantic view. Column names do not change if the SV `expr` matches the column name.

---

## 4. Metric Integrity

**Only include this section if `METRIC_INTEGRITY_FINDINGS` contains issues.**

| Issue Type | Severity | Metric / Fact | Table | Detail |
|---|---|---|---|---|
| Semi-additive SUM | HIGH | `<metric>` | `<table>` | Expression `<expr>` on snapshot-indicating table — may need `NON ADDITIVE BY` |
| Non-boolean FILTER fact | HIGH | `<fact>` | `<table>` | DATA_TYPE is not BOOLEAN — confirm via `SELECT GET_DDL('SEMANTIC VIEW', '<fqn>')` |
| PK cardinality suspect | MEDIUM | — | `<table>` | PK column `<col>` also appears as FK — run `SELECT COUNT(*), COUNT(DISTINCT <col>) FROM <table>` |

**Semi-additive fix:** Add `NON ADDITIVE BY (<time_dimension> DESC)` to the metric.
**Non-boolean FILTER fix:** Confirm via `GET_DDL('SEMANTIC VIEW', ...)` and ensure the FACT expression resolves to BOOLEAN.
**PK cardinality fix:** Run the cardinality check. If counts differ, declare the actually-unique column as PRIMARY KEY instead.

---

## 5. Missing Tables

Tables frequently joined with SV tables in user queries but not included in the SV.

| # | Table | Co-query Count | Users | Join Key | Recommendation |
|---|-------|---------------|-------|----------|----------------|
| 1 | <TABLE> | <N> | <N> | <KEY> | ADD / CONSIDER / SKIP |
...

Recommendation logic:
- **ADD** — >= 50 co-queries OR >= 5 distinct users
- **CONSIDER** — 20-49 co-queries OR 3-4 distinct users
- **SKIP** — < 20 co-queries AND < 3 distinct users

---

## 6. Missing Columns

Columns frequently accessed by users but not defined in the SV.

| # | Column | Table | Access Count | Users | Suggested Role | Recommendation |
|---|--------|-------|-------------|-------|----------------|----------------|
| 1 | <COL> | <TABLE> | <N> | <N> | FACT / DIMENSION | ADD |
...

Suggested role logic:
- Column appears in GROUP BY or WHERE → **DIMENSION**
- Column appears in WHERE only with equality checks → **DIMENSION** with `label: filter`
- Column appears in SUM/AVG/COUNT → **FACT** (with corresponding default_aggregation)
- Column appears in GROUP BY AND aggregate → **DIMENSION** (grouping takes precedence)
- DATE/TIMESTAMP type used in filters → **TIME_DIMENSION**

---

## 7. Unused Columns

Columns defined in the SV but with zero access in the last 30 days.

| # | Column | Table | SV Role | Recommendation |
|---|--------|-------|---------|----------------|
| 1 | <COL> | <TABLE> | <ROLE> | REMOVE / KEEP |
...

Recommendation logic:
- **REMOVE** — zero access AND not part of a relationship key
- **KEEP** — zero access BUT is a relationship key or primary key (note: "relationship key — keep")

> Note: Unused columns are low priority. Removing them reduces SV surface area
> but does not break existing queries. Consider keeping columns that may be
> needed for future use cases.

---

## 8. Relationship Gaps

JOIN patterns observed in user queries that have no corresponding RELATIONSHIP in the SV.

| # | From Table | From Column | To Table | To Column | Query Frequency | Inferred Type | Recommendation |
|---|-----------|-------------|----------|-----------|----------------|---------------|----------------|
| 1 | <TABLE> | <COL> | <TABLE> | <COL> | <N> queries | MANY_TO_ONE | ADD RELATIONSHIP |
...

All relationship gaps are recommended as **ADD** — without relationships, Cortex Analyst cannot auto-join tables to answer cross-table questions.

---

## 9. Metric Opportunities

Aggregate patterns found in user queries that could be defined as SV metrics.

| # | Expression | Base Column | Table | Frequency | Suggested Metric Name |
|---|-----------|-------------|-------|-----------|-----------------------|
| 1 | SUM(<COL>) | <COL> | <TABLE> | <N> queries | TOTAL_<COL> |
| 2 | AVG(<COL>) | <COL> | <TABLE> | <N> queries | AVG_<COL> |
| 3 | COUNT(DISTINCT <COL>) | <COL> | <TABLE> | <N> queries | UNIQUE_<COL>_COUNT |
...

> Metrics are optional but improve Cortex Analyst accuracy for common aggregations.
> They pre-define the aggregation so the LLM does not have to infer it.

---

## 10. Metadata Quality

**Only include this section if `METADATA_QUALITY_FINDINGS` contains issues.**

| Issue | Severity | Count | Detail |
|---|---|---|---|
| AI\_SQL\_GENERATION missing | HIGH | — | No `CUSTOM_INSTRUCTIONS` row with `property='AI_SQL_GENERATION'` in DESCRIBE output |
| Tables missing COMMENT | MEDIUM/HIGH | `<N>` | `<list of table names>` |
| Columns missing COMMENT | MEDIUM | `<N>` | >30% of facts/dims/metrics uncovered |
| Tables or columns missing synonyms | LOW | `<N>` | `<list>` |
| VARCHAR dims missing SAMPLE\_VALUES | MEDIUM | `<N>` | Requires DDL inspection: `GET_DDL('SEMANTIC VIEW', ...)` |

**AI\_SQL\_GENERATION fix:** Add via `CREATE OR ALTER SEMANTIC VIEW` with guidance on: which date column to use, gross vs net revenue distinction, filters to always/never apply, column disambiguation rules. For YAML models: use `module_custom_instructions.sql_generation` (modern) or `custom_instructions` (legacy).

**COMMENT fix:** Add COMMENT to every table and key column. Prioritize tables first, then facts/metrics, then dimensions.

**SAMPLE\_VALUES fix:** Retrieve the full DDL with `SELECT GET_DDL('SEMANTIC VIEW', '<DB>.<SCHEMA>.<SV_NAME>')` or the YAML with `SELECT SYSTEM$READ_YAML_FROM_SEMANTIC_VIEW(...)`. For each VARCHAR dimension with enumerated values (status codes, region codes, categories), add `SAMPLE_VALUES ('val1', 'val2', 'val3') IS_ENUM` to the dimension in the DDL.

---

## 11. Size Assessment

| Metric | Current | After Changes |
|--------|---------|---------------|
| Tables | <N> | <N + additions - removals> |
| Columns | <N> | <N + additions - removals> |
| Relationships | <N> | <N + additions> |
| Coverage | <X>% | <Y>% |
```

**Size guidance:**
- **Compact** (< 30 columns): Good for focused use cases
- **Standard** (30-80 columns): Typical for department-level SVs
- **Large** (80-150 columns): Consider splitting by domain
- **Oversized** (> 150 columns): Recommend splitting into domain-specific SVs

If the resulting SV would be **oversized**, add a note:

```
Size Warning: The recommended changes would bring the SV to <N> columns
across <M> tables. Consider splitting into domain-specific semantic views:

  - <SV_NAME>_ORDERS — order and transaction tables
  - <SV_NAME>_CUSTOMERS — customer and demographic tables
  - <SV_NAME>_PRODUCTS — product and inventory tables

This improves Cortex Analyst accuracy and reduces token overhead per query.
```

---

## Step 12B: Priority ranking

Order all recommendations by impact, highest first:

```
Priority Ranking
════════════════

 PRIORITY 1 — Structural Topology  [CRITICAL — wrong numbers or runtime errors]
   Fan traps inflate metrics by the cardinality of the bridge table.
   Chasm traps double-count metrics sharing a dimension.
   Orphan tables cause runtime query failures ("must be related to...").
   → See Section 1

 PRIORITY 2 — Source Object Accessibility  [CRITICAL — SV silently breaks]
   If the current role cannot SELECT from an underlying table, the SV fails
   at query time even though DESCRIBE SEMANTIC VIEW succeeds.
   → See Section 2

 PRIORITY 3 — VQR Format Issues  [HIGH — spec violation, bypasses SV relationships]
   VQR SQL using FQN or bare physical table names violates the VQR specification.
   Reproducible fix: replace table refs with __LOGICAL_TABLE_NAME.
   → See Section 3

 PRIORITY 4 — Metric Integrity  [HIGH — silent wrong results]
   Semi-additive SUM metrics on snapshot data inflate numbers across time.
   FILTER facts on non-boolean expressions produce runtime errors.
   PK declared on a non-unique column disables fan-trap guards silently.
   → See Section 4

 PRIORITY 5 — Missing Tables (ADD-classified)  [HIGH — users bypass the SV]
   Tables frequently joined by users but invisible to the SV.
   → See Section 5

 PRIORITY 6 — Relationship Gaps  [HIGH — Analyst cannot auto-join]
   JOIN patterns from user queries that have no SV RELATIONSHIP defined.
   → See Section 8

 PRIORITY 7 — Missing Columns (high access count)  [MEDIUM]
   Frequently accessed columns not in the SV.
   → See Section 6

 PRIORITY 8 — Metadata Quality  [MEDIUM — degrades question matching]
   Missing AI_SQL_GENERATION, COMMENTs, SYNONYMS, SAMPLE_VALUES.
   → See Section 10

 PRIORITY 9 — Metric Opportunities  [MEDIUM]
   Common aggregations that could be defined as SV metrics.
   → See Section 9

 PRIORITY 10 — Unused Columns  [LOW — cleanup only]
   SV columns with zero access in last 30 days.
   → See Section 7
```

---

## Step 12C: MANDATORY STOP — User Approval Gate

Present the full report from Steps 12A and 12B, then ask:

```
What would you like to do?

  A) Apply all recommendations
     → I'll generate ALTER SEMANTIC VIEW / CREATE OR REPLACE DDL
        using $semantic-view-ddl with these modifications

   B) Apply selected recommendations
      → Tell me which items to include/exclude by section number
         (e.g., "Apply all except Section 5 item #3 and Section 7 item #1")

  C) Export report only
     → I'll save this audit report for offline review
        (no changes to the semantic view)

  D) Cancel
     → End audit with no changes
```

**GATE: Do NOT proceed with any DDL changes until the user explicitly selects A or B.**

---

## Step 12D: Execute approved changes

**If user selects A or B:**

Summarize the approved changes:

```
Approved changes:
  + ADD table: <TABLE> (with relationship to <EXISTING_TABLE>)
  + ADD column: <COL> as DIMENSION on <TABLE>
  + ADD column: <COL> as FACT on <TABLE>
  + ADD relationship: <TABLE1>.<COL> → <TABLE2>.<COL>
  + ADD metric: <METRIC_NAME> = <EXPRESSION>
  - REMOVE column: <COL> from <TABLE>
```

Then advise the user:

```
To apply these changes, invoke $semantic-view-ddl with:

  Semantic view: <SV_FQN>
  Mode: Modify existing (CREATE OR REPLACE)

  Modifications:
    <list of approved changes as natural language instructions>

The semantic-view-ddl skill will generate and execute the DDL.
```

Do NOT generate the DDL directly in this phase — hand off to `$semantic-view-ddl` which has the full DDL generation, validation, and self-check pipeline.

**If user selects C:**

Format the report as a clean markdown summary and present it. Offer to save to a file:

```
Audit report ready. Save to a file? Provide a path or I'll use:
  /tmp/sv_audit_<SV_NAME>_<YYYYMMDD>.md
```

**If user selects D:**

```
Audit complete for <SV_FQN>. No changes applied.
The audit findings above are available for reference in this session.
```

---

## Final Summary

Always end with:

```
Audit complete for <SV_FQN>.

  Findings:
    <N> high-impact improvements identified
    <M> medium-impact improvements identified
    <L> low-priority cleanups suggested

  Next steps:
    → Invoke $semantic-view-ddl to rebuild the SV with approved improvements
    → Re-run $sv-audit in 30 days to measure improvement
```

---

## Output variables

| Variable | Contents |
|----------|----------|
| `AUDIT_REPORT` | Full markdown audit report |
| `APPROVED_CHANGES` | List of user-approved modifications (empty if cancelled/export only) |
| `HANDOFF_INSTRUCTIONS` | Natural language modification instructions for $semantic-view-ddl |
