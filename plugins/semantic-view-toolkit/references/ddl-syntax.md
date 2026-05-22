# DDL Syntax Reference

Complete semantic view DDL grammar reference for Snowflake.

## CREATE OR REPLACE SEMANTIC VIEW

```sql
CREATE OR REPLACE SEMANTIC VIEW <database>.<schema>.<name>
  [ COMMENT = '<comment>' ]
  TABLES (
    <table_ref> [ AS <alias> ] [, ...]
  )
  [ RELATIONSHIPS (
    <relationship_def> [, ...]
  ) ]
  [ FACTS (
    <table_or_alias> (
      <column_def> [, ...]
    ) [, ...]
  ) ]
  [ DIMENSIONS (
    <table_or_alias> (
      <column_def> [, ...]
    ) [, ...]
  ) ]
  [ METRICS (
    <metric_def> [, ...]
  ) ]
  [ VERIFIED_QUERIES (
    <vqr_def> [, ...]
  ) ]
;
```

## ALTER SEMANTIC VIEW

```sql
-- Add/modify columns, relationships, metrics
ALTER SEMANTIC VIEW <name> {
  ADD | DROP | MODIFY
} { TABLE | RELATIONSHIP | FACT | DIMENSION | METRIC | VERIFIED_QUERY } ...;

-- Rename
ALTER SEMANTIC VIEW <name> RENAME TO <new_name>;

-- Set comment
ALTER SEMANTIC VIEW <name> SET COMMENT = '<comment>';
```

## Clause Order (MANDATORY)

Clauses must appear in this exact order:

1. `TABLES` — source table references
2. `RELATIONSHIPS` — join definitions between tables
3. `FACTS` — numeric/measure columns
4. `DIMENSIONS` — categorical/grouping columns
5. `METRICS` — calculated aggregate expressions
6. `VERIFIED_QUERIES` — example question/SQL pairs (VQRs)

**Violation:** Placing FACTS before RELATIONSHIPS or METRICS before DIMENSIONS will produce a syntax error.

## Table Reference

```sql
TABLES (
    DB.SCHEMA.TABLE_NAME AS alias,
    DB.SCHEMA.OTHER_TABLE AS other_alias
)
```

- Fully qualified names recommended
- Aliases required when table names conflict
- Supports: base tables, views, dynamic tables, materialized views, external tables

## Relationship Definition

```sql
RELATIONSHIPS (
    alias_a REFERENCES alias_b (col_a, col_b)
      [ JOIN TYPE = { 'INNER' | 'LEFT OUTER' | 'RIGHT OUTER' | 'FULL OUTER' } ]
      [ RELATIONSHIP TYPE = { 'one_to_one' | 'one_to_many' | 'many_to_one' | 'many_to_many' } ]
)
```

**Rules:**
- `REFERENCES` requires the target table to have a PK or UNIQUE constraint on the referenced column(s)
- If no constraint exists, the relationship will still compile but may produce warnings
- Multiple relationship paths between the same tables need `USING` clause in metrics/facts to disambiguate

## Column Definition (Facts & Dimensions)

```sql
<column_name>
  [ DATA TYPE <type> ]
  [ KIND { 'dimension' | 'time_dimension' | 'fact' | 'measure' } ]
  [ DESCRIPTION '<text>' ]
  [ SYNONYMS ( '<syn1>', '<syn2>', ... ) ]
  [ EXPR '<sql_expression>' ]
  [ FILTERS (
    <filter_name> ( DESCRIPTION '<text>', EXPR '<sql_expression>' ) [, ...]
  ) ]
```

**Direct column alias rule:** When referencing a physical column directly (no EXPR), the column name in the semantic view MUST match the physical column name. Use SYNONYMS for alternate names.

**Duplicate columns across tables:** If two source tables have columns with the same name, you must either:
- Use table alias prefix: `orders.STATUS` vs `returns.STATUS`
- Or include only one and omit the other

## Metric Definition

```sql
<metric_name>
  EXPR '<aggregate_expression>'
  [ DEFAULT_AGGREGATION { SUM | AVG | COUNT | COUNT_DISTINCT | MIN | MAX } ]
  [ DESCRIPTION '<text>' ]
  [ SYNONYMS ( '<syn1>', '<syn2>', ... ) ]
  [ USING <relationship_name> ]
```

**USING clause:** Required when multiple join paths exist between tables referenced in the metric expression. Specifies which relationship to traverse.

## Verified Query Representation (VQR)

```sql
VERIFIED_QUERIES (
    '<question_text>'
    VERIFIED_QUERY '<sql_text>'
    [ VERIFIED_AT '<timestamp>' ]
    [ VERIFIED_BY '<user>' ]
)
```

**Rules:**
- Question should be natural language a user would actually ask
- SQL must be valid and return correct results against the semantic view's source tables
- Single quotes in SQL must be escaped (double single quotes)

## Self-Check Rules

### Syntax Rules (18)

| # | Rule | Error if Violated |
|---|------|-------------------|
| 1 | Clause order: TABLES → RELATIONSHIPS → FACTS → DIMENSIONS → METRICS → VERIFIED_QUERIES | Syntax error |
| 2 | All table references must exist in TABLES clause | Unknown table reference |
| 3 | Column names in FACTS/DIMENSIONS must exist in source table | Unknown column |
| 4 | REFERENCES target must have PK/UNIQUE (warning if missing) | Relationship warning |
| 5 | No duplicate column names within same section without table prefix | Ambiguous column |
| 6 | EXPR must be valid SQL expression | Expression error |
| 7 | DEFAULT_AGGREGATION must be valid function | Invalid aggregation |
| 8 | SYNONYMS must be string literals | Type error |
| 9 | Direct column alias must match physical name | Alias mismatch |
| 10 | Table aliases must be unique | Duplicate alias |
| 11 | Relationship tables must reference TABLES clause aliases | Unknown alias |
| 12 | Metric EXPR must reference columns from declared tables | Unknown column in metric |
| 13 | USING clause must reference a declared relationship | Unknown relationship |
| 14 | VQR SQL must be parseable | SQL parse error |
| 15 | FILTERS EXPR must reference columns from same table | Cross-table filter |
| 16 | KIND value must be one of allowed values | Invalid kind |
| 17 | COMMENT must be string literal | Type error |
| 18 | Semicolon required at end | Missing terminator |

### Semantic Rules (5)

| # | Rule | Impact |
|---|------|--------|
| 1 | Every table should have at least one column in FACTS or DIMENSIONS | Unused table warning |
| 2 | Every relationship should connect tables that share columns | Orphan relationship |
| 3 | Metrics should reference columns from at least one table | Detached metric |
| 4 | VQR SQL should reference only tables in TABLES clause | External reference |
| 5 | time_dimension columns should have DATE/TIMESTAMP type | Type mismatch |

## Common Error Messages and Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `Semantic view compilation error: unknown table` | Table not in TABLES clause | Add table to TABLES |
| `Column 'X' not found in table 'Y'` | Typo or wrong table reference | Check column spelling, verify table |
| `Ambiguous column reference` | Same column name in multiple tables | Add table alias prefix |
| `Invalid relationship: target has no unique constraint` | REFERENCES target lacks PK/UNIQUE | Add constraint or ignore warning |
| `Duplicate synonym` | Same synonym on multiple columns | Remove duplicate, keep on most relevant |
| `Expression error in metric` | Invalid SQL in EXPR | Fix SQL expression syntax |
| `Multiple paths between tables` | Two relationships connect same pair | Add USING clause to metrics |
