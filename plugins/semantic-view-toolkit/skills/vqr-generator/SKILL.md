---
name: vqr-generator
description: >
  Auto-generate verified query (VQR) candidates for a semantic view from query history
  patterns. Validates candidates execute correctly against source tables before adding.
  Use when your SV has few or no VQRs and you need them for evaluation.
triggers:
  - generate VQRs
  - verified queries
  - need more examples
  - grow eval set
  - generate questions
  - bootstrap VQRs
  - I have no verified queries
  - add VQRs to my SV
---

# VQR Generator Skill

## When to Use

Use this skill when:
- Your SV has 0 VQRs and you need them to run evaluations
- You want to grow your VQR set for better eval coverage
- You want data-driven question suggestions based on actual user behavior
- You're bootstrapping a new SV and need initial example queries

**VQRs are the foundation of SV evaluation and optimization.** Without them, sv-evaluation and sv-optimization cannot run.

---

## Workflow

```
Phase 1: Connect & Analyze SV      → get SV structure, existing VQRs, source tables
    ↓
Phase 2: Mine Query History         → find real questions users have asked
    ↓
Phase 3: Synthesize Candidates      → generate question + SQL pairs
    ↓
Phase 4: Validate                   → execute each candidate SQL, verify it works
    ↓ [STOP: user approves candidates]
Phase 5: Apply                      → ALTER SEMANTIC VIEW to add VQRs
```

---

## Phase 1: Connect & Analyze SV

### 1.1 Get SV FQN and describe it

```sql
DESCRIBE SEMANTIC VIEW <SV_FQN>;
```

Extract:
- Tables and their columns
- Existing VQRs (if any)
- Metrics defined (these suggest natural questions)
- Dimensions defined (these suggest filter/grouping patterns)
- Relationships (these suggest cross-table questions)

### 1.2 Assess gaps

```
Current state:
  Tables: N
  Metrics: M
  Dimensions: D
  Existing VQRs: V
  
  Recommended VQR count: 10-20 (based on SV complexity)
  Gap: need ~X more VQRs
```

---

## Phase 2: Mine Query History

### 2.1 Find queries referencing SV tables

```sql
SELECT
    ah.QUERY_ID,
    qh.QUERY_TEXT,
    qh.USER_NAME,
    qh.START_TIME
FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah,
    LATERAL FLATTEN(input => ah.BASE_OBJECTS_ACCESSED) obj
JOIN SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY qh
    ON ah.QUERY_ID = qh.QUERY_ID
WHERE ah.QUERY_START_TIME >= DATEADD('day', -90, CURRENT_TIMESTAMP())
    AND obj.value:objectName::STRING IN (<SV_TABLE_FQNS>)
    AND qh.QUERY_TYPE = 'SELECT'
    AND qh.EXECUTION_STATUS = 'SUCCESS'
ORDER BY qh.START_TIME DESC
LIMIT 500;
```

### 2.2 Extract patterns

From the query set, identify:
- **Common aggregations**: GROUP BY patterns, SUM/AVG/COUNT usage
- **Common filters**: WHERE clause patterns (date ranges, status values)
- **Common joins**: which tables are joined and how
- **Top N patterns**: ORDER BY ... LIMIT queries
- **Trend patterns**: date-based grouping (by month, by quarter)

### 2.3 Cluster into question types

| Pattern Type | Example Question | Coverage |
|---|---|---|
| Simple aggregation | "What's the total revenue?" | Metrics |
| Filtered aggregation | "Revenue in California last month?" | Metrics + Dimensions |
| Top-N ranking | "Top 10 customers by revenue?" | Metrics + Dimensions |
| Trend over time | "Monthly revenue trend for 2024?" | Metrics + Time Dimensions |
| Cross-table | "Revenue by product category?" | Relationships |
| Comparison | "Revenue this quarter vs last?" | Time Dimensions |

---

## Phase 3: Synthesize Candidates

For each pattern type, generate 2-3 VQR candidates:

### VQR Format

```sql
-- VQR must use LOGICAL column names from the SV, not physical names
-- Use table aliases as defined in the SV TABLES clause (e.g., orders, not __orders)
SELECT SUM(revenue) AS total_revenue
FROM orders
WHERE order_date >= '2024-01-01' AND order_date < '2025-01-01';
```

### Generation rules

1. **Use logical names**: Column names as defined in the SV (the `AS` alias), not physical column names
2. **Use SV table aliases**: Use the logical table alias directly as defined in the SV TABLES clause (e.g., `FROM orders`, not `FROM __orders`). Do not add any prefix to table names.
3. **Use absolute dates**: Never `CURRENT_DATE` or relative dates — always fixed dates for reproducibility
4. **Target specific capabilities**: Each VQR should test a different SV feature (metric, dimension, relationship, filter)
5. **Keep SQL simple**: 1-3 lines. VQRs are teaching examples, not complex analytics.
6. **Match SV metrics**: If the SV defines `total_revenue = SUM(amount)`, use `total_revenue` in the VQR, not `SUM(amount)`

### Present candidates

```
| # | Question | SQL | Tests |
|---|----------|-----|-------|
| 1 | "What was total revenue in Q1 2024?" | SELECT SUM(revenue)... | Metric: total_revenue |
| 2 | "Top 5 customers by order count?" | SELECT customer_name... | Dim + Metric + TopN |
| 3 | "Monthly revenue trend for 2024?" | SELECT DATE_TRUNC... | Time grouping |
| ... | ... | ... | ... |
```

---

## Phase 4: Validate

For each candidate, execute the SQL to verify:

```sql
-- Translate logical names to physical for validation
-- (The SV handles this at runtime, but we validate manually)
<translated SQL using physical table/column names>
```

Check:
- ✓ Query executes without error
- ✓ Returns non-empty results
- ✓ Results are reasonable (not NULL, not obviously wrong)
- ✓ Uses correct logical column names from SV definition

Mark each candidate: VALID / INVALID / NEEDS_FIX

**STOP Gate**: Present validated candidates for user approval.

---

## Phase 5: Apply

For approved candidates, add VQRs to the SV:

```sql
-- ALTER SEMANTIC VIEW ... ADD VERIFIED QUERY is not supported — returns syntax error.
-- The only working path is CREATE OR REPLACE with the full DDL + new VQRs appended.

-- Step 1: Get current DDL
DESCRIBE SEMANTIC VIEW <SV_FQN>;
-- Copy the DDL from the DESCRIBE output (or use the file saved during sv-ddl Phase 7)

-- Step 2: Add new VQRs to the AI_VERIFIED_QUERIES block and rebuild:
CREATE OR REPLACE SEMANTIC VIEW <SV_FQN>
  TABLES ( ... )          -- unchanged from current DDL
  RELATIONSHIPS ( ... )   -- unchanged
  FACTS ( ... )           -- unchanged
  DIMENSIONS ( ... )      -- unchanged
  METRICS ( ... )         -- unchanged
  COMMENT = '...'         -- unchanged
  AI_SQL_GENERATION '...' -- unchanged if present
  AI_VERIFIED_QUERIES (
    -- existing VQRs preserved here
    existing_vqr_1 AS (
      QUESTION '...'
      SQL '...'
    ),
    -- new VQRs appended:
    <vqr_name> AS (
      QUESTION '<natural language question>'
      ONBOARDING_QUESTION TRUE
      SQL '<the verified SQL using logical table alias names>'
    )
  );
```

> **Note:** Always preserve existing `AI_VERIFIED_QUERIES` entries when adding new ones — `CREATE OR REPLACE` replaces the entire object. Fetch the current DDL from `DESCRIBE SEMANTIC VIEW` first, then append new entries to the existing `AI_VERIFIED_QUERIES` block.

After adding, verify:
```sql
DESCRIBE SEMANTIC VIEW <SV_FQN>;
-- Check VQRs appear in output
```

---

## Integration with Toolkit

- **Fed by sv-ddl**: after creating a SV, bootstrap VQRs
- **Feeds sv-evaluation**: VQRs enable running evals
- **Feeds sv-optimization**: more VQRs = better eval coverage for optimization
- **Can be triggered by sv-evaluation**: if eval fails due to too few VQRs, route here

---

## Tips

- **Quality over quantity**: 10 well-crafted VQRs > 30 trivial ones
- **Cover all tools**: each metric, key dimension, and relationship should be tested by at least 1 VQR
- **Diverse difficulty**: mix simple (single table) and complex (multi-table, filtered) questions
- **User language**: phrase questions how real users would ask, not like SQL queries
