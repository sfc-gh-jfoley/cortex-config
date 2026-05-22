---
name: semantic-view-ddl-syntax-reference
description: Complete CREATE SEMANTIC VIEW DDL syntax with all pitfalls, examples, and battle-tested rules
---

# CREATE SEMANTIC VIEW — DDL Syntax Reference

## Top-level template

```sql
CREATE [ OR REPLACE ] SEMANTIC VIEW [ IF NOT EXISTS ] <db>.<schema>.<name>
  TABLES ( logicalTable [ , ... ] )
  [ RELATIONSHIPS ( relationshipDef [ , ... ] ) ]
  [ FACTS ( factExpression [ , ... ] ) ]
  [ DIMENSIONS ( dimensionExpression [ , ... ] ) ]
  [ METRICS ( metricExpression [ , ... ] ) ]
  [ COMMENT = '<comment_about_semantic_view>' ]
  [ [ WITH ] TAG ( <tag_name> = '<tag_value>' [ , ... ] ) ]
  [ AI_SQL_GENERATION '<instructions_for_sql_generation>' ]
  [ AI_QUESTION_CATEGORIZATION '<instructions_for_question_categorization>' ]
  [ AI_VERIFIED_QUERIES ( verifiedQuery [ , ... ] ) ]
```

---

## Clause grammar

### logicalTable

```sql
[ <table_alias> AS ] <database>.<schema>.<table_or_view_name>
  [ PRIMARY KEY ( <col> [ , ... ] ) ]
  [ UNIQUE ( <col> [ , ... ] ) [ ... ] ]        -- can repeat for multiple unique key sets
  [ CONSTRAINT [ <constraint_name> ]
    DISTINCT RANGE BETWEEN <start_column> AND <end_column> EXCLUSIVE ]
  [ WITH SYNONYMS [ = ] ( '<synonym>' [ , ... ] ) ]
  [ [ WITH ] TAG ( <tag_name> = '<tag_value>' [ , ... ] ) ]
  [ COMMENT = '<table description>' ]
```

**Supported source object types:** The `<table_or_view_name>` can reference any of:
- Standard tables
- Views (including secure views)
- Dynamic tables
- Materialized views

All are valid sources for a semantic view. The engine resolves the FQN against the catalog — any object that supports `SELECT` can be used. Semantic views referencing other semantic views ("composable SVs") are not yet GA.

**DISTINCT RANGE BETWEEN:** Declares a half-open interval `[start, end)` constraint. Both columns must be the same type (DATE, TIMESTAMP, or NUMBER) and belong to the same logical table. Used for SCD Type 2 tables, rate tables, and time-banded lookups. Used with range-join relationships (see `relationshipDef`).

### relationshipDef

```sql
[ <rel_name> AS ]
<left_table_alias> ( <fk_col> [ , ... ] )
REFERENCES <right_table_alias>
[ ( <pk_col> [ , ... ] ) ]
```

For ASOF joins (matching on nearest-prior date):
```sql
<left_table_alias> ( <fk_col>, <date_col> )
REFERENCES <right_table_alias> ( <pk_col>, ASOF <date_col> )
```

For range joins (matching against a half-open interval):
```sql
<left_table_alias> ( <col> )
REFERENCES <right_table_alias> ( BETWEEN <start_col> AND <end_col> EXCLUSIVE )
```

**Range join:** Used with tables that have a `DISTINCT RANGE BETWEEN` constraint. The left-hand column is matched against the right-hand table's `[start_col, end_col)` interval. Typical uses: SCD Type 2 lookups, rate/tier tables, time-banded dimension joins.

### factExpression

```sql
[ PRIVATE | PUBLIC ] <table_alias>.<fact_name>
  [ LABELS = ( FILTER ) ]
  AS <sql_expr>
  [ WITH SYNONYMS [ = ] ( '<synonym>' [ , ... ] ) ]
  [ [ WITH ] TAG ( <tag_name> = '<tag_value>' [ , ... ] ) ]
  [ COMMENT = '<description>' ]
```

`LABELS = ( FILTER )` marks a fact as usable in WHERE clauses. The `AS` expression **must** resolve to BOOLEAN. Cannot be used on metrics.

### dimensionExpression

```sql
[ PUBLIC ] <table_alias>.<dim_name>
  [ LABELS = ( FILTER ) ]
  AS <sql_expr>
  [ WITH SYNONYMS [ = ] ( '<synonym>' [ , ... ] ) ]
  [ [ WITH ] TAG ( <tag_name> = '<tag_value>' [ , ... ] ) ]
  [ COMMENT = '<description>' ]
  [ WITH CORTEX SEARCH SERVICE <db>.<schema>.<css_name> [ USING <col_name> ] ]
```

`LABELS = ( FILTER )` on a dimension marks it as a preferred WHERE-clause filter. Typically used on BOOLEAN dimensions (IS_ACTIVE, HAS_DISCOUNT, etc.).

### metricExpression

```sql
[ PRIVATE | PUBLIC ] <table_alias>.<metric_name>
  [ USING ( <relationship_name> [ , ... ] ) ]
  [ NON ADDITIVE BY ( <dim> [ ASC | DESC ] [ , ... ] ) ]
  AS <aggregate_sql_expr>
  [ WITH SYNONYMS [ = ] ( '<synonym>' [ , ... ] ) ]
  [ [ WITH ] TAG ( <tag_name> = '<tag_value>' [ , ... ] ) ]
  [ COMMENT = '<description>' ]
```

### windowFunctionMetricExpression

```sql
[ PRIVATE | PUBLIC ] <table_alias>.<metric_name>
  [ USING ( <relationship_name> [ , ... ] ) ]
  AS <window_function>( <metric> ) OVER (
    [ PARTITION BY { <exprs_using_dimensions_or_metrics> | EXCLUDING <dimensions> } ]
    [ ORDER BY <exprs_using_dimensions_or_metrics> [ ASC | DESC ] [ NULLS { FIRST | LAST } ] [, ...] ]
    [ <windowFrameClause> ]
  )
  [ WITH SYNONYMS [ = ] ( '<synonym>' [ , ... ] ) ]
  [ [ WITH ] TAG ( <tag_name> = '<tag_value>' [ , ... ] ) ]
  [ COMMENT = '<description>' ]
```

Window function metrics apply a window function over an existing metric. Key constraints:
- `PARTITION BY EXCLUDING` dynamically removes specified dimensions from the partition at query time — the engine partitions by all remaining dimensions in the query's GROUP BY except the excluded ones.
- The inner `<metric>` reference must be a metric defined in the same entity (table).
- Cannot nest window functions or use subqueries in `PARTITION BY`.
- Only dimensions accessible from the same entity can be referenced in `EXCLUDING`.

### verifiedQuery (for AI_VERIFIED_QUERIES)

```sql
<vq_name> AS (
  QUESTION '<natural language question>'
  [ VERIFIED_AT <timestamp> ]
  [ ONBOARDING_QUESTION TRUE | FALSE ]
  SQL '<sql_query>'
)
```

---

## Critical rules — violations produce silent wrong results or DDL errors

| # | Rule | Common mistake |
|---|------|----------------|
| 1 | Clause order is **enforced**: TABLES → RELATIONSHIPS → FACTS → DIMENSIONS → METRICS | Putting DIMENSIONS before RELATIONSHIPS |
| 2 | TABLES alone → "No queryable expression" error. Need FACTS **or** DIMENSIONS minimum | Defining only TABLES block |
| 3 | For a direct column reference, the alias **MUST match the source column name exactly** | `orders.order_date AS order_dt` → broken. Must be `AS o_orderdate` if the source object's col is `o_orderdate` |
| 4 | Computed expressions **CAN** have a new name | `orders.order_year AS YEAR(o_orderdate)` is valid |
| 5 | A column with the same name appearing in multiple tables → define as fact/dim from **ONE table only**, skip the others | Defining `CUSTOMER_ID` from both orders and customers tables |
| 6 | The **right-hand table** in a REFERENCES clause needs `PRIMARY KEY` or `UNIQUE` on the join column | Referencing a table with no key constraint → join fails |
| 7 | `PRIVATE` is valid on facts and metrics; dimensions only support `PUBLIC` | Using `PRIVATE` on a dimension |
| 8 | When two relationship paths exist between the same pair of tables, use `USING (rel_name)` on the metric | Ambiguous routing causes query errors |
| 9 | `NON ADDITIVE BY` marks a metric as non-additive along the given dimensions (e.g. DISTINCT COUNT by user) | Omitting this causes incorrect roll-up aggregation |
| 10 | `AI_VERIFIED_QUERIES` SQL must reference the logical alias names (not physical table.col), and use the SV's fact/dim/metric names | Using physical table names in VQ SQL |
| 11 | `LABELS = ( FILTER )` requires the `AS` expression to resolve to BOOLEAN | Applying FILTER label to a VARCHAR or numeric column |
| 12 | Window function metrics cannot reference aggregates or subqueries in `PARTITION BY` | `PARTITION BY SUM(x)` → use a PRIVATE metric for the inner aggregate |
| 13 | `DISTINCT RANGE BETWEEN` columns must belong to the same logical table as the constraint | Referencing columns from a different table in the range constraint |

---

## Common column classification guide

| Column characteristics | Classify as |
|------------------------|-------------|
| `INTEGER`, `NUMBER`, `FLOAT` that represents a measured value | FACT |
| `DATE`, `TIMESTAMP`, `DATETIME` | DIMENSION (time dimension — name it clearly) |
| `VARCHAR`, `TEXT`, `BOOLEAN` that is a category, label, or ID used in filters | DIMENSION |
| Aggregate expression: `SUM(...)`, `COUNT(...)`, `AVG(...)` — not a raw column | METRIC |
| `NUMBER` used as a foreign key / ID (not summed) | DIMENSION |

---

## Full working example (TPC-H)

```sql
CREATE OR REPLACE SEMANTIC VIEW MY_DB.PUBLIC.TPCH_REVENUE_SV
  TABLES (
    orders    AS SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.ORDERS
      PRIMARY KEY (O_ORDERKEY)
      WITH SYNONYMS = ('sales orders', 'purchase orders')
      COMMENT = 'All customer orders',
    customers AS SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.CUSTOMER
      PRIMARY KEY (C_CUSTKEY)
      COMMENT = 'Customer master data',
    line_items AS SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.LINEITEM
      PRIMARY KEY (L_ORDERKEY, L_LINENUMBER)
      COMMENT = 'Individual line items within orders'
  )
  RELATIONSHIPS (
    orders_to_customers AS orders (O_CUSTKEY) REFERENCES customers,
    line_item_to_orders AS line_items (L_ORDERKEY) REFERENCES orders
  )
  FACTS (
    orders.O_TOTALPRICE AS O_TOTALPRICE
      COMMENT = 'Total price of the order',
    line_items.L_EXTENDEDPRICE AS L_EXTENDEDPRICE
      COMMENT = 'Line item extended price before discount',
    line_items.discounted_price AS L_EXTENDEDPRICE * (1 - L_DISCOUNT)
      COMMENT = 'Line item price after applying discount'
  )
  DIMENSIONS (
    customers.C_NAME AS C_NAME
      WITH SYNONYMS = ('customer name', 'client name')
      COMMENT = 'Full name of the customer',
    customers.C_MKTSEGMENT AS C_MKTSEGMENT
      WITH SYNONYMS = ('market segment', 'industry')
      COMMENT = 'Market segment the customer belongs to',
    orders.O_ORDERDATE AS O_ORDERDATE
      COMMENT = 'Date the order was placed',
    orders.order_year AS YEAR(O_ORDERDATE)
      COMMENT = 'Calendar year the order was placed',
    orders.O_ORDERSTATUS AS O_ORDERSTATUS
      WITH SYNONYMS = ('order status', 'status')
      COMMENT = 'Current order status: O (Open), F (Fulfilled), P (Partial)'
  )
  METRICS (
    customers.customer_count AS COUNT(C_CUSTKEY)
      COMMENT = 'Total number of customers',
    orders.total_revenue AS SUM(O_TOTALPRICE)
      COMMENT = 'Sum of all order values',
    orders.avg_order_value AS AVG(O_TOTALPRICE)
      COMMENT = 'Average value per order'
  )
  COMMENT = 'Revenue and customer analytics semantic view on TPC-H data'
  AI_SQL_GENERATION 'Always filter orders by O_ORDERSTATUS when a status is mentioned. Use O_ORDERDATE for all time-based filtering. Prefer COUNT(DISTINCT C_CUSTKEY) for unique customer counts.'
  AI_VERIFIED_QUERIES (
    top_customers AS (
      QUESTION 'Who are the top 10 customers by total revenue?'
      ONBOARDING_QUESTION TRUE
      SQL 'SELECT C_NAME, SUM(O_TOTALPRICE) AS total_revenue
           FROM orders JOIN customers ON O_CUSTKEY = C_CUSTKEY
           GROUP BY C_NAME ORDER BY total_revenue DESC LIMIT 10'
    ),
    monthly_revenue AS (
      QUESTION 'What is total revenue by month?'
      SQL 'SELECT DATE_TRUNC(''month'', O_ORDERDATE) AS month, SUM(O_TOTALPRICE) AS revenue
           FROM orders GROUP BY 1 ORDER BY 1'
    )
  );
```

### Window metric and range join example

```sql
CREATE OR REPLACE SEMANTIC VIEW MY_DB.PUBLIC.SALES_WITH_RATES_SV
  TABLES (
    orders AS MY_DB.PUBLIC.ORDERS
      PRIMARY KEY (ORDER_ID)
      COMMENT = 'Daily sales orders',
    exchange_rates AS MY_DB.PUBLIC.EXCHANGE_RATES
      PRIMARY KEY (CURRENCY_CODE, EFFECTIVE_DATE)
      CONSTRAINT rates_range DISTINCT RANGE BETWEEN EFFECTIVE_DATE AND EXPIRY_DATE EXCLUSIVE
      COMMENT = 'SCD Type 2 currency exchange rates'
  )
  RELATIONSHIPS (
    orders_to_rates AS orders (CURRENCY_CODE, ORDER_DATE)
      REFERENCES exchange_rates (CURRENCY_CODE, ASOF EFFECTIVE_DATE),
    orders_to_rates_range AS orders (ORDER_DATE)
      REFERENCES exchange_rates (BETWEEN EFFECTIVE_DATE AND EXPIRY_DATE EXCLUSIVE)
  )
  FACTS (
    orders.ORDER_AMOUNT AS ORDER_AMOUNT
      COMMENT = 'Order amount in local currency',
    orders.IS_RETURNED AS IS_RETURNED
      LABELS = ( FILTER )
      COMMENT = 'Whether the order was returned'
  )
  DIMENSIONS (
    orders.ORDER_DATE AS ORDER_DATE
      COMMENT = 'Date the order was placed',
    orders.order_year AS YEAR(ORDER_DATE)
      COMMENT = 'Calendar year of order',
    orders.CURRENCY_CODE AS CURRENCY_CODE
      COMMENT = 'ISO currency code',
    orders.IS_PRIORITY AS IS_PRIORITY
      LABELS = ( FILTER )
      COMMENT = 'Whether the order is high priority'
  )
  METRICS (
    PRIVATE orders.total_revenue AS SUM(ORDER_AMOUNT)
      COMMENT = 'Sum of order amounts (private — used by window metrics)',
    orders.avg_order_value AS AVG(ORDER_AMOUNT)
      COMMENT = 'Average order amount',
    orders.revenue_running_total AS SUM(orders.total_revenue) OVER (
      PARTITION BY EXCLUDING orders.ORDER_DATE
      ORDER BY orders.ORDER_DATE
      ROWS UNBOUNDED PRECEDING
    )
      COMMENT = 'Cumulative revenue running total over time',
    orders.revenue_rank AS RANK() OVER (
      ORDER BY orders.total_revenue DESC
    )
      COMMENT = 'Revenue rank across all groupings'
  )
  COMMENT = 'Sales analytics with SCD2 exchange rates and window metrics'
  WITH TAG ( 'domain' = 'finance', 'data_classification' = 'internal' )
  AI_SQL_GENERATION 'Use ORDER_DATE for time filtering. IS_RETURNED and IS_PRIORITY are boolean filters.';
```

---

## Querying a semantic view (SELECT syntax)

After deployment, you can query your semantic view directly using SQL:

**Approach A — SEMANTIC_VIEW clause:**
```sql
SELECT * FROM SEMANTIC_VIEW(
  MY_DB.PUBLIC.TPCH_REVENUE_SV
  DIMENSIONS customers.C_MKTSEGMENT
  METRICS orders.total_revenue
) ORDER BY C_MKTSEGMENT;
```

**Approach B — Direct FROM with AGG():**
```sql
SELECT C_MKTSEGMENT, AGG(total_revenue)
FROM MY_DB.PUBLIC.TPCH_REVENUE_SV
GROUP BY C_MKTSEGMENT
ORDER BY C_MKTSEGMENT;
```

**Key rules:**
- You need `SELECT` privilege on the semantic view (not on the underlying source objects)
- Cannot mix FACTS and METRICS in the same SEMANTIC_VIEW() clause
- Dimensions used with a metric must have equal or lower granularity than the metric's entity
- Use `SHOW SEMANTIC DIMENSIONS FOR METRIC <sv>.<metric>` to check valid dimension/metric combinations

---

## Error cheat sheet

| Error message | Root cause | Fix |
|--------------|-----------|-----|
| `No queryable expression` | TABLES defined but no FACTS or DIMENSIONS | Add at least one FACTS or DIMENSIONS clause |
| `invalid identifier 'X'` | Fact/dim alias doesn't match physical column name | Change alias to match exact physical column name |
| `Duplicate identifier` | Same column name defined in multiple tables' FACTS/DIMENSIONS | Keep definition on one table, remove from others |
| `relationship ... requires primary key` | Right-hand table in REFERENCES has no PRIMARY KEY or UNIQUE | Add PRIMARY KEY to the referenced table |
| `ambiguous relationship` | Two relationship paths between same tables | Add `USING (relationship_name)` on the metric |
| `Object does not exist` | Physical table path wrong or role lacks access | Verify `SELECT * FROM db.schema.table LIMIT 1` first |
| `PRIVATE not allowed on dimension` | Used PRIVATE on a dimension expression | Remove PRIVATE; use PUBLIC or no modifier |
| `FILTER label on non-boolean expression` | LABELS = (FILTER) on a column whose AS expr is not BOOLEAN | Ensure the AS expression returns BOOLEAN (e.g., `AS IS_ACTIVE`, `AS L_QUANTITY > 0`) |
| `Window function in window function` | Nested window function in a window metric | Flatten: define the inner window as a PRIVATE metric, then reference it in the outer window metric |
| `Range constraint columns from different tables` | DISTINCT RANGE BETWEEN references columns not in the same logical table | Both start and end columns must be physical columns of the same table declared in TABLES |
| `syntax error at position N unexpected 'COMMENT'` (in RELATIONSHIPS) | COMMENT placed inside a relationship definition | Remove COMMENT from RELATIONSHIPS — only tables/facts/dims support COMMENT |
| `syntax error near 'SYNONYMS'` | Used bare `SYNONYMS = (...)` without `WITH` keyword | Must use `WITH SYNONYMS = ('...')` — always include the `WITH` prefix |
| `SQL compilation error` on COMMENT before TABLES | Top-level COMMENT placed before TABLES clause | Move COMMENT to after the last clause (METRICS), before AI_SQL_GENERATION |
| `Referenced key ... does not match` | FK column count doesn't match referenced table's PK column count | Ensure the number of columns in `(<fk_cols>)` matches the PK declaration on the REFERENCES target. For composite PKs, list all PK columns or omit the column list (auto-match). |
| `Object '<X>' does not exist or not authorized` | Source object FQN is wrong, object doesn't exist, or role lacks SELECT | Verify with `SHOW OBJECTS LIKE '<name>' IN SCHEMA <db>.<schema>` and check grants |
| `Semantic view cannot reference another semantic view` | Attempted to use an SV as a source in TABLES clause | Composable SVs are in Private Preview — use the underlying tables/views instead |

---

## Semantic correctness warnings — silent wrong results

These issues **do not produce errors at deploy time**. They cause wrong query results or Cortex Analyst refusals that are hard to diagnose after the fact. Phase 5 self-check audits for all of these.

| # | Issue | Symptom | Detection | Fix |
|---|-------|---------|-----------|-----|
| 1 | **Orphaned table** — table in TABLES but no RELATIONSHIP connects it | Query-time error: "dimension entity must be related to..." | Scan RELATIONSHIPS for each table alias | Add the missing relationship or remove the table |
| 2 | **Fan trap** — metric at coarser grain than dimension reachable only through child table | Query-time error: "dimension entity must have equal or lower granularity" | Check if metric's table connects to dim table only via bridge/child | Move metric to bridge-grain table |
| 3 | **Cardinality lie** — PK declared on a non-unique column | No error. Silently inflated numbers (fan-trap guard disabled) | `SELECT COUNT(*), COUNT(DISTINCT pk_col) FROM table` — mismatch = wrong PK | Declare PK on the actually-unique column |
| 4 | **Synonym overlap** — same synonym in multiple definitions | Cortex Analyst refuses: "term is ambiguous, could refer to X or Y" | Collect all synonyms; find duplicates | Scope synonyms uniquely per definition |
| 5 | **Wrong relationship direction** — dimension on LHS of REFERENCES | Deploy-time error: "referenced key must be primary key" | Check that RHS is always the PK/dimension table | Flip: `many(FK) REFERENCES one(PK)` |
| 6 | **Forgotten semi-additive** — SUM on snapshot data | No error. Numbers inflated by N× (days, periods counted) | Table/column comments mention snapshot/balance/headcount/inventory | Add `NON ADDITIVE BY (<time_dim> DESC)` |

### Pre-deployment audit questions

Ask these for every SV before deploying:

1. Does every table with 2+ date FKs have USING on all metrics?
2. Is every PK declaration the actually-unique column (not a FK)?
3. Is every SUM metric on flow data (not snapshot)?
4. Does every synonym appear in exactly one definition?
5. Does every table participate in at least one relationship?

---

## LABELS = (FILTER) — deployment notes

`LABELS = (FILTER)` went **GA May 5, 2026**. Accounts on older deployments will reject this syntax with a parse error.

**Behavior**: Marks a boolean fact or dimension as usable in WHERE clauses via the FILTER semantic hint. Cortex Analyst can then apply it as a predicate automatically.

**Fallback**: If not available on the target account, emit boolean expressions as plain facts/dimensions without the LABELS clause. They still work — Cortex Analyst can use boolean columns in WHERE clauses, but won't recognize them as dedicated "filter" semantic types.

**Feature probe pattern** (used in Phase 5 Step 5.0.5):
```sql
CREATE OR REPLACE SEMANTIC VIEW <db>.<schema>.__FILTER_PROBE
  TABLES ( <table> PRIMARY KEY (<pk>) )
  FACTS ( <alias>.probe LABELS = (FILTER) AS TRUE )
  COMMENT = 'probe';
DROP SEMANTIC VIEW IF EXISTS <db>.<schema>.__FILTER_PROBE;
```

---

## Verified queries — column reference behavior

When you write SQL inside `AI_VERIFIED_QUERIES`, the engine automatically transforms column references:

- **Write**: `SELECT customer_name, SUM(total_amount) FROM ...`
- **Engine stores**: `SELECT __orders.customer_name, SUM(__orders.total_amount) FROM ...`

The `__<table_alias>` prefix is added internally by the semantic view engine at verified query registration time. This is expected behavior.

**Rules for writing verified query SQL**:
- Write plain column names as you would in a normal SQL query against the semantic view
- Do NOT manually add `__table.` prefixes — the engine handles this
- Use the logical table alias (not source object name) when disambiguating: `orders.amount` not `MY_DB.MY_SCHEMA.ORDERS.AMOUNT`
- If the engine's auto-transform produces invalid SQL, the verified query will silently fail to match at query time — verify by running `SHOW SEMANTIC FACTS IN <sv>` and checking the verified query SQL
