---
name: sv-audit-phase12-audit-recommend
description: Present prioritized audit findings with improvement recommendations and user approval gate before any changes
---

# Phase 12: Audit Recommend

## Purpose
Compile all findings from Phase 11 into a structured audit report, rank recommendations by impact, and present to the user for approval before any modifications are made.

**Inputs required from Phase 10:** `SV_FQN`, `SV_TABLES`, `SV_COLUMNS`, `SV_RELATIONSHIPS`, `TOTAL_SV_COLUMNS`, `TOTAL_SOURCE_COLUMNS`, `VQR_HEALTH_FINDINGS`, `TOPOLOGY_FINDINGS`, `JOIN_TYPE_FINDINGS`, `METRIC_INTEGRITY_FINDINGS`, `METADATA_QUALITY_FINDINGS`
**Inputs required from Phase 11:** `MISSING_TABLE_CANDIDATES`, `SUBQUERY_FILTER_CANDIDATES`, `MISSING_COLUMNS`, `UNUSED_COLUMNS`, `RELATIONSHIP_GAPS`, `FILTER_COLUMNS`, `GROUPBY_COLUMNS`, `AGGREGATE_COLUMNS`, `NEIGHBORING_TABLES`, `SV_TABLE_SIZES`, `ACCESS_HISTORY_AVAILABLE`, `QUERY_COUNT`, `DISTINCT_USERS`

---

## Step 12A: Compile findings into report

Build the full audit report. Use the exact structure below, omitting any section that has zero findings.

```markdown
# Semantic View Audit Report: <SV_FQN>

> Analyzed <QUERY_COUNT> queries from <DISTINCT_USERS> users over the last 30 days.
> ACCESS_HISTORY: <available / not available (Standard Edition)>

---

## 0. Join Type Mismatches (Priority 0 — BLOCKING)

**Only include this section if `JOIN_TYPE_FINDINGS` is non-empty.** Always list it first.

| # | Relationship | Left column (type) | Right column (type) | Severity |
|---|---|---|---|---|
| 1 | `<rel_name>` | `<left_table>.<left_col>` (`<left_type>`) | `<right_table>.<right_col>` (`<right_type>`) | CRITICAL / HIGH / MEDIUM / LOW |

**Fix:** Use the resolution options from Phase 10 Step 10.4f (correct join column, bridge
table, or a view that casts at source). Any CRITICAL item blocks recommending the SV for
production use until it is fixed.

---

## 1. Structural Topology

**Only include this section if `TOPOLOGY_FINDINGS` contains issues.** Fan and chasm traps are not
reported: semantic SQL rejects dimensions at a coarser grain than the metric's table (see Phase 10
Step 10.4b).

| Issue Type | Severity | Details |
|---|---|---|
| Orphan table | MEDIUM | `<table>` has no RELATIONSHIP — its fields cannot be combined with other tables |
| Missing USING | HIGH | Table pair `<A>↔<B>` has 2+ relationship paths — metrics need USING clause |

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
| CA extension column-drop (Ref Check 3) | CRITICAL | <N> | <list> |
| Physical FQN table references (Ref Check 1) | HIGH | <N> | <list> |
| Columns not in SV (Ref Check 2) | HIGH | <N> | <list> |
| Aggregation mismatch vs metric definition (Ref Check 7) | HIGH | <N> | <list> |
| Uncovered metrics — no VQR exercises them (Ref Check 5) | MEDIUM | <N> | <metric list> |
| GROUP BY alias (Ref Check 4) | MEDIUM | <N> | <list> |
| Nested subquery, unverified heuristic (Ref Check 8) | MEDIUM | <N> | <list> |
| Bare logical table names, prefer `__` (Ref Check 1) | LOW | <N> | <list> |
| Duplicate VQR name keys | LOW | <N> | <list> |

**Why this matters:**  
VQR SQL that references physical tables or non-existent columns, or aggregates differently from
the SV metric, produces ground truth that a correct answer cannot match. Uncovered metrics have no
eval signal at all.

**Fix:**  
Use the fix guidance in `../../../references/vqr-eval-health.md` for each check. VQR changes are
customer-VQR mutations (gate `SV-VQR-MUTATE`): propose them with current and proposed text, and apply
only what the operator approves (never in AUTONOMOUS mode). Route new VQRs for uncovered metrics to
`vqr-generator`.

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

## 4b. Snippet Pattern Gaps

Run the `sv-snippet-suggester` skill (detection and scoring only, Steps 1–3) against the current SV
DDL (from `SELECT GET_DDL('SEMANTIC_VIEW', '<SV_FQN>')`) and the source table schemas. It reads the
index of `../../../references/sv-snippet-patterns.md` and only the matching pattern sections.

For each pattern that is MATCH or POSSIBLE but NOT already implemented in the SV, surface it here.

**Only include this section if at least one gap is detected.**

| # | Pattern | Signal | Impact | Recommendation |
|---|---------|--------|--------|----------------|
| 1 | `semi_additive_metric` | BALANCE_USD + BALANCE_DATE; SUM metric on snapshot table | Queries without date filter return inflated grand totals | Add `NON ADDITIVE BY (balance_date)` + separate `avg_daily_balance AS AVG(...)` |
| 2 | `range_join` (Preview) | VALID_FROM + VALID_TO on CUSTOMER_SEGMENTS; current join is on latest record only | Revenue attributed to current tier, not historical tier at time of purchase | Add `CONSTRAINT DISTINCT RANGE BETWEEN VALID_FROM AND VALID_TO EXCLUSIVE` |
| … | … | … | … | … |

**Only report patterns the SV clearly should implement.** Do not flag `variables` or
`inline_sv` without strong evidence the user needs them — prefer specific to exhaustive.

Add each gap to the recommendation list. Implementation happens only on a candidate copy (Step 12D).

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

## 5b. Subquery Filter Candidates

**Only include this section if `SUBQUERY_FILTER_CANDIDATES` is non-empty.**

Tables observed in user queries only as WHERE subquery filter targets — not as FROM/JOIN tables.
These are not missing SV relationships; they are already usable at query time via WHERE subquery.

| # | Table | Filter-query Count | Users | Example Pattern | Recommendation |
|---|-------|-------------------|-------|-----------------|----------------|
| 1 | <TABLE> | <N> | <N> | `WHERE id IN (SELECT id FROM <TABLE>)` | ANALYST_RELATIONSHIP / SKIP |

Recommendation logic:
- **ANALYST_RELATIONSHIP** — If users would benefit from asking Cortex Analyst to filter by this
  table's attributes (e.g., "show revenue for EAST region customers"), add it as an SV relationship.
  Without a relationship, Analyst cannot perform this filtering; it is only available in
  manually-authored queries.
- **SKIP** — If the filtering is exclusively programmatic/manual and Analyst access is not needed,
  no SV change is required. WHERE subquery at query time is sufficient.

---

## 6. Missing Columns

Columns frequently accessed by users but not defined in the SV.

| # | Column | Table | Access Count | Users | Suggested Role | Recommendation |
|---|--------|-------|-------------|-------|----------------|----------------|
| 1 | <COL> | <TABLE> | <N> | <N> | FACT / DIMENSION | ADD |
...

Suggested role logic:
- Column appears in GROUP BY or WHERE → **DIMENSION**
- Boolean column used only as a WHERE predicate → **DIMENSION** or **FACT** with `LABELS = (FILTER)`
- Column appears in SUM/AVG/COUNT → **FACT**, plus a **METRIC** with that aggregation
- Column appears in GROUP BY AND aggregate → **DIMENSION** (grouping takes precedence)
- DATE/TIMESTAMP type used in filters → **DIMENSION** (time grain)

---

## 7. Unused Columns

Columns defined in the SV but with zero access in the last 30 days.

| # | Column | Table | SV Role | Recommendation |
|---|--------|-------|---------|----------------|
| 1 | <COL> | <TABLE> | <ROLE> | REVIEW / KEEP |
...

Recommendation logic:
- **REVIEW** — zero direct access AND not part of a relationship key. Operator decides; access via
  the semantic view or Cortex Analyst may not show up in ACCESS_HISTORY for base tables.
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

Recommend **ADD RELATIONSHIP** only when the referenced (`To`) side has a declared PRIMARY KEY or
UNIQUE constraint in the SV, or the Phase 10 cardinality check shows the `To` column is unique.
Otherwise mark **REVIEW — referenced side not proven unique**. A non-unique referenced side is a
direct many-to-many relationship (Preview, 2026-11-13): valid only if intended, and queries that
traverse it cannot use LOD or `USING` metrics. Prefer a bridge table unless the owner confirms.

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

## 9b. Materialization Opportunities

**Only include this section if `AGGREGATE_COLUMNS` contains high-frequency patterns AND at least one
SV source table is large (> 100M rows or > 10GB in `SV_TABLE_SIZES`).**

> **Scope note:** Materializations (Preview) benefit queries executed as Semantic SQL. Queries from
> Cortex Analyst, Cortex Agents and Snowflake CoWork that run physical SQL against the underlying
> tables do not benefit. Only recommend if the user has Semantic SQL consumers.

Identify the strongest materialization candidate from the audit findings:

| Signal | Evidence from Audit | Weight |
|---|---|---|
| Large source table | `> 100M rows` in table size data | HIGH |
| Additive metrics queried repeatedly | Same SUM/COUNT/MIN/MAX expressions in `AGGREGATE_COLUMNS` | HIGH |
| Same dimension group in many queries | Same column set in `GROUPBY_COLUMNS` across multiple queries | HIGH |
| Non-additive metrics dominate | AVG, COUNT DISTINCT in `AGGREGATE_COLUMNS` | LOW |

**If HIGH signals present, emit:**

```
## 9b. Materialization Opportunities

The following pattern appears in <N> queries and could benefit from a materialization:

  Suggested grain:    <top GROUPBY_COLUMNS> 
  Suggested metrics:  <top additive AGGREGATE_COLUMNS>
  Largest table:      <TABLE> (<N>M rows, <N>GB)

  Prerequisite: Only useful if consumers query via SEMANTIC_VIEW() or direct SQL against
  the SV. Cortex Analyst queries are not accelerated by materializations.

  → Route to sv-materialize for full eligibility assessment and DDL generation
```

This section is **informational only** — audit does not create or modify materializations. Hand
off to `sv-materialize` for eligibility classification, design, and creation.

---

## 10. Metadata Quality

**Only include this section if `METADATA_QUALITY_FINDINGS` contains issues.**

| Issue | Severity | Count | Detail |
|---|---|---|---|
| AI\_SQL\_GENERATION missing | HIGH | — | No `CUSTOM_INSTRUCTIONS` row with `property='AI_SQL_GENERATION'` in DESCRIBE output |
| Tables missing COMMENT | MEDIUM/HIGH | `<N>` | `<list of table names>` |
| Columns missing COMMENT | MEDIUM | `<N>` | >30% of facts/dims/metrics uncovered |
| VARCHAR dims missing SAMPLE\_VALUES | MEDIUM | `<N>` | Requires DDL inspection: `GET_DDL('SEMANTIC VIEW', ...)` |

**AI\_SQL\_GENERATION fix:** Add to the candidate DDL with guidance on: which date column to use, gross vs net revenue distinction, filters to always/never apply, column disambiguation rules. For YAML models: use `module_custom_instructions.sql_generation` (modern) or `custom_instructions` (legacy).

**COMMENT fix:** Add COMMENT to every table and key column. Prioritize tables first, then facts/metrics, then dimensions.

**SAMPLE\_VALUES fix:** Retrieve the full DDL with `SELECT GET_DDL('SEMANTIC VIEW', '<DB>.<SCHEMA>.<SV_NAME>')` or the YAML with `SELECT SYSTEM$READ_YAML_FROM_SEMANTIC_VIEW(...)`. For each VARCHAR dimension with enumerated values (status codes, region codes, categories), add `SAMPLE_VALUES ('val1', 'val2', 'val3') IS_ENUM` to the dimension in the DDL.

---

## 11. Size Assessment

| Metric | Current | After Changes |
|--------|---------|---------------|
| Tables | <N> | <N + additions - removals> |
| Columns | <N> | <N + additions - removals> |
| Relationships | <N> | <N + additions> |
| VQRs | <N> | — |
| Coverage | <X>% | <Y>% |

**Sizing:** Do not recommend a split from column, table, fact-table or VQR counts. Apply the
single sizing policy in `../../sv-discovery/phases/03_analyze.md` Step 3B (prefer the fewest SVs;
split only for excessive estimated context size, unresolved relationship ambiguity or genuinely
independent workloads). If the changes would push the SV toward the ~100,000-token guideline, note
it and point to that step; label any accuracy benefit of splitting as an assumption.

---

## Step 12B: Priority ranking

Order all recommendations by impact, highest first:

```
Priority Ranking
════════════════

 PRIORITY 0 — Join Type Mismatches  [BLOCKING]
   Relationship join columns with incompatible types.
   → See Section 0

 PRIORITY 1 — Structural Topology  [HIGH/MEDIUM]
   Multi-path table pairs without USING; orphan tables whose fields cannot be combined.
   → See Section 1

 PRIORITY 2 — Source Object Accessibility  [CRITICAL — SV silently breaks]
   If the current role cannot SELECT from an underlying table, the SV fails
   at query time even though DESCRIBE SEMANTIC VIEW succeeds.
   → See Section 2

 PRIORITY 3 — VQR Health  [CRITICAL/HIGH — eval ground truth cannot be matched]
   CA extension column-drop, physical FQN refs, unknown columns, aggregation mismatches,
   uncovered metrics.
   → See Section 3

 PRIORITY 4 — Metric Integrity  [HIGH — silent wrong results]
   Semi-additive SUM metrics on snapshot data inflate numbers across time.
   FILTER facts on non-boolean expressions produce runtime errors.
   PK declared on a non-unique column makes a relationship's cardinality wrong.
   → See Section 4

 PRIORITY 5 — Missing Tables (ADD-classified)  [HIGH — users bypass the SV]
   Tables frequently joined by users but invisible to the SV.
   → See Section 5

 PRIORITY 5b — Subquery Filter Candidates  [MEDIUM — Analyst gap, not a hard failure]
   Tables used only via WHERE subquery filtering in user queries.
   No SV change needed for programmatic use; add as relationship only if Analyst access desired.
   → See Section 5b

 PRIORITY 6 — Relationship Gaps  [HIGH — Analyst cannot auto-join]
   JOIN patterns from user queries that have no SV RELATIONSHIP defined.
   → See Section 8

 PRIORITY 7 — Missing Columns (high access count)  [MEDIUM]
   Frequently accessed columns not in the SV.
   → See Section 6

 PRIORITY 8 — Metadata Quality  [MEDIUM — degrades question matching]
   Missing AI_SQL_GENERATION, COMMENTs, SAMPLE_VALUES.
   → See Section 10

 PRIORITY 9 — Metric Opportunities  [MEDIUM]
   Common aggregations that could be defined as SV metrics.
   → See Section 9

 PRIORITY 9b — Materialization Opportunities  [MEDIUM — Semantic SQL consumers only]
   Repeated additive-metric query patterns on large tables.
   Does NOT help Cortex Analyst queries.
   → See Section 9b; route to sv-materialize for implementation

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
     → sv-ddl builds a candidate copy <SV>__CAND__<run> with these changes;
        production is untouched until you accept it at SV-PROMOTE

   B) Apply selected recommendations
      → Tell me which items to include/exclude by section number
         (e.g., "Apply all except Section 5 item #3 and Section 7 item #1")

  C) Export report only
     → I'll save this audit report for offline review
        (no changes to the semantic view)

  D) Cancel
     → End audit with no changes
```

**GATE (INTERACTIVE (default)): Do NOT proceed with any DDL changes until the user explicitly selects A or B.**

**AUTONOMOUS mode:** never select Option A. Select **Option C (Export report)**. If the report
contains additive, deterministic items (relationship additions whose referenced side is proven
unique, column additions, missing COMMENTs), you may also take **Option B restricted to those
items**, which builds a candidate copy only. Never include REVIEW items, removals,
relationship-type changes or metric restructuring. The run then stops at `SV-PROMOTE`, which is
OPERATOR_REQUIRED in both modes.

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
To apply these changes, invoke $sv-ddl with:

  Source semantic view: <SV_FQN>
  Target: candidate copy (candidate.py name --kind cand) built from GET_DDL
  Modifications:
    <list of approved changes as natural language instructions>
  End state: evaluate the candidate, then gate SV-PROMOTE

sv-ddl deploys only the candidate. Production changes happen only at SV-PROMOTE.
```

Do NOT generate the DDL directly in this phase — hand off to `$sv-ddl`, which has the full DDL
generation, validation and self-check pipeline. The candidate workflow, promotion options and
cleanup are defined in `../../../references/candidate-promotion.md`.

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
    → Invoke $sv-ddl to build a candidate with the approved improvements, then SV-PROMOTE
    → Re-run $sv-audit in 30 days to measure improvement
```

---

## Output variables

| Variable | Contents |
|----------|----------|
| `AUDIT_REPORT` | Full markdown audit report |
| `APPROVED_CHANGES` | List of user-approved modifications (empty if cancelled/export only) |
| `HANDOFF_INSTRUCTIONS` | Natural language modification instructions for $sv-ddl (candidate copy) |
