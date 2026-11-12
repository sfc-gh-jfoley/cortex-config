# Relationship Detection

Shared logic for detecting table relationships from multiple sources. Used by `sv-discovery` and `sv-gepa-optimizer` skills.

## Detection Sources (Priority Order)

### 1. Declared FK/PK Constraints (Confidence: 1.0)

Snowflake does not enforce FK constraints, but declared constraints are strong evidence of intentional relationships.

```sql
-- Discover declared FK relationships using SHOW IMPORTED KEYS.
-- INFORMATION_SCHEMA.KEY_COLUMN_USAGE does not exist in Snowflake.
-- FK constraints on standard tables are informational (RELY/NOVALIDATE).
SHOW IMPORTED KEYS IN DATABASE <DB>
  ->> SELECT
        "pk_table_name" AS parent_table,
        "pk_column_name" AS parent_column,
        "fk_table_name" AS child_table,
        "fk_column_name" AS child_column,
        "key_sequence" AS key_sequence,
        "fk_name" AS fk_constraint_name
      FROM $1
      WHERE "fk_schema_name" = :schema_name;
```

```sql
-- Discover PK and UNIQUE constraints.
SHOW PRIMARY KEYS IN DATABASE <DB>
  ->> SELECT
        "table_name",
        "column_name",
        "key_sequence",
        "constraint_name"
      FROM $1
      WHERE "schema_name" = :schema_name;

SHOW UNIQUE KEYS IN DATABASE <DB>
  ->> SELECT
        "table_name",
        "column_name",
        "key_sequence",
        "constraint_name"
      FROM $1
      WHERE "schema_name" = :schema_name;
```

`SHOW IMPORTED KEYS` supplies the column-level FK mapping, while `SHOW PRIMARY KEYS` and `SHOW UNIQUE KEYS` supply the target-key metadata. `TABLE_CONSTRAINTS` and `REFERENTIAL_CONSTRAINTS` do not expose key columns. On standard Snowflake tables, FK constraints are informational metadata and may be declared with `RELY`/`NOVALIDATE`.

### 2. Column Name Pattern Inference (Confidence: 0.70–0.95)

Match columns across tables using naming conventions. Higher confidence when column data types also match.

**Suffix Patterns:**

| Suffix | Example | Confidence |
|--------|---------|------------|
| `_ID` | `CUSTOMER_ID` → `CUSTOMERS.ID` or `CUSTOMERS.CUSTOMER_ID` | 0.90 |
| `_KEY` | `PRODUCT_KEY` → `DIM_PRODUCT.PRODUCT_KEY` | 0.85 |
| `_CODE` | `CURRENCY_CODE` → `CURRENCIES.CODE` | 0.80 |
| `_SK` | `CUSTOMER_SK` → `DIM_CUSTOMER.CUSTOMER_SK` | 0.85 |
| `_NBR` / `_NO` | `ORDER_NBR` → `ORDERS.ORDER_NBR` | 0.75 |
| `_FK` | `ORDER_FK` → `ORDERS.ORDER_ID` | 0.95 |

**Matching Algorithm:**

1. For each column with a recognized suffix, extract the entity name (prefix before suffix)
2. Search for a table whose name matches the entity (singular or plural)
3. Check if the target table has a PK/unique column matching the data type
4. Assign confidence based on suffix type + data type match

```python
# Pseudocode for pattern matching
SUFFIX_PATTERNS = {
    '_ID': 0.90, '_KEY': 0.85, '_CODE': 0.80,
    '_SK': 0.85, '_NBR': 0.75, '_NO': 0.75, '_FK': 0.95,
}

def match_column(col_name, tables):
    for suffix, base_confidence in SUFFIX_PATTERNS.items():
        if col_name.upper().endswith(suffix):
            entity = col_name[:-len(suffix)]
            # Look for table named entity (singular/plural)
            candidates = find_matching_tables(entity, tables)
            # Boost if data type matches PK
            if pk_type_matches:
                confidence = min(0.95, base_confidence + 0.05)
            return candidates, confidence
    return [], 0.0
```

### 3. Query Co-occurrence from ACCESS_HISTORY (Confidence: from frequency)

Tables frequently accessed together in the same query are likely related. Uses the structured `base_objects_accessed` JSON array — NOT query text parsing.

```sql
-- Find table co-occurrence pairs from ACCESS_HISTORY
-- Uses structured base_objects_accessed (array of objects with objectName, objectDomain)
WITH query_tables AS (
    SELECT
        query_id,
        f.value:objectName::STRING AS table_name
    FROM snowflake.account_usage.access_history,
        LATERAL FLATTEN(input => base_objects_accessed) f
    WHERE f.value:objectDomain::STRING = 'Table'
        AND query_start_time >= DATEADD(day, -90, CURRENT_TIMESTAMP())
        AND SPLIT_PART(f.value:objectName::STRING, '.', 2) = :schema_name
),
co_occurrences AS (
    SELECT
        a.table_name AS table_a,
        b.table_name AS table_b,
        COUNT(DISTINCT a.query_id) AS co_query_count
    FROM query_tables a
    JOIN query_tables b
        ON a.query_id = b.query_id
        AND a.table_name < b.table_name  -- avoid duplicates
    GROUP BY 1, 2
)
SELECT
    table_a,
    table_b,
    co_query_count,
    CASE
        WHEN co_query_count >= 50 THEN 'HIGH'
        WHEN co_query_count >= 10 THEN 'MEDIUM'
        ELSE 'LOW'
    END AS confidence_tier
FROM co_occurrences
ORDER BY co_query_count DESC;
```

### 4. Column Access Frequency (Supplementary Signal)

Which columns are most commonly accessed — helps prioritize which relationships matter most.

```sql
-- Column-level access frequency from ACCESS_HISTORY
SELECT
    obj.value:objectName::STRING AS table_name,
    col.value:columnName::STRING AS column_name,
    COUNT(DISTINCT query_id) AS access_count
FROM snowflake.account_usage.access_history,
    LATERAL FLATTEN(input => base_objects_accessed) obj,
    LATERAL FLATTEN(input => obj.value:columns) col
WHERE query_start_time >= DATEADD(day, -90, CURRENT_TIMESTAMP())
    AND obj.value:objectDomain::STRING = 'Table'
    AND SPLIT_PART(obj.value:objectName::STRING, '.', 2) = :schema_name
GROUP BY 1, 2
ORDER BY access_count DESC;
```

## Important Notes

- **Snowflake FK enforcement**: Snowflake does NOT enforce foreign keys. They are informational metadata only. However, declared FKs represent intentional design and get confidence 1.0.
- **ACCESS_HISTORY availability**: Requires Enterprise Edition or higher. Standard Edition accounts will only have methods 1 and 2 available.
- **Privileges**: Querying `SNOWFLAKE.ACCOUNT_USAGE` requires the `IMPORTED PRIVILEGES` grant on the SNOWFLAKE database.
- **Structured JSON approach**: Always use `base_objects_accessed` (structured array) rather than parsing `query_text`. The structured approach is reliable, version-stable, and doesn't require regex parsing of SQL.
