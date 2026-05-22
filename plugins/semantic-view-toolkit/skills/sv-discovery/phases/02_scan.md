---
name: sv-discovery-phase2-scan
description: Scan for relationships using FK constraints, column pattern inference, ACCESS_HISTORY co-occurrence (structured JSON), and column usage frequency
---

# Phase 2: Scan

## Purpose

Detect relationships between tables in the discovery scope using four methods. Build a weighted edge graph where nodes are tables and edges represent detected relationships with confidence scores.

**Input variables from Phase 1:** `DISCOVERY_DB`, `DISCOVERY_SCHEMAS`, `HAS_ACCOUNT_USAGE`, `TOTAL_OBJECT_COUNT`, `COVERED_TABLES`, `MODE`

---

## O(N²) Mitigation (>200 Objects)

If `TOTAL_OBJECT_COUNT > 200`, the pairwise column comparison in Step 2B becomes expensive. Present options before scanning:

**GUIDED mode — always ask:**
```
Your scope has <N> objects. Pairwise column comparison is O(N²) and may be slow.

Options:
A) Narrow scope — exclude specific schemas (e.g., staging, raw)
B) Pre-filter by schema affinity — only compare tables within the same schema + tables that share column prefixes across schemas
C) Proceed anyway (may take 2-5 minutes)
D) Skip column inference entirely (rely on FK constraints + co-occurrence only)
```

**AUTOPILOT mode:**
- If N > 200 and N <= 500: auto-select option B (schema affinity pre-filter)
- If N > 500: auto-select option B AND cap co-occurrence pairs at top 1000
- Report the optimization applied

Store as: `SCAN_STRATEGY` — `full` | `schema_affinity` | `fk_and_cooccurrence_only`

---

## Step 2A: FK/PK Constraint Scan

Follow the detection method in `references/relationship-detection.md`, Section 1 (Declared FK/PK Constraints).

For each schema in `DISCOVERY_SCHEMAS`:

```sql
-- Find all foreign key relationships in this schema
SELECT
    tc.table_name AS child_table,
    tc.table_schema AS child_schema,
    kcu.column_name AS child_column,
    rc.unique_constraint_name,
    kcu2.table_name AS parent_table,
    kcu2.table_schema AS parent_schema,
    kcu2.column_name AS parent_column
FROM <DISCOVERY_DB>.INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
JOIN <DISCOVERY_DB>.INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
    ON tc.constraint_name = rc.constraint_name
    AND tc.constraint_schema = rc.constraint_schema
JOIN <DISCOVERY_DB>.INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
    ON tc.constraint_name = kcu.constraint_name
    AND tc.constraint_schema = kcu.constraint_schema
JOIN <DISCOVERY_DB>.INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu2
    ON rc.unique_constraint_name = kcu2.constraint_name
    AND rc.unique_constraint_schema = kcu2.constraint_schema
WHERE tc.constraint_type = 'FOREIGN KEY'
    AND tc.table_schema IN (<DISCOVERY_SCHEMAS>);
```

Also get PK/UNIQUE constraints for reference:

```sql
SELECT
    tc.table_name,
    tc.table_schema,
    kcu.column_name,
    tc.constraint_type
FROM <DISCOVERY_DB>.INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
JOIN <DISCOVERY_DB>.INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
    ON tc.constraint_name = kcu.constraint_name
    AND tc.constraint_schema = kcu.constraint_schema
WHERE tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE')
    AND tc.table_schema IN (<DISCOVERY_SCHEMAS>)
ORDER BY tc.table_name, kcu.ordinal_position;
```

**Output:** Store each FK relationship as an edge:
```
{from_table, from_schema, from_column, to_table, to_schema, to_column, detection_method: 'FK', confidence: 1.0}
```

Set flag: `CONSTRAINTS_AVAILABLE = true/false` (if zero FK rows returned).

---

## Step 2B: Column Name FK Inference

Follow the detection method in `references/relationship-detection.md`, Section 2 (Column Name Pattern Inference).

**Skip this step if** `SCAN_STRATEGY = 'fk_and_cooccurrence_only'`.

First, get all columns in scope:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    COLUMN_NAME,
    DATA_TYPE,
    IS_NULLABLE
FROM <DISCOVERY_DB>.INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA IN (<DISCOVERY_SCHEMAS>)
ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION;
```

**Matching algorithm (pseudocode):**

```
For each column with a recognized suffix (_ID, _KEY, _CODE, _SK, _NBR, _NO, _FK):
  1. Extract entity name (prefix before suffix)
  2. Search for tables matching entity name (singular/plural/alias):
     - Exact match: CUSTOMER_ID → CUSTOMERS table
     - Singular: CUSTOMER_ID → CUSTOMER table
     - Alias: CUST_ID → CUSTOMERS (common abbreviations)
  3. In the target table, find PK/UNIQUE column with matching data type
  4. Assign confidence per references/relationship-detection.md suffix table
```

**Schema affinity pre-filter (if SCAN_STRATEGY = 'schema_affinity'):**
- Only compare columns WITHIN the same schema
- PLUS cross-schema where both schemas share ≥3 column name prefixes in common

**Output:** Store each inferred relationship as an edge:
```
{from_table, from_schema, from_column, to_table, to_schema, to_column, detection_method: 'COLUMN_PATTERN', confidence: 0.70-0.95}
```

---

## Step 2C: ACCESS_HISTORY Co-Occurrence

**Skip this step if** `HAS_ACCOUNT_USAGE = false`.

This is the most impactful signal — tables queried together are almost always related. Uses structured `base_objects_accessed` JSON array, NOT query text parsing.

```sql
WITH query_tables AS (
    SELECT
        ah.QUERY_ID,
        obj.value:objectName::VARCHAR AS table_fqn
    FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah,
        LATERAL FLATTEN(input => ah.BASE_OBJECTS_ACCESSED) obj
    WHERE ah.QUERY_START_TIME >= DATEADD('day', -90, CURRENT_TIMESTAMP())
        AND obj.value:objectDomain::STRING = 'Table'
        AND obj.value:objectName::STRING LIKE '<DISCOVERY_DB>.%'
)
SELECT
    a.table_fqn AS table_a,
    b.table_fqn AS table_b,
    COUNT(DISTINCT a.QUERY_ID) AS co_query_count
FROM query_tables a
JOIN query_tables b
    ON a.QUERY_ID = b.QUERY_ID
    AND a.table_fqn < b.table_fqn
GROUP BY 1, 2
HAVING co_query_count >= 3  -- minimum threshold to reduce noise
ORDER BY co_query_count DESC
LIMIT 2000;  -- cap for large accounts
```

**Filter to scope:** Remove pairs where either table is NOT in `DISCOVERY_SCHEMAS`.

**Confidence assignment per `references/confidence-scoring.md`:**
- co_query_count >= 50 → HIGH
- co_query_count 10-49 → MEDIUM
- co_query_count 3-9 → LOW

**Output:** Store each co-occurrence pair as an edge:
```
{table_a_fqn, table_b_fqn, co_query_count, detection_method: 'CO_OCCURRENCE', confidence: tier_score}
```

---

## Step 2D: Column Usage Frequency

**Skip this step if** `HAS_ACCOUNT_USAGE = false`.

Which columns are most commonly accessed — helps prioritize which relationships and columns matter most for the final SV recommendations.

```sql
SELECT
    obj.value:objectName::STRING AS table_fqn,
    col.value:columnName::STRING AS column_name,
    COUNT(DISTINCT query_id) AS access_count
FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY,
    LATERAL FLATTEN(input => BASE_OBJECTS_ACCESSED) obj,
    LATERAL FLATTEN(input => obj.value:columns) col
WHERE QUERY_START_TIME >= DATEADD('day', -90, CURRENT_TIMESTAMP())
    AND obj.value:objectDomain::STRING = 'Table'
    AND obj.value:objectName::STRING LIKE '<DISCOVERY_DB>.%'
GROUP BY 1, 2
ORDER BY access_count DESC
LIMIT 5000;
```

**Filter to scope:** Keep only columns for tables in `DISCOVERY_SCHEMAS`.

**Output:** Store as column usage map:
```
{table_fqn → {column_name → access_count}}
```

This data is used in Phase 3 for:
- Ranking which columns are most important per table
- Determining whether to recommend a table as "core" vs "peripheral"
- Identifying unused tables (zero column access = candidate for exclusion)

---

## Step 2E: Merge Edges into Relationship Graph

Combine all detected edges into a unified graph. For table pairs with multiple detection signals, compute combined confidence per `references/confidence-scoring.md`:

```
combined_score = max(individual_scores) + bonus_from_additional_signals

Bonus:
  2 signals agree: +0.05
  3 signals agree: +0.10
  4 signals agree: +0.15

Cap at 1.0.
```

**FK boost:** If an FK exists for a pair, boost the combined score one tier.

**Data type match boost:** If join columns have identical data types, add +0.05.

Store the final relationship graph:
```
RELATIONSHIP_GRAPH = [
  {table_a, table_b, join_column_a, join_column_b, combined_confidence, detection_methods[], co_query_count}
]
```

---

## Step 2F: Scan Summary

Present a summary before proceeding:

```
Scan Complete:

Detection Results:
  FK constraints found:        <N> relationships
  Column pattern matches:      <N> relationships
  Co-occurrence pairs (≥3):    <N> table pairs
  Column usage data:           <N> columns with access data

Relationship Graph:
  Total edges:                 <N>
  HIGH confidence (≥0.85):     <N>
  MEDIUM confidence (0.60-0.84): <N>
  LOW confidence (0.30-0.59):  <N>

Tables with ≥1 relationship:  <N> / <TOTAL_OBJECT_COUNT>
Orphan tables (no relationships): <N>

Top 5 most connected tables:
  1. <TABLE> — <N> edges
  2. <TABLE> — <N> edges
  ...
```

**GUIDED mode:** Present summary and wait for approval before Phase 3.
**AUTOPILOT mode:** Present summary and continue automatically.

---

## Output Variables Passed to Phase 3

| Variable | Contents |
|----------|----------|
| `RELATIONSHIP_GRAPH` | List of edges with confidence scores |
| `COLUMN_USAGE` | Column access frequency map |
| `PK_MAP` | Primary key columns per table |
| `CONSTRAINTS_AVAILABLE` | Whether FK constraints existed |
| `ORPHAN_TABLES` | Tables with no detected relationships |
| `SCAN_STRATEGY` | Which optimization was applied |
