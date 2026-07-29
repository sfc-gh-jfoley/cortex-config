---
document_type: expansion-manifest
document_id: 01-sv-ddl-expansion
created: 2026-07-10
track: "Track 1 — Semantic View DDL"
scope: three-ga-features
---

# Track 1 Manifest: Semantic View DDL Expansion

**Purpose**: Document the integration of three Jun 25–26 GA DDL features into the sv-ddl plugin. These features enable SQL queries as logical tables, top-level VARIABLES clauses, and sample value/enum indicators for dimensions. This is a scope document, not an implementation.

---

## Feature Summary

### Feature 1: SQL Queries as Logical Tables

**Announcement**: Jun 25 GA — `logicalTable` now accepts a SQL query instead of just FQN references.

**Current ddl_syntax.md (lines 28–48)**:
- Defines `logicalTable` as `[ <table_alias> AS ] <database>.<schema>.<table_or_view_name> ...`
- Supported sources: "Standard tables, Views (including secure views), Dynamic tables, Materialized views"
- No mention of SQL queries

**Expansion needed**:
1. Update `logicalTable` grammar to:
   ```sql
   [ <table_alias> AS ] ( <database>.<schema>.<table_or_view_name> | SQL ( <sql_query> ) )
     [ PRIMARY KEY (...) ]
     [ UNIQUE (...) ] [ ... ]
     ...
   ```
2. Add new subsection "SQL Query Logical Tables" with:
   - When to use: "Use SQL queries to create virtual tables from aggregations, CTEs, or cross-schema unions"
   - Limitations: "SQL query results are materialized on CREATE SEMANTIC VIEW; the query is not re-executed per request. For dynamic results, use a materialized view instead."
   - Best-practice example: aggregation → SUM by REGION
   - Anti-pattern: "SQL query with `UNION ALL` of 10+ tables → creates very large materialization"

3. **Breaking change in sv-ddl/phases/02_profile_describe.md (Phase 2)**:
   - Currently: "Profiling is done via `INFORMATION_SCHEMA.COLUMNS` query against the source table/view."
   - Problem: SQL queries don't have INFORMATION_SCHEMA entries; query can't be profiled before execution
   - Fix: Add source-type detection branch:
     ```
     FOR each logicalTable:
       IF source is FQN:
         profile via INFORMATION_SCHEMA.COLUMNS
       ELSE IF source is SQL query:
         execute query (time-limited) → derive column list dynamically
       ENDIF
     ```
   - Documentation: "For SQL queries, profiling executes the query to sample columns. Set a timeout (30s default) to avoid long-running profilers."

### Feature 2: Top-Level VARIABLES Clause

**Announcement**: Jun 25 GA — New `VARIABLES` block at semantic view top level for parameterized queries.

**Current ddl_syntax.md**: No mention of VARIABLES clause

**Expansion needed**:
1. Add `VARIABLES` to top-level template (after TABLES, before RELATIONSHIPS per DDL order):
   ```sql
   CREATE [ OR REPLACE ] SEMANTIC VIEW [ IF NOT EXISTS ] <db>.<schema>.<name>
     TABLES ( logicalTable [ , ... ] )
     [ VARIABLES ( variableDefinition [ , ... ] ) ]    ← NEW
     [ RELATIONSHIPS (...) ]
     ...
   ```

2. Add `variableDefinition` grammar:
   ```sql
   <var_name> AS <sql_type> = <default_value>
     [ COMMENT = '<description>' ]
   ```
   - Example: `$region_filter AS VARCHAR = 'US_EAST'`
   - Variables are referenced in fact/dimension/metric expressions as `$var_name`

3. Add new subsection "Variables in Expressions" with:
   - Use case: "Parameterize metrics for regional/temporal filtering without creating multiple SVs"
   - Example: A metric like `SUM(amount) WHERE region = $region_filter`
   - Limitation: "Variables are substituted at query-time; they cannot be used in relationship join conditions"
   - Best-practice: "Use variables for WHERE filters and aggregations only"

4. **Breaking change in sv-ddl/phases/03_classify.md (Phase 3 — Classify)**:
   - Currently: "Phase 3 classifies columns as FACT / DIMENSION / METRIC based on type and usage"
   - New step: Before classifying, resolve any `$variable` references in fact/dimension/metric expressions
   - Documentation: "If an expression uses `$var_name`, ensure that variable is defined in the VARIABLES block. Undefined variables will produce a 'Variable not found' error at CREATE time."

### Feature 3: Sample Values + Enum Indicators

**Announcement**: Jun 26 GA — `dimensionExpression` can now include SAMPLE_VALUES and ENUM markers for AI guidance.

**Current ddl_syntax.md (lines 87–97)**:
- Defines `dimensionExpression` with optional `LABELS = ( FILTER )` and COMMENT
- No mention of sample values or enum indicators

**Expansion needed**:
1. Extend `dimensionExpression` grammar:
   ```sql
   [ PUBLIC ] <table_alias>.<dim_name>
     [ LABELS = ( FILTER ) ]
     AS <sql_expr>
     [ WITH SYNONYMS [ = ] ( '<synonym>' [ , ... ] ) ]
     [ WITH SAMPLE_VALUES ( '<value>' [ , ... ] ) ]     ← NEW
     [ WITH ENUM_INDICATOR ]                             ← NEW
     [ [ WITH ] TAG (...) ]
     [ COMMENT = '<description>' ]
   ```

2. Add new subsection "Sample Values and Enum Indicators" with:
   - **SAMPLE_VALUES**: "Provide 3–5 representative values for the dimension to guide AI generation. Example: `WITH SAMPLE_VALUES ( 'US_EAST', 'US_WEST', 'EU' )`"
   - **ENUM_INDICATOR**: "Mark a dimension as an enumeration (finite, known set of values). AI will prefer IN lists over LIKE patterns. Example: status dimension with values {ACTIVE, PENDING, INACTIVE}"
   - Use case: "Improves natural language question matching — AI understands that 'all regions' queries should map to IN ('US_EAST', 'US_WEST', ...) not LIKE '%REGION%'"
   - Best-practice example: region dimension with ENUM_INDICATOR + sample values {US_EAST, US_WEST, EU_WEST, APAC}

3. **Addition to sv-ddl/phases/05_generate_ddl.md (Phase 5 — Generate DDL)**:
   - New self-check rules (24–26):
     - Rule 24: "SAMPLE_VALUES must contain only valid SQL string literals (quoted)"
     - Rule 25: "If ENUM_INDICATOR is used, SAMPLE_VALUES should be provided (warning, not error)"
     - Rule 26: "Dimension with SAMPLE_VALUES but no ENUM_INDICATOR is valid but redundant — consider adding ENUM_INDICATOR if values are finite"

---

## Files Modified

| File | Change Type | Scope |
|------|-------------|-------|
| `plugins/semantic-view-toolkit/skills/sv-ddl/reference/ddl_syntax.md` | UPDATE | Add SQL query grammar + VARIABLES + sample values; 3 new subsections; expand example |
| `plugins/semantic-view-toolkit/skills/sv-ddl/phases/02_profile_describe.md` | UPDATE | Add source-type detection branch for SQL query profiling |
| `plugins/semantic-view-toolkit/skills/sv-ddl/phases/03_classify.md` | UPDATE | Add variable resolution step before classification |
| `plugins/semantic-view-toolkit/skills/sv-ddl/phases/05_generate_ddl.md` | UPDATE | Add self-check rules 24–26 for sample values + enum indicators |
| `plugins/semantic-view-toolkit/SKILL.md` | UPDATE | Add notes in Phase 2 section: "SQL logical tables require dynamic column profiling; see phases/02_profile_describe.md for flow" |
| (cross-track) `plugins/ops-monitor/skills/artifact-drift-monitor/SKILL.md` | UPDATE | Phase 2 note: "SQL logical tables are not visible in INFORMATION_SCHEMA; use fallback scan method (see sv-ddl expansion manifest)" |

---

## Breaking Changes and Mitigation

### Break 1: Phase 2 Profiling Fails on SQL Logical Tables

**What breaks**: Users creating an SV with a SQL logical table will hit "Column profiling failed: INFORMATION_SCHEMA query returned no results" when Phase 2 tries to profile columns.

**Why**: Current Phase 2 assumes all sources are FQN-addressable in INFORMATION_SCHEMA. SQL query results are ephemeral.

**Mitigation in manifest scope**:
1. Update Phase 2 to detect source type (is it `SQL(...)` syntax?)
2. For SQL sources, execute the query (with 30s timeout) to sample column names
3. Document the timeout behavior: "Long-running queries may cause profiling to fail; optimize or switch to a materialized view"

**Implementation detail** (for integration step, not manifest):
- In Phase 2 code, add `IF source_contains('SQL(') THEN execute_for_column_list ELSE INFORMATION_SCHEMA lookup ENDIF`

---

### Break 2: artifact-drift-monitor Phase 2 Queries INFORMATION_SCHEMA

**What breaks**: The `artifact-drift-monitor` skill in `ops-monitor` plugin uses Phase 2 to scan tables for drift. If a table is defined with `SQL(...)` logical table, the INFORMATION_SCHEMA query fails.

**Why**: artifact-drift-monitor runs table scans against `INFORMATION_SCHEMA.TABLES` to find all semantic views; it does not handle SQL query sources.

**Mitigation in manifest scope**:
1. Add a note in artifact-drift-monitor's Phase 2: "SQL logical tables are not visible in INFORMATION_SCHEMA; use fallback scan method."
2. The fallback: Query `SHOW SEMANTIC VIEWS` and parse the `logicalTable` definitions (slower, but handles SQL sources)
3. Cross-reference in sv-ddl expansion manifest: "See ops-monitor/artifact-drift-monitor for fallback details"

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|-----------|
| SQL query profiling timeout on large queries | MEDIUM | Set default 30s timeout; document in Phase 2; user can manually set timeout |
| Variables in expressions cause undefined variable errors | LOW | Phase 3 validation checks for undefined $var_name; user gets clear error message |
| artifact-drift-monitor silently skips SQL tables | MEDIUM | Add fallback scan method in artifact-drift-monitor; cross-document in both manifests |
| Sample values with incorrect SQL string formatting | LOW | Phase 5 self-check rule 24 validates quoted strings |

---

## Verification Checklist

- ✅ All three features (SQL queries, VARIABLES, sample values) have grammar sections in ddl_syntax.md
- ✅ Breaking changes in Phase 2 (profiling) and artifact-drift-monitor are documented with mitigation
- ✅ Phase 3 and Phase 5 updates are listed with specific rule numbers
- ✅ Cross-reference to ops-monitor/artifact-drift-monitor is bidirectional (listed in "Files Modified" and noted in mitigation)
- ✅ No file is proposed for deletion or renaming
- ✅ Example SQL is syntactically valid (or clearly marked as pseudo-code)

---

## Integration Sequencing

Track 1 has no dependencies on other tracks and can be implemented in parallel with Track 2a. After T1 + T2a complete, proceed to T2b.

Once all three manifests (T0, T1, T2) are written and verified, main agent performs the batch skill-loader update in Phase V.
