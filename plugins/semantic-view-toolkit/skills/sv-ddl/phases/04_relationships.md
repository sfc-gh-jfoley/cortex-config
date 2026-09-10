---
name: sv-ddl-phase4-relationships
description: Detect foreign key relationships between tables using column naming patterns, confirm with user, and validate with cardinality checks
---

# Phase 4: Relationship Detection

## Purpose
Identify which tables join to which, and on which columns.
Wrong or missing relationships are the most common cause of bad Cortex Analyst SQL generation.

---

## Step 4.1: Auto-detect candidate relationships

Scan `TABLE_PROFILES` for FK column naming patterns.

### Pattern matching rules

For every pair of tables (A, B):

1. **Exact name match**: column `X` appears in both tables → candidate join on `X`
2. **Table-prefixed FK**: table B has primary key `B_ID`; table A has column `B_ID` → A.B_ID → B.B_ID
3. **Suffix match**: table A has `<prefix>_ID` and table B has a column matching `<prefix>` or `<prefix>_ID`
4. **Common FK suffixes**: `_KEY`, `_CODE`, `_NBR`, `_NO`, `_SK`

```python
# Pseudocode for pattern detection
for col_a in table_a.columns:
    for col_b in table_b.columns:
        if col_a.name == col_b.name and col_a.name ends with FK_SUFFIXES:
            → candidate join: table_a.col_a → table_b.col_b
```

Also check for existing foreign key constraints:
```sql
SELECT
    fk.TABLE_NAME,
    fk.COLUMN_NAME,
    pk.TABLE_NAME AS REF_TABLE,
    pk.COLUMN_NAME AS REF_COLUMN
FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE fk ON rc.CONSTRAINT_NAME = fk.CONSTRAINT_NAME
JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE pk ON rc.UNIQUE_CONSTRAINT_NAME = pk.CONSTRAINT_NAME
WHERE fk.TABLE_SCHEMA = '<schema>';
```

(This often returns nothing in Snowflake since FK constraints are not enforced, but worth checking.)

---

## Step 4.2: Validate candidate joins with cardinality check

For each candidate join, verify it's actually N:1 (many-to-one) and not M:N:

```sql
-- Does table_a.fk_col have all values in table_b.pk_col? (referential integrity)
SELECT
    COUNT(*)                                    AS total_a,
    COUNT(DISTINCT a.<fk_col>)                  AS distinct_fk_values,
    COUNT(DISTINCT b.<pk_col>)                  AS distinct_pk_values,
    -- Check if FK values all exist in PK
    SUM(CASE WHEN b.<pk_col> IS NULL THEN 1 ELSE 0 END) AS unmatched_rows
FROM <table_a> a
LEFT JOIN <table_b> b ON a.<fk_col> = b.<pk_col>
LIMIT 1000000;
```

Use results to classify:
- `unmatched_rows > 0` → data quality warning (note it, but don't block)
- `distinct_fk_values ≈ total_a` → likely a 1:1 join
- `distinct_fk_values << total_a` → N:1 (many-to-one) — the expected case

---

## Step 4.2.5: M:N (many-to-many) bridge table detection

If the cardinality check in Step 4.2 reveals M:N (neither side is unique on the join column), the tables cannot be directly related in a semantic view — Snowflake requires one side to have a PRIMARY KEY or UNIQUE.

### Detection signal

For a candidate join A.col → B.col:
- `COUNT(DISTINCT A.col) << COUNT(*) FROM A` (col is not unique in A)
- `COUNT(DISTINCT B.col) << COUNT(*) FROM B` (col is not unique in B)
- → This is M:N. Neither table can be the "one" side.

### Common M:N patterns
- Students ↔ Courses (via enrollments)
- Products ↔ Orders (via line_items/order_items)
- Users ↔ Roles (via user_roles)
- Tags ↔ Articles (via article_tags)

### Response

Present to the user:

```
⚠️  M:N relationship detected: <table_a> ↔ <table_b>
    Neither side is unique on <join_col> — this is a many-to-many relationship.

    Semantic views require one side of each relationship to have a PRIMARY KEY.
    You need a bridge/junction table to model this correctly.

    Options:
      A) A bridge table already exists in your schema — tell me which one
         (e.g., LINE_ITEMS bridges ORDERS ↔ PRODUCTS)

      B) No bridge table exists — I'll suggest the structure:

         The bridge table should have:
           - A composite PRIMARY KEY: (<table_a_fk>, <table_b_fk>)
           - Foreign keys to both tables
           - Optionally: quantity, date, or other attributes of the relationship

         Example DDL for a bridge:
         CREATE TABLE <schema>.BRIDGE_<A>_<B> (
             <table_a_fk>  <type>  NOT NULL,
             <table_b_fk>  <type>  NOT NULL,
             -- optional attributes:
             -- QUANTITY NUMBER,
             -- CREATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
             PRIMARY KEY (<table_a_fk>, <table_b_fk>)
         );

      C) Skip this relationship — these tables don't need to be connected in the SV

    Which option?
```

Based on response:
- **A (bridge exists)** → add two N:1 relationships: bridge → table_a, bridge → table_b. Add the bridge table to `SOURCE_OBJECTS` if not already included.
- **B (create bridge)** → generate the DDL, present for approval, note that user must populate the table before the SV will work with this relationship.
- **C (skip)** → remove this candidate, proceed without connecting these tables.

---

## Step 4.2.6: Join column data type compatibility — BLOCKING check

For every candidate relationship that survived Steps 4.1–4.2.5, verify that the join columns on both sides have compatible data types before accepting them. This is a **hard block** — a type-mismatched relationship passes SV validation but causes every SQL generation attempt on that join path to fail at runtime. The agent has no way to detect or recover from this.

**Why this matters:** The SV relationship graph is trusted verbatim by the SQL generator. A `NUMBER(38,0)` column joined to a `VARCHAR(30)` column cannot match, regardless of what SQL is generated. This is the single most invisible defect class in semantic views — it passes `CREATE SEMANTIC VIEW`, passes `DESCRIBE`, but silently breaks every query that traverses that path.

Query `INFORMATION_SCHEMA.COLUMNS` for both sides of each relationship:

```sql
SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, NUMERIC_PRECISION, NUMERIC_SCALE, CHARACTER_MAXIMUM_LENGTH
FROM <SV_DB>.INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = '<schema>'
  AND (
      (TABLE_NAME = '<left_table>'  AND COLUMN_NAME = '<left_col>')
   OR (TABLE_NAME = '<right_table>' AND COLUMN_NAME = '<right_col>')
  );
```

> If tables span multiple databases, run one query per database using that database's `INFORMATION_SCHEMA`.

**Severity rules:**

| Left type | Right type | Severity | Action |
|---|---|---|---|
| `NUMBER` / `INT` / `FLOAT` | `VARCHAR` / `TEXT` / `CHAR` | **BLOCK** | Remove relationship — do not proceed |
| `BOOLEAN` | any non-boolean | **BLOCK** | Remove relationship — do not proceed |
| `VARIANT` / `OBJECT` / `ARRAY` | any structured type | **BLOCK** | Remove relationship — do not proceed |
| `DATE` | `TIMESTAMP_*` | **WARN** | Implicit cast exists but may lose time precision — confirm with data owner |
| `NUMBER(x,0)` | `NUMBER(y,0)` (different precision) | **WARN** | Potential truncation — confirm values fit |
| `VARCHAR(x)` | `VARCHAR(y)` (different lengths) | **INFO** | Usually fine — flag if left max length > right max length |
| Same base type, same precision | — | **PASS** | |

**On BLOCK — present to user:**

```
🚫 TYPE MISMATCH — RELATIONSHIP BLOCKED

  Relationship: <rel_name>
  Left:   <left_table>.<left_col>   →  <LEFT_DATA_TYPE>
  Right:  <right_table>.<right_col> →  <RIGHT_DATA_TYPE>

  These types are incompatible. This join will fail at query time.
  The relationship cannot be included in the semantic view as defined.

  Options:
    A) Find the correct join column — the matching key may be a different column.
       Run: SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME IN ('<left>', '<right>')
            ORDER BY DATA_TYPE, COLUMN_NAME;
       Look for a column that is <correct_type> on BOTH sides.

    B) Add an indirect bridge — if a third table has compatible keys to both sides,
       define two relationships through it rather than one broken direct relationship.
       Example: FCT.PRODUCT_SKU_ID (NUMBER) → GGC_LEVEL2.PRODUCT_SKU_ID (NUMBER) →
                DIM.PRODUCT_SKU_ID (NUMBER) — 2 clean hops instead of 1 broken hop.

    C) Fix at source — cast or coerce the mismatched column in the source table DDL
       or create a view that applies the cast, then re-point the SV table entry to the view.

    D) Remove this relationship — these tables don't share a compatible join key.
```

Remove the blocked relationship from `RELATIONSHIPS`. **Do not present it to the user in Step 4.3 as a valid candidate.** Present only the resolution options above and wait for the user to resolve before continuing.

Store all findings (BLOCK, WARN, INFO) as `TYPE_MISMATCH_FINDINGS`:
```
[{
  "rel_name": "...",
  "left_table": "...", "left_col": "...", "left_type": "...",
  "right_table": "...", "right_col": "...", "right_type": "...",
  "severity": "BLOCK|WARN|INFO"
}]
```

Add `TYPE_MISMATCH_FINDINGS` to the output variables for this phase (Step 4.8 → output).

---

## Step 4.3: Present relationship candidates for confirmation

```
Detected relationships (confirm or edit):

  1. line_items → orders  (MANY-TO-ONE)
     line_items.ORDER_ID references orders.ORDER_ID
     Cardinality: 120,000 line_items, 30,000 distinct ORDER_ID → ~4 items/order ✓

  2. orders → customers  (MANY-TO-ONE)
     orders.CUSTOMER_ID references customers.CUSTOMER_ID
     Cardinality: 30,000 orders, 8,500 distinct CUSTOMER_ID → ~3.5 orders/customer ✓

  3. vehicles → dealers  (MANY-TO-ONE)  ⚠️ WARNING: 234 unmatched rows
     vehicles.DEALER_ID references dealers.DEALER_ID
     234 vehicles have DEALER_ID values not in dealers table

No relationship detected between: orders ↔ vehicles (no common ID columns found)

Add missing relationships? Remove any above? (type changes or 'ok')
```

⚠️ **STOPPING POINT** — Wait for user to confirm.

---

## Step 4.4: Identify the "one" side — PRIMARY KEY confirmation

For each relationship, the right-hand (referenced) table **must** have PRIMARY KEY or UNIQUE on the join column.

For each reference table, run uniqueness check:
```sql
SELECT
    COUNT(*)                        AS total_rows,
    COUNT(DISTINCT <pk_col>)        AS distinct_values,
    COUNT(*) - COUNT(DISTINCT <pk_col>) AS duplicates
FROM <db>.<schema>.<ref_table>;
```

- `duplicates = 0` → can safely use `PRIMARY KEY (<pk_col>)` ✓
- `duplicates > 0` → the column is NOT a unique key; use `UNIQUE` only if a composite key is needed, or redesign

Report to user if any reference table fails the uniqueness check.

---

## Step 4.5: Handle multiple relationships between same table pair

If two tables have more than one relationship (e.g. `flights → airports` via both `departure_airport` and `arrival_airport`):

```
⚠️  Multiple relationships detected: flights → airports
    1. flights.DEPARTURE_AIRPORT → airports.AIRPORT_CODE  (named: flight_departure_airport)
    2. flights.ARRIVAL_AIRPORT   → airports.AIRPORT_CODE  (named: flight_arrival_airport)

Metrics that use both relationships will need USING (relationship_name) clause.
This will be handled automatically in Phase 5.
```

---

## Step 4.6: ASOF Relationship Detection

For each `ASOF_CANDIDATES` column from Phase 3, check if it can form a temporal join with a fact table.

### Detection logic

1. For each table with `asof_candidate: true` columns (typically dimension/lookup tables):
   - Find fact tables that share a FK column AND a date/timestamp column
   - The fact table's date column represents "as of when" and the dimension table's ASOF column represents "effective since"

2. Validate data types:
   ```sql
   -- ASOF column must be DATE, TIMESTAMP_NTZ, TIMESTAMP_LTZ, TIMESTAMP_TZ, or NUMBER
   SELECT COLUMN_NAME, DATA_TYPE
   FROM INFORMATION_SCHEMA.COLUMNS
   WHERE TABLE_SCHEMA = '<schema>'
     AND TABLE_NAME = '<dim_table>'
     AND COLUMN_NAME = '<asof_col>';
   ```

3. Generate the ASOF relationship:
   ```sql
   <fact_alias> ( <fk_col>, <date_col> ) REFERENCES <dim_alias> ( <pk_col>, ASOF <effective_date_col> )
   ```

### Example

```
ASOF relationship detected:

  orders (CURRENCY_CODE, ORDER_DATE) → exchange_rates (CURRENCY_CODE, ASOF EFFECTIVE_DATE)
  Meaning: For each order, match the exchange rate that was effective on or before the order date.
  ASOF column type: DATE ✓
```

---

## Step 4.7: Range Join Detection

For each `RANGE_JOIN_CANDIDATES` pair from Phase 3, generate a range-based relationship.

### Detection logic

1. For each table with `range_join_candidate: true` column pairs (`start_col`, `end_col`):
   - Verify both columns are the same type:
     ```sql
     SELECT COLUMN_NAME, DATA_TYPE
     FROM INFORMATION_SCHEMA.COLUMNS
     WHERE TABLE_SCHEMA = '<schema>'
       AND TABLE_NAME = '<range_table>'
       AND COLUMN_NAME IN ('<start_col>', '<end_col>');
     ```
   - Both must be DATE, TIMESTAMP, or NUMBER

2. Find fact tables with a date/temporal column that should match against the range interval

3. Generate the CONSTRAINT on the range table:
   ```sql
   CONSTRAINT <table>_range DISTINCT RANGE BETWEEN <start_col> AND <end_col> EXCLUSIVE
   ```

4. Generate the range relationship:
   ```sql
   <fact_alias> ( <date_col> ) REFERENCES <range_alias> ( BETWEEN <start_col> AND <end_col> EXCLUSIVE )
   ```

### Use cases
- **SCD Type 2 tables**: `VALID_FROM` / `VALID_TO` — match a fact's event date to the correct dimension version
- **Rate tables**: `EFFECTIVE_DATE` / `EXPIRY_DATE` — match to the applicable rate period
- **Time-banded pricing**: `START_DATE` / `END_DATE` — find the price tier for a transaction date

### Example

```
Range relationship detected:

  CONSTRAINT rates_range DISTINCT RANGE BETWEEN EFFECTIVE_DATE AND EXPIRY_DATE EXCLUSIVE
  orders (ORDER_DATE) → exchange_rates (BETWEEN EFFECTIVE_DATE AND EXPIRY_DATE EXCLUSIVE)
  Meaning: For each order, find the rate whose [EFFECTIVE_DATE, EXPIRY_DATE) interval contains ORDER_DATE.
  Column types: DATE = DATE ✓
```

---

## Step 4.8: Present all relationships for confirmation

Present standard FK relationships (from Steps 4.1–4.5) first, then ASOF and range relationships in separate sections.

```
═══ Standard FK Relationships ═══

  1. line_items → orders  (MANY-TO-ONE)
     line_items.ORDER_ID references orders.ORDER_ID ✓

  2. orders → customers  (MANY-TO-ONE)
     orders.CUSTOMER_ID references customers.CUSTOMER_ID ✓

═══ ASOF Relationships (temporal point-in-time) ═══

  3. orders → exchange_rates  (ASOF)
     orders (CURRENCY_CODE, ORDER_DATE) references exchange_rates (CURRENCY_CODE, ASOF EFFECTIVE_DATE)
     Match: nearest rate effective on or before each order date

═══ Range Relationships (interval matching) ═══

  4. orders → rate_tiers  (RANGE)
     CONSTRAINT: DISTINCT RANGE BETWEEN START_DATE AND END_DATE EXCLUSIVE
     orders (ORDER_DATE) references rate_tiers (BETWEEN START_DATE AND END_DATE EXCLUSIVE)
     Match: rate tier whose [START_DATE, END_DATE) contains each order date

Accept all? Edit? Remove any? (type changes or 'ok')
```

⚠️ **STOPPING POINT** — Wait for user to confirm ASOF and range relationships separately from standard FKs. These are more complex and users should verify the temporal semantics are correct.

---

## Step 4.9: No-relationship clarity gate

If Steps 4.1–4.8 found **zero** relationships across multiple tables, do NOT silently proceed. Present targeted questions:

```
I wasn't able to detect any relationships between your tables automatically.
This usually means column names don't follow common FK conventions (_ID, _KEY, etc.)
or these tables don't join directly.

A few questions to clarify:

1. Do any of these tables share a common key?
   Tables: <list all table names>
   (e.g., "TRANSACTIONS and ACCOUNTS both have ACCT_NBR")

2. Are these tables meant to be queried together (joined), or are they independent
   tables you want in a single semantic view for convenience?

3. If they do join — what columns link them?
   (e.g., "INVOICES.CLIENT_CODE = CLIENTS.CODE")
```

Based on user response:
- **User provides join columns** → add to `RELATIONSHIPS`, validate cardinality (Step 4.2), confirm
- **User says independent/no join** → set `RELATIONSHIPS = []`, proceed to Phase 5 (SV will work but cross-table queries won't be possible)
- **User is unsure** → suggest running `SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME IN (...)` to look for overlapping column names, then re-evaluate

⚠️ **STOPPING POINT** — Do not proceed to Phase 5 without a clear answer on relationships for multi-table SVs.

---

## Output variables

| Variable | Contents |
|----------|----------|
| `RELATIONSHIPS` | List of {name, left_table, left_col, right_table, right_col, cardinality_validated} |
| `PRIMARY_KEYS` | Per-table: {table → [pk_cols]} |
| `MULTI_REL_PAIRS` | Pairs of tables with >1 relationship path (need USING clause) |
| `ASOF_RELATIONSHIPS` | List of {name, left_table, fk_col, date_col, right_table, pk_col, asof_col, asof_col_type} |
| `RANGE_RELATIONSHIPS` | List of {name, left_table, match_col, right_table, start_col, end_col, constraint_name} |
| `TYPE_MISMATCH_FINDINGS` | List of {rel_name, left_table, left_col, left_type, right_table, right_col, right_type, severity} — BLOCK entries are excluded from RELATIONSHIPS |
