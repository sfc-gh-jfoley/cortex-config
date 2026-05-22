# Impact Analysis — Cross-Reference Changes vs Pipelines

## Overview

This reference describes how to assess the impact of Snowflake behavior changes against a customer's pipeline inventory. The goal is to produce a severity-scored report identifying which pipelines are at risk.

## Input Requirements

- **Behavior changes list** from Phase 1 (scrape workflow)
- **Pipeline inventory** from Phase 2 (discovery queries)

## Analysis Strategy

### Layer 1 — Keyword Matching

For each behavior change, extract key terms (function names, SQL keywords, feature names, parameter names) and search for them in pipeline object definitions.

**Where to search:**

| Object Type | How to Get Definition |
|------------|----------------------|
| Tasks | `SELECT GET_DDL('TASK', '<name>')` or `DESCRIBE TASK <name>` |
| Stored Procedures | `SELECT GET_DDL('PROCEDURE', '<name>(arg_types)')` |
| User Functions | `SELECT GET_DDL('FUNCTION', '<name>(arg_types)')` |
| Views | `SELECT GET_DDL('VIEW', '<name>')` |
| Dynamic Tables | `SELECT GET_DDL('DYNAMIC_TABLE', '<name>')` |

For large inventories, batch these queries and search the results.

**Example keyword extraction:**

If a behavior change says: "The `FLATTEN` function now returns NULL instead of empty array for NULL input"

Keywords to search: `FLATTEN`, `NULL`, `LATERAL FLATTEN`

### Layer 2 — Feature Area Matching

Map behavior change categories to pipeline object types:

| Change Category | Likely Affected Objects |
|----------------|----------------------|
| SQL Functions | Procedures, UDFs, Views, Dynamic Tables, Tasks with SQL |
| Data Loading | Pipes, COPY INTO statements, Stages |
| Security / RBAC | Role grants, Row Access Policies, Masking Policies |
| Data Types | All objects using the affected type |
| Streams | Stream consumers (Tasks reading from streams) |
| Replication | Failover groups, Database replication configs |
| Connectors / Drivers | External applications (not directly visible in Snowflake) |
| Warehouses | Warehouse configs, Resource Monitors |

### Layer 3 — Query History Pattern Analysis

Search recent query history for patterns that match the behavior change:

```sql
SELECT QUERY_TEXT, QUERY_TYPE, DATABASE_NAME, SCHEMA_NAME, USER_NAME,
       COUNT(*) as execution_count
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE START_TIME > DATEADD('day', -30, CURRENT_TIMESTAMP())
  AND QUERY_TEXT ILIKE '%<keyword>%'
GROUP BY 1, 2, 3, 4, 5
ORDER BY execution_count DESC
LIMIT 50;
```

This catches ad-hoc queries and patterns not captured in stored object definitions.

### Layer 4 — AI-Assisted Classification (Optional)

For ambiguous matches, use Cortex AI to classify:

```sql
SELECT SNOWFLAKE.CORTEX.AI_COMPLETE(
  'llama3.1-70b',
  CONCAT(
    'Given this Snowflake behavior change: "', :change_description, '"\n',
    'And this SQL code: "', :sql_code, '"\n',
    'Is this code affected by the behavior change? Answer CRITICAL, WARNING, or NOT_AFFECTED with a brief explanation.'
  )
);
```

Use this sparingly — only for matches where keyword search found a hit but severity is unclear.

## Severity Scoring Rules

### CRITICAL — Assign when:
- Exact function/syntax match found in object definitions
- The change modifies return values or error behavior for a function actively used
- The change affects data types used in table columns that feed pipelines
- The change removes or renames a parameter the customer is using

### WARNING — Assign when:
- Feature area match but no exact keyword match
- Query history shows usage of the affected feature but not the specific pattern
- The change is in a category the customer uses heavily but the specific impact is unclear
- The change affects a driver or connector version (can't verify from SQL alone)

### NOT_AFFECTED / INFO — Assign when:
- No keyword matches in any object definitions or query history
- The change is in a feature area the customer does not use
- The change only affects new objects created after a certain date

## Output Format

Produce an impact matrix:

```markdown
| # | Bundle | Change | Severity | Affected Objects | Evidence |
|---|--------|--------|----------|-----------------|----------|
| 1 | 2026_03 | FLATTEN NULL handling | CRITICAL | PROD.ETL.PARSE_JSON_PROC, PROD.ETL.FLATTEN_EVENTS_TASK | GET_DDL shows LATERAL FLATTEN on nullable column |
| 2 | 2026_03 | COPY INTO error_on_column_count_mismatch default | WARNING | PROD.INGEST.* (3 pipes) | Pipes use COPY INTO but ON_ERROR not explicitly set |
| 3 | 2026_03 | New SHOW GRANTS output columns | INFO | None detected | No SHOW GRANTS in stored objects |
```

## Edge Cases

- **Encrypted/obfuscated procedures**: If `GET_DDL` returns obfuscated code, note this and flag the object as "unable to analyze — manual review required"
- **External code**: Changes to drivers, connectors, or client libraries can't be detected from Snowflake queries. Note any driver-related changes and recommend the customer check their application code.
- **Cross-account references**: If pipelines reference objects in other accounts (via shares, listings), note that impact on shared objects requires analysis in the provider account.
