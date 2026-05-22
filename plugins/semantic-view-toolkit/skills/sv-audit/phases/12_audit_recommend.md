---
name: sv-discovery-phase12-audit-recommend
description: Present prioritized audit findings with improvement recommendations and user approval gate before any changes
---

# Phase 12: Audit Recommend

## Purpose
Compile all findings from Phase 11 into a structured audit report, rank recommendations by impact, and present to the user for approval before any modifications are made.

**Inputs required from Phase 10:** `SV_FQN`, `SV_TABLES`, `SV_COLUMNS`, `SV_RELATIONSHIPS`, `TOTAL_SV_COLUMNS`, `TOTAL_SOURCE_COLUMNS`
**Inputs required from Phase 11:** `MISSING_TABLE_CANDIDATES`, `MISSING_COLUMNS`, `UNUSED_COLUMNS`, `RELATIONSHIP_GAPS`, `FILTER_COLUMNS`, `GROUPBY_COLUMNS`, `AGGREGATE_COLUMNS`, `NEIGHBORING_TABLES`, `ACCESS_HISTORY_AVAILABLE`, `QUERY_COUNT`, `DISTINCT_USERS`

---

## Step 12A: Compile findings into report

Build the full audit report. Use the exact structure below, omitting any section that has zero findings.

```markdown
# Semantic View Audit Report: <SV_FQN>

> Analyzed <QUERY_COUNT> queries from <DISTINCT_USERS> users over the last 30 days.
> ACCESS_HISTORY: <available / not available (Standard Edition)>

---

## 1. Missing Tables

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

## 2. Missing Columns

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

## 3. Unused Columns

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

## 4. Relationship Gaps

JOIN patterns observed in user queries that have no corresponding RELATIONSHIP in the SV.

| # | From Table | From Column | To Table | To Column | Query Frequency | Inferred Type | Recommendation |
|---|-----------|-------------|----------|-----------|----------------|---------------|----------------|
| 1 | <TABLE> | <COL> | <TABLE> | <COL> | <N> queries | MANY_TO_ONE | ADD RELATIONSHIP |
...

All relationship gaps are recommended as **ADD** — without relationships, Cortex Analyst cannot auto-join tables to answer cross-table questions.

---

## 5. Metric Opportunities

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

## 6. Size Assessment

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

 PRIORITY 1 — Relationship Gaps  [HIGH IMPACT]
   Without relationships, Cortex Analyst cannot join tables automatically.
   Users are forced to write manual SQL for cross-table questions.
   → <N> gaps found

 PRIORITY 2 — Missing Tables (ADD-classified)  [HIGH IMPACT]
   Tables frequently joined by users but invisible to the SV.
   Every query requiring these tables bypasses the semantic layer.
   → <N> tables recommended to add

 PRIORITY 3 — Missing Columns (high access count)  [MEDIUM IMPACT]
   Common query patterns not served by the SV. Users must know column
   names and write SQL manually for these fields.
   → <N> columns recommended to add

 PRIORITY 4 — Metric Opportunities  [MEDIUM IMPACT]
   Pre-defining common aggregations improves Analyst accuracy and
   ensures consistent calculation across users.
   → <N> metrics suggested

 PRIORITY 5 — Unused Columns  [LOW IMPACT]
   Cleanup opportunity. Reduces SV complexity but does not unlock
   new capabilities.
   → <N> columns flagged for removal
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
     → Tell me which items to include/exclude by number
        (e.g., "Apply all except Missing Tables #3 and Unused Columns #1")

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
    → Re-run $semantic-view-discovery audit in 30 days to measure improvement
```

---

## Output variables

| Variable | Contents |
|----------|----------|
| `AUDIT_REPORT` | Full markdown audit report |
| `APPROVED_CHANGES` | List of user-approved modifications (empty if cancelled/export only) |
| `HANDOFF_INSTRUCTIONS` | Natural language modification instructions for $semantic-view-ddl |
