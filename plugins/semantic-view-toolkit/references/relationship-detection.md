# Relationship Detection

Shared detection rules for table relationships. The SQL for each method lives in one place,
`skills/sv-discovery/phases/02_scan.md`; this file holds the rules that SQL applies. Scores are in
`confidence-scoring.md`.

## Detection Sources (Priority Order)

### 1. Declared FK/PK Constraints (Confidence: 1.0)

Snowflake does not enforce FK constraints, but declared constraints are strong evidence of intentional relationships.

Use `SHOW IMPORTED KEYS`, `SHOW PRIMARY KEYS` and `SHOW UNIQUE KEYS` (SQL: Phase 2 Step 2A).
Keep the `pk_*`/`fk_*` database and schema columns so cross-schema FKs are not lost.
`INFORMATION_SCHEMA.KEY_COLUMN_USAGE` does not exist in Snowflake, and `TABLE_CONSTRAINTS` /
`REFERENTIAL_CONSTRAINTS` do not expose key columns. On standard Snowflake tables, FK constraints
are informational metadata and may be declared with `RELY`/`NOVALIDATE`.

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
    '_FK': 0.95, '_ID': 0.90, '_KEY': 0.85, '_SK': 0.85,
    '_CODE': 0.80, '_NBR': 0.75, '_NO': 0.75,
}

def match_column(col, tables):
    """col: {name, data_type}. Returns [(target_table, target_col, confidence)]."""
    matches = []
    for suffix, base in SUFFIX_PATTERNS.items():
        if not col['name'].upper().endswith(suffix):
            continue
        entity = col['name'][:-len(suffix)]
        for table in find_matching_tables(entity, tables):       # singular/plural/alias
            for key in table.pk_or_unique_columns():
                score = base + (0.05 if key.data_type == col['data_type'] else 0.0)
                matches.append((table.name, key.name, min(0.95, score)))
    return matches  # empty if no suffix or no target matched
```

### 3. Query Co-occurrence from ACCESS_HISTORY (Confidence: from frequency)

Tables frequently accessed together in the same query are likely related (SQL: Phase 2 Step 2C).
Rules:
- Use the structured `base_objects_accessed` array, not query-text parsing.
- Compare `objectDomain` case-insensitively (`UPPER(...)`); doc examples spell it inconsistently.
- Filter to the discovery database **and** schemas inside the CTE, before any LIMIT.
- Co-occurrence is table-level: it never supplies join columns (see `confidence-scoring.md`,
  Join-key rule).
- ETL statements (INSERT…SELECT, CTAS, dynamic-table refreshes) inflate counts; exclude them where
  possible.

### 4. Column Access Frequency (Supplementary Signal)

Which columns are most commonly accessed (SQL: Phase 2 Step 2D). It ranks columns and tables; it is
not a pairwise relationship signal.

## Important Notes

- **Snowflake FK enforcement**: Snowflake does NOT enforce foreign keys. They are informational metadata only. However, declared FKs represent intentional design and get confidence 1.0.
- **ACCESS_HISTORY availability**: Requires Enterprise Edition or higher. Standard Edition accounts will only have methods 1 and 2 available.
- **Privileges**: Querying `SNOWFLAKE.ACCOUNT_USAGE` requires the `IMPORTED PRIVILEGES` grant on the SNOWFLAKE database.
- **Structured JSON approach**: Always use `base_objects_accessed` (structured array) rather than parsing `query_text`. The structured approach is reliable, version-stable, and doesn't require regex parsing of SQL.
