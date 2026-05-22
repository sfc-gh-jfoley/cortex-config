# Audit Mode Fixture: Pre-built SV with Known Gaps

## Scenario

Audit a semantic view that has deliberate gaps for testing.

### Setup — Create Test SV

```sql
CREATE OR REPLACE SEMANTIC VIEW TEST_DB.PUBLIC.ORDERS_SV
  COMMENT = 'Test SV for audit fixture — deliberately incomplete'
AS
TABLES (
  TEST_DB.PUBLIC.ORDERS
    PRIMARY KEY (ORDER_ID)
    AS (
      ORDER_ID COMMENT 'Unique order identifier',
      CUSTOMER_ID COMMENT 'FK to customers',
      ORDER_DATE COMMENT 'Date order placed',
      TOTAL_AMOUNT COMMENT 'Order total in USD',
      STATUS COMMENT 'Order status'
    ),
  TEST_DB.PUBLIC.ORDER_ITEMS
    PRIMARY KEY (ITEM_ID)
    AS (
      ITEM_ID COMMENT 'Unique line item ID',
      ORDER_ID COMMENT 'FK to orders',
      PRODUCT_ID COMMENT 'FK to products',
      QUANTITY COMMENT 'Quantity ordered',
      UNIT_PRICE COMMENT 'Price per unit'
    )
)
RELATIONSHIPS (
  ORDER_ITEMS (ORDER_ID) REFERENCES ORDERS (ORDER_ID)
)
FACTS (
  ORDERS (TOTAL_AMOUNT),
  ORDER_ITEMS (QUANTITY, UNIT_PRICE)
)
DIMENSIONS (
  ORDERS (ORDER_ID, CUSTOMER_ID, STATUS),
  ORDER_ITEMS (ITEM_ID, ORDER_ID, PRODUCT_ID)
)
METRICS (
  TOTAL_REVENUE AS SUM(ORDERS.TOTAL_AMOUNT),
  AVG_ORDER_SIZE AS AVG(ORDER_ITEMS.QUANTITY)
);
```

### Deliberate Gaps (what audit should find)

1. **Missing table:** CUSTOMERS is referenced by CUSTOMER_ID but not included
2. **Missing table:** PRODUCTS is referenced by PRODUCT_ID but not included
3. **Missing relationship:** ORDER_ITEMS.PRODUCT_ID → PRODUCTS.PRODUCT_ID not defined
4. **Missing column:** Assume ORDER_DATE is heavily used for filtering (TIME_DIMENSION) but only as DIMENSION
5. **Unused column potential:** If no queries filter by ITEM_ID, it could be flagged

### Simulated Query Patterns (what QUERY_HISTORY should show)

Assume these queries exist in the account's history:

```sql
-- Pattern 1: Orders + Customers join (89 queries)
SELECT o.*, c.CUSTOMER_NAME FROM ORDERS o JOIN CUSTOMERS c ON o.CUSTOMER_ID = c.CUSTOMER_ID;

-- Pattern 2: Order Items + Products join (67 queries)
SELECT oi.*, p.PRODUCT_NAME FROM ORDER_ITEMS oi JOIN PRODUCTS p ON oi.PRODUCT_ID = p.PRODUCT_ID;

-- Pattern 3: Full chain (45 queries)
SELECT c.CUSTOMER_NAME, o.ORDER_DATE, p.PRODUCT_NAME, oi.QUANTITY
FROM ORDERS o
JOIN CUSTOMERS c ON o.CUSTOMER_ID = c.CUSTOMER_ID
JOIN ORDER_ITEMS oi ON o.ORDER_ID = oi.ORDER_ID
JOIN PRODUCTS p ON oi.PRODUCT_ID = p.PRODUCT_ID
WHERE o.ORDER_DATE >= '2024-01-01';

-- Pattern 4: Shipments join (23 queries) — table not even in SV
SELECT o.ORDER_ID, s.SHIP_DATE, s.CARRIER
FROM ORDERS o JOIN SHIPMENTS s ON o.ORDER_ID = s.ORDER_ID;
```

## Expected Audit Output

### 1. Missing Tables

| Table | Co-query Count | Join Key | Recommendation |
|---|---|---|---|
| CUSTOMERS | 134 | ORDERS.CUSTOMER_ID → CUSTOMERS.CUSTOMER_ID | **ADD** — heavily joined |
| PRODUCTS | 112 | ORDER_ITEMS.PRODUCT_ID → PRODUCTS.PRODUCT_ID | **ADD** — heavily joined |
| SHIPMENTS | 23 | ORDERS.ORDER_ID → SHIPMENTS.ORDER_ID | **CONSIDER** — moderate usage |

### 2. Missing Columns

| Column | Table | Access Count | Recommendation |
|---|---|---|---|
| CUSTOMER_NAME | CUSTOMERS | 134 | ADD (requires CUSTOMERS table first) |
| PRODUCT_NAME | PRODUCTS | 112 | ADD (requires PRODUCTS table first) |
| SHIP_DATE | SHIPMENTS | 23 | CONSIDER (requires SHIPMENTS table) |

### 3. Relationship Gaps

| From | To | Join Pattern | Frequency | Recommendation |
|---|---|---|---|---|
| ORDER_ITEMS | PRODUCTS | PRODUCT_ID | 112 queries | ADD RELATIONSHIP |
| ORDERS | SHIPMENTS | ORDER_ID | 23 queries | ADD RELATIONSHIP (if SHIPMENTS added) |

### 4. Classification Improvements

| Column | Current | Suggested | Reason |
|---|---|---|---|
| ORDER_DATE | DIMENSION | TIME_DIMENSION | Heavily used in date range filters |

### 5. Size Assessment

- Current: 10 columns, 2 tables
- After additions: ~25 columns, 4-5 tables
- Verdict: Standard size — single SV is appropriate

## Validation Criteria

- [ ] CUSTOMERS identified as missing (HIGH priority)
- [ ] PRODUCTS identified as missing (HIGH priority)
- [ ] SHIPMENTS identified as candidate (MEDIUM priority)
- [ ] ORDER_ITEMS → PRODUCTS relationship gap detected
- [ ] ORDER_DATE reclassification suggested (if ACCESS_HISTORY shows date filtering)
- [ ] Recommendations ordered by priority (relationship gaps → missing tables → missing columns)
- [ ] User approval gate before suggesting changes
- [ ] Handoff to semantic-view-ddl suggested for applying changes
