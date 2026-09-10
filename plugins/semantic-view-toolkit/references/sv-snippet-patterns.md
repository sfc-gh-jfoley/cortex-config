# SV Snippet Pattern Catalog

Reference used by `sv-snippet-suggester`, `sv-ddl` (phases 03/04/05), and `sv-audit`.
One entry per pattern. Each entry: detection signals, the problem it solves, DDL key,
gotchas, and synonym discipline where relevant.

Source: https://github.com/Snowflake-Labs/coco-skills/tree/main/skills/semantic-view-patterns/snippets

## Live Examples (deployed to SNIPPETS.PUBLIC)

All 8 core patterns are deployed and verified in `SNIPPETS.PUBLIC`. When showing
a user a pattern, give them a working query they can run immediately.

| Pattern | SV Name | Sample Query |
|---------|---------|-------------|
| `semi_additive_metric` | `SNIPPETS.PUBLIC.ACCOUNT_BALANCES_SV` | `SELECT * FROM SEMANTIC_VIEW(SNIPPETS.PUBLIC.ACCOUNT_BALANCES_SV DIMENSIONS balances.balance_date METRICS balances.total_balance) ORDER BY balance_date;` |
| `range_join` | `SNIPPETS.PUBLIC.ORDERS_BY_SEGMENT` | `SELECT * FROM SEMANTIC_VIEW(SNIPPETS.PUBLIC.ORDERS_BY_SEGMENT DIMENSIONS customer_segments.segment METRICS orders.total_revenue) ORDER BY total_revenue DESC;` |
| `asof_join` | `SNIPPETS.PUBLIC.ORDERS_BY_ADDRESS` | `SELECT * FROM SEMANTIC_VIEW(SNIPPETS.PUBLIC.ORDERS_BY_ADDRESS DIMENSIONS Customer_address.zip METRICS Orders.total_revenue) ORDER BY zip;` |
| `accumulating_snapshot` | `SNIPPETS.PUBLIC.LOAN_PIPELINE_SV` | `SELECT * FROM SEMANTIC_VIEW(SNIPPETS.PUBLIC.LOAN_PIPELINE_SV DIMENSIONS date_dim.year, date_dim.month_num, date_dim.month_name METRICS applications.application_count, applications.review_count, applications.decision_count, applications.funding_count) ORDER BY year, month_num;` |
| `role_playing_dimensions` | `SNIPPETS.PUBLIC.ORDERS_RPD_SV` | `SELECT * FROM SEMANTIC_VIEW(SNIPPETS.PUBLIC.ORDERS_RPD_SV DIMENSIONS order_date_dim.order_month_name, ship_date_dim.ship_month_name METRICS orders.total_revenue) ORDER BY order_month_name, ship_month_name;` |
| `entity_facts` | `SNIPPETS.PUBLIC.CUSTOMER_ORDERS_SV` | `SELECT * FROM SEMANTIC_VIEW(SNIPPETS.PUBLIC.CUSTOMER_ORDERS_SV DIMENSIONS customers.value_segment METRICS orders.total_revenue, customers.customer_count) ORDER BY value_segment;` |
| `window_metrics` | `SNIPPETS.PUBLIC.DAILY_SALES_SV` | `SELECT * FROM SEMANTIC_VIEW(SNIPPETS.PUBLIC.DAILY_SALES_SV DIMENSIONS daily_sales.date METRICS daily_sales.total_revenue, daily_sales.rolling_7d_avg_revenue, daily_sales.ytd_revenue) ORDER BY date LIMIT 10;` |
| `derived_metrics` | `SNIPPETS.PUBLIC.CHANNEL_SALES_SV` | `SELECT * FROM SEMANTIC_VIEW(SNIPPETS.PUBLIC.CHANNEL_SALES_SV DIMENSIONS dim_date.month METRICS store_sales.store_revenue, web_sales.web_revenue, total_revenue) ORDER BY month;` |

## Known Bug in Upstream Repo

**`accumulating_snapshot/semantic_view.sql`** — The canonical file uses entity-prefixed
derived metrics (`applications.funding_rate AS DIV0(...)`) which Snowflake rejects.
Correct syntax removes the prefix: `funding_rate AS DIV0(applications.funding_count, ...)`.
The README documents the correct syntax; the SQL file has the bug. Tracked: tested
2026-09-10 against SNIPPETS.PUBLIC.LOAN_PIPELINE_SV.

---



## 1. semi_additive_metric

**Problem:** Fact table rows represent a snapshot in time (balance, headcount, inventory,
open pipeline). Summing across time double-counts — a $1,000 balance on Monday AND
Tuesday is still $1,000, not $2,000.

**Detection signals:**
- Table/column names: `BALANCE`, `HEADCOUNT`, `INVENTORY`, `OPEN_PIPELINE`, `SNAPSHOT`,
  `END_OF_DAY`, `PERIOD_END`, `MONTH_END`, `ON_HAND`
- Table comment contains: snapshot, point-in-time, as-of, balance, headcount, inventory
- A SUM metric on a table that also has a date column that represents "as of" not "occurred"

**DDL key:**
```sql
METRICS (
  -- NON ADDITIVE BY prevents cross-date sum. Always group/filter by balance_date.
  balances.total_balance NON ADDITIVE BY (balance_date) AS SUM(BALANCE_USD)
    WITH SYNONYMS ('current balance', 'balance as of date', 'snapshot balance',
                   'end of day balance', 'point in time balance')
    COMMENT = 'Sum across accounts for a given date. Always filter or group by date.',

  -- Separate metric for trend analysis — cannot compose with NON ADDITIVE
  balances.avg_daily_balance AS AVG(BALANCE_USD)
    WITH SYNONYMS ('average balance', 'average daily balance', 'balance trend',
                   'mean balance', 'typical balance')
)
```

**Gotchas:**
- Cannot apply AVG() to a NON ADDITIVE metric — they are separate metric definitions
- NON ADDITIVE BY only works with SUM, AVG, MIN, MAX — never COUNT or COUNT DISTINCT
- Querying total_balance without a balance_date dimension returns per-date subtotals, not a grand total
- `AI_SQL_GENERATION` should instruct: "Never use total_balance without balance_date dimension or WHERE filter"

**Synonym discipline:** Keep `total_balance` synonyms explicitly point-in-time ("as of",
"snapshot", "on hand"). Keep `avg_daily_balance` synonyms explicitly trend-oriented ("average",
"trend", "typical"). Never share "balance" between them without a qualifier.

**What cannot be materialized:** Semi-additive metrics (NON ADDITIVE BY) cannot be materialized.

---

## 2. range_join

**Problem:** Dimension table has SCD2 history — each row has VALID_FROM and VALID_TO.
Fact events must be attributed to the dimension version active at event time.

**Detection signals:**
- Column pairs: `VALID_FROM`+`VALID_TO`, `START_DATE`+`END_DATE`, `EFFECTIVE_DATE`+`EXPIRY_DATE`,
  `BEGIN_DATE`+`END_DATE`
- Table names containing: `_HISTORY`, `_SCD`, `_SEGMENTS`, `_TIERS`
- Comments mentioning: historical, SCD2, temporal, slowly changing

**DDL key:**
```sql
TABLES (
  customer_segments AS DB.SCHEMA.CUSTOMER_SEGMENTS
    PRIMARY KEY (SEGMENT_ID)
    UNIQUE (CUSTOMER_ID, VALID_FROM, VALID_TO)
    CONSTRAINT segment_period DISTINCT RANGE BETWEEN VALID_FROM AND VALID_TO EXCLUSIVE
)
RELATIONSHIPS (
  orders_to_segment AS orders(CUSTOMER_ID, ORDER_DATE)
    REFERENCES customer_segments(CUSTOMER_ID, BETWEEN VALID_FROM AND VALID_TO EXCLUSIVE)
)
```

**Gotchas:**
- VALID_TO must be EXCLUSIVE (first day NOT active). Inclusive end dates need `valid_to + INTERVAL 1 DAY` in a view.
- DISTINCT RANGE requires both columns to be the same type (DATE/TIMESTAMP/NUMBER)
- Entity isolation: dimensions from the range-joined table can only be used with metrics
  that have a direct join path to that table. Cross-entity metric+dimension pairs that
  only connect through the range join will error.
- Type compatibility: if ORDER_DATE is DATE and VALID_FROM/TO are TIMESTAMP_NTZ, add a
  PRIVATE FACT with a cast: `PRIVATE orders.order_ts AS ORDER_DATE::TIMESTAMP_NTZ`

---

## 3. asof_join

**Problem:** Dimension table has only a start date (no explicit end date). Need "the
most recent record whose start date is on or before the event date."

**Detection signals:**
- Single temporal column in a lookup/history table with no companion end date:
  `EFFECTIVE_DATE`, `AS_OF_DATE`, `VALID_FROM`, `PRICE_DATE`, `RATE_DATE`, `SNAPSHOT_DATE`
- Table names: `*_RATES`, `*_PRICES`, `*_CONFIG`, `*_HISTORY` with low row counts per entity

**DDL key:**
```sql
TABLES (
  customer_address AS DB.SCHEMA.CUSTOMER_ADDRESS
    -- UNIQUE on (entity_key, start_date) required — no end date needed
    UNIQUE (ca_custid, ca_start_date)
)
RELATIONSHIPS (
  orders_to_addr AS orders(o_custid, o_orddate)
    REFERENCES customer_address(ca_custid, ASOF ca_start_date)
)
```

**vs range_join:** Use ASOF when the dimension has only a start date.
Use range_join when it has explicit start+end dates (BETWEEN ... EXCLUSIVE).

---

## 4. accumulating_snapshot

**Problem:** Business pipeline (loan origination, hiring, claims) where each entity
moves through sequential milestone stages, each with its own date. Need per-stage
metrics that bucket by the correct date for each stage.

**Detection signals:**
- Multiple date columns representing stages: `APPLICATION_DATE`, `REVIEW_DATE`,
  `DECISION_DATE`, `FUNDING_DATE` — or any set of `*_DATE` cols implying a funnel
- Business context mentions: funnel, pipeline, stages, milestones, conversion rates

**DDL key:**
```sql
TABLES (
  applications AS DB.SCHEMA.LOAN_APPLICATIONS  PRIMARY KEY (APPLICATION_ID),
  date_dim AS DB.SCHEMA.DIM_DATE PRIMARY KEY (DATE_KEY)
    -- Single date_dim alias serves all milestone paths
)
RELATIONSHIPS (
  app_to_application_date AS applications(APPLICATION_DATE) REFERENCES date_dim(DATE_KEY),
  app_to_review_date      AS applications(REVIEW_DATE)      REFERENCES date_dim(DATE_KEY),
  app_to_decision_date    AS applications(DECISION_DATE)    REFERENCES date_dim(DATE_KEY),
  app_to_funding_date     AS applications(FUNDING_DATE)     REFERENCES date_dim(DATE_KEY)
)
METRICS (
  -- USING (relationship) BEFORE AS — not after
  applications.application_count USING (app_to_application_date) AS COUNT(APPLICATION_ID),
  applications.review_count      USING (app_to_review_date)      AS COUNT(REVIEW_DATE),
  applications.decision_count    USING (app_to_decision_date)    AS COUNT(DECISION_DATE),
  applications.funding_count     USING (app_to_funding_date)     AS COUNT(FUNDING_DATE)
)
```

**Gotchas:**
- `USING` clause syntax: `USING (rel_name) AS aggregate_expr` — USING comes BEFORE AS
- Derived metrics referencing USING-scoped metrics MUST have NO entity prefix on left side.
  This is enforced by Snowflake — the engine rejects: "Metric defined with using relationship
  cannot be referenced in the definition of 'ENTITY.METRIC_NAME'. Only derived metrics can
  refer to metrics defined with using relationship."
  `funding_rate AS DIV0(applications.funding_count, applications.application_count)` ✓
  `applications.funding_rate AS DIV0(...)` ✗ — runtime error
- NULL milestone dates produce a NULL dimension row (expected LEFT JOIN behavior)
- This is NOT cohort analysis — conversion rates are same-period ratios, not "of Jan applications how many eventually funded"

**vs role_playing_dimensions:** Use accumulating_snapshot+USING when metrics must use
different date paths. Use role_playing_dimensions when you need both date attributes
simultaneously in one query (cross-tab).

---

## 5. role_playing_dimensions

**Problem:** Fact table has two+ FK date columns pointing to the same physical DIM_DATE
table. Need ORDER_YEAR and SHIP_YEAR as independent, simultaneously queryable dimensions.

**Detection signals:**
- Two columns in the same fact table both ending in `_DATE` (e.g. ORDER_DATE, SHIP_DATE)
  or `_AT` that both represent calendar dates
- A single DIM_DATE / CALENDAR table in the schema

**DDL key:**
```sql
TABLES (
  orders          AS DB.SCHEMA.ORDERS     PRIMARY KEY (ORDER_ID),
  order_date_dim  AS DB.SCHEMA.DIM_DATE   PRIMARY KEY (DATE_KEY),  -- role 1
  ship_date_dim   AS DB.SCHEMA.DIM_DATE   PRIMARY KEY (DATE_KEY)   -- role 2: same physical table
)
RELATIONSHIPS (
  orders_to_order_date AS orders(ORDER_DATE) REFERENCES order_date_dim(DATE_KEY),
  orders_to_ship_date  AS orders(SHIP_DATE)  REFERENCES ship_date_dim(DATE_KEY)
)
DIMENSIONS (
  order_date_dim.order_year       AS YEAR,
  order_date_dim.order_month_name AS MONTH_NAME,
  ship_date_dim.ship_year         AS YEAR,        -- same physical col, unique logical name
  ship_date_dim.ship_month_name   AS MONTH_NAME
)
```

**Gotchas:**
- All logical dimension names must be globally unique: `order_year` ≠ `ship_year` ✓
  — `year` in both aliases = deploy error
- Grouping by both roles simultaneously produces a cross-tab (one row per combination)
- DIM_DATE must cover the full date range of the fact table or LEFT JOIN produces NULLs
- No `USING` needed — each alias has its own unique dimension names

---

## 6. multi_path_metrics

**Problem:** Two FKs from the same fact table reference the same physical dimension table
(different roles: departure city, arrival city). Need separate metrics for each path.
Without disambiguation: "Multi-path relationship ... not supported" error at query time.

**Detection signals:**
- Two relationships in the SV both referencing the same physical table via different FKs
- Error: "Multi-path relationship between dimension entity X and base metric entity Y"

**DDL key:**
```sql
RELATIONSHIPS (
  flight_departure_weather AS flights(departure_city, departure_time)
    REFERENCES weather(city_code, BETWEEN start_date AND end_date EXCLUSIVE),
  flight_arrival_weather AS flights(arrival_city, arrival_time)
    REFERENCES weather(city_code, BETWEEN start_date AND end_date EXCLUSIVE)
)
METRICS (
  flights.m_late_departure_count AS COUNT_IF(is_late)
    USING (flight_departure_weather)
    WITH SYNONYMS ('late flights by departure weather'),
  flights.m_late_arrival_count AS COUNT_IF(is_late)
    USING (flight_arrival_weather)
    WITH SYNONYMS ('late flights by arrival weather')
)
```

**vs role_playing_dimensions:**
- Use `multi_path_metrics` + USING when the dimension column is shared (weather_condition)
  and disambiguation is at the metric level
- Use `role_playing_dimensions` when you need ORDER_YEAR and SHIP_YEAR as independent dims
  in the same query

---

## 7. time_intelligence

**Problem:** Need SPLY (same period last year), MoM (month-over-month), YoY
comparison without window functions or pre-aggregated tables.

**Detection signals:**
- Business context: SPLY, YoY, MoM, QoQ, prior period, year over year, same period last year
- A calendar/date dimension table is available
- Monthly or quarterly grain data

**DDL key — role alias + shifted FACT join key:**
```sql
TABLES (
  sales    AS DB.SCHEMA.FACT_SALES PRIMARY KEY (ROW_ID),
  sales_ly AS DB.SCHEMA.FACT_SALES PRIMARY KEY (ROW_ID),  -- same table, LY alias
  sales_lm AS DB.SCHEMA.FACT_SALES PRIMARY KEY (ROW_ID),  -- same table, LM alias
  calendar AS DB.SCHEMA.DIM_CALENDAR PRIMARY KEY (MONTH)
)
FACTS (
  -- Computed shift keys for joining LY/LM aliases to current calendar periods
  sales_ly.sale_month_shifted_ly AS DATEADD('year',  1, SALE_MONTH),
  sales_lm.sale_month_shifted_lm AS DATEADD('month', 1, SALE_MONTH)
)
RELATIONSHIPS (
  sales_to_calendar    AS sales(SALE_MONTH)                   REFERENCES calendar(MONTH),
  sales_ly_to_calendar AS sales_ly(sale_month_shifted_ly)     REFERENCES calendar(MONTH),
  sales_lm_to_calendar AS sales_lm(sale_month_shifted_lm)     REFERENCES calendar(MONTH)
)
METRICS (
  sales.revenue          AS SUM(AMOUNT),
  sales_ly.revenue_ly    AS SUM(AMOUNT),
  sales_lm.revenue_lm    AS SUM(AMOUNT),
  -- Cross-entity derived: no table prefix on left side
  yoy_pct AS DIV0(sales.revenue - sales_ly.revenue_ly, sales_ly.revenue_ly) * 100,
  mom_pct AS DIV0(sales.revenue - sales_lm.revenue_lm, sales_lm.revenue_lm) * 100
)
```

**Gotchas:**
- LY/LM metrics are NULL for boundary periods (no prior-year data in first year)
- This pattern gives point-in-time period comparisons, NOT cumulative YTD
- For YTD, use `window_metrics` with `SUM OVER (PARTITION BY year ... ROWS UNBOUNDED PRECEDING)`
- The shift is a full period — partial periods need calendar filtering outside the SV

---

## 8. window_metrics

**Problem:** Metrics that span time: rolling averages, YTD running totals, LAG
for prior-period comparison, RANK.

**Detection signals:**
- Business context: rolling average, 7-day, moving average, running total, YTD,
  cumulative, rank, percentile, LAG, period-over-period
- Phase 3 `WINDOW_METRIC_CANDIDATES` populated

**DDL key — three patterns:**
```sql
METRICS (
  -- 1. Rolling 7-day average
  daily_sales.rolling_7d_avg AS
    AVG(total_revenue)
    OVER (PARTITION BY EXCLUDING daily_sales.date
          ORDER BY daily_sales.date
          RANGE BETWEEN INTERVAL '6 days' PRECEDING AND CURRENT ROW),

  -- 2. LAG — prior period comparison
  daily_sales.revenue_30d_ago AS
    LAG(total_revenue, 30)
    OVER (PARTITION BY EXCLUDING daily_sales.date
          ORDER BY daily_sales.date),

  -- 3. YTD — resets each year
  daily_sales.ytd_revenue AS
    SUM(total_revenue)
    OVER (PARTITION BY daily_sales.year
          ORDER BY daily_sales.date
          ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
)
```

**Critical gotcha — PARTITION BY EXCLUDING + FACTS:**
If the inner metric references a column declared in the FACTS clause, `PARTITION BY EXCLUDING`
will fail: "PARTITION BY EXCLUDING is not allowed when the window function operates over a
row-level expression."
Fix: Remove the column from FACTS and reference it by bare physical column name in the metric.
```sql
-- WRONG: balance_usd declared in FACTS, then used in window metric
-- RIGHT: omit from FACTS; reference as bare column name in SUM(BALANCE_USD)
```

**Other gotchas:**
- Window metrics must include their ORDER BY dimension in the DIMENSIONS clause at query time
- `PARTITION BY EXCLUDING` removes the specified dim from the partition (dynamic — adding
  more dims applies the window per-group automatically)
- Cannot use window metrics in materializations

---

## 9. derived_metrics

**Problem:** Cross-entity totals, ratios, percent-of-total from metrics on different tables.

**Detection signals:**
- Multiple fact tables in the SV
- User asks for "total across channels", "net revenue", "% of total"

**DDL key:**
```sql
METRICS (
  store_sales.store_revenue  AS SUM(revenue),
  web_sales.web_revenue      AS SUM(revenue),
  -- Cross-table: NO entity prefix on left side of derived metric name
  total_revenue AS store_sales.store_revenue + web_sales.web_revenue,
  store_pct     AS store_sales.store_revenue / total_revenue,
  net_revenue   AS total_revenue - channel_returns.total_returns
)
```

**Gotchas:**
- Derived metric names MUST NOT have an entity prefix on the left side
- A derived metric can reference other derived metrics as building blocks
- Division returns 0.0–1.0 decimal — multiply × 100 in standard SQL wrapper for display as %
- Derived metrics do NOT support NON ADDITIVE BY

---

## 10. entity_facts

**Problem:** Need entity-level analytics (customer LTV, value tier) without a separate
pre-computed table. LTV requires aggregating orders up to the customer level.

**Detection signals:**
- "segment customers by total spend", "lifetime value", "value tier", "derived age"
- Entity-level aggregation needed across a child table

**DDL key:**
```sql
FACTS (
  -- PRIVATE: not queryable directly; used only in DIMENSIONS expressions
  PRIVATE customers.lifetime_value AS SUM(orders.order_amount)
)
DIMENSIONS (
  customers.value_segment AS (
    CASE
      WHEN customers.lifetime_value < 1000  THEN 'low'
      WHEN customers.lifetime_value <= 3000 THEN 'medium'
      ELSE                                       'high'
    END
  ),
  customers.age AS (YEAR(CURRENT_DATE()) - birth_year)
)
```

**PRIVATE vs public facts:** PRIVATE facts are usable in DIMENSIONS expressions but
not directly queryable. Use PRIVATE when the fact is an intermediate computation only.

---

## 11. fact_as_relationship_key

**Problem:** FK doesn't exist as a physical column on the fact table — it must be
derived (e.g., fiscal quarter from sale_date).

**Detection signals:**
- Dimension table keyed by computed/composite value (fiscal_quarter_key, region_code)
- Fact table has the raw components (sale_date) but not the derived key

**DDL key:**
```sql
FACTS (
  -- Computed key — scalar (row-level) expression only, NOT an aggregate
  sales.fiscal_qtr_key AS CONCAT(TO_VARCHAR(YEAR(sale_date)), '-Q', TO_VARCHAR(QUARTER(sale_date)))
)
RELATIONSHIPS (
  sales_to_quarters AS sales(sales.fiscal_qtr_key) REFERENCES fiscal_quarters
)
```

**Gotchas:**
- The computed fact is NOT queryable directly as a dimension or metric
- Must be a scalar (row-level) expression — aggregates (SUM, COUNT) are invalid
- Referenced table must have a matching PRIMARY KEY

---

## 12. multi_fact_table

**Problem:** Multiple independent fact tables (store_sales, web_sales, returns) that
should share common dimensions (product, date) and allow cross-fact derived metrics.

**Detection signals:**
- Multiple fact tables in the schema that share dimension tables
- User wants "total across channels" or "net revenue"

**DDL key:**
```sql
TABLES (
  dim_product           PRIMARY KEY (product_id),
  channel_dim_date      PRIMARY KEY (date_id),
  channel_store_sales,
  channel_web_sales,
  channel_returns
)
RELATIONSHIPS (
  store_to_date    AS channel_store_sales(date_id)    REFERENCES channel_dim_date,
  store_to_product AS channel_store_sales(product_id) REFERENCES dim_product,
  web_to_date      AS channel_web_sales(date_id)      REFERENCES channel_dim_date,
  web_to_product   AS channel_web_sales(product_id)   REFERENCES dim_product,
  returns_to_date  AS channel_returns(date_id)        REFERENCES channel_dim_date
)
METRICS (
  channel_store_sales.store_revenue AS SUM(revenue),
  channel_web_sales.web_revenue     AS SUM(revenue),
  channel_returns.total_returns     AS SUM(return_amount),
  total_gross_revenue AS channel_store_sales.store_revenue + channel_web_sales.web_revenue,
  net_revenue         AS total_gross_revenue - channel_returns.total_returns
)
```

**Key behavior:** Querying only `store_revenue` does NOT join `channel_web_sales`.
`SHOW SEMANTIC DIMENSIONS FOR METRIC store_revenue` shows only dims reachable via store_sales.

---

## 13. shared_degenerate_dimension

**Problem:** Two+ fact tables have the same categorical column (region, status) with
no dedicated dimension table. Need a single dimension that works across all facts.

**Detection signals:**
- Same column name (e.g., REGION, STATUS, COUNTRY) appears on multiple fact tables
- No corresponding DIM_REGION or DIM_STATUS table exists

**DDL key:**
```sql
-- Step 1: helper UNION view (or inline SQL in TABLES)
CREATE VIEW region_dim AS
    SELECT DISTINCT region FROM store_orders
    UNION
    SELECT DISTINCT region FROM web_orders;

-- Step 2: UNIQUE entity in TABLES
TABLES (
  regions AS region_dim UNIQUE (region),
  store_orders,
  web_orders
)
RELATIONSHIPS (
  store_to_region AS store_orders(region) REFERENCES regions,
  web_to_region   AS web_orders(region)   REFERENCES regions
)
```

**Inline SQL alternative (Private Preview):**
```sql
regions AS (
  SELECT DISTINCT region FROM store_orders
  UNION
  SELECT DISTINCT region FROM web_orders
) UNIQUE (region)
```

---

## 14. ai_metadata

**Problem:** Need to steer Cortex Analyst SQL generation style, define question
boundaries, or pre-approve SQL for high-frequency questions.

**Detection signals:**
- User mentions "always filter by status", "don't answer questions about PII",
  "pre-approve this query", VQRs
- Business context contains implicit filtering rules

**DDL key:**
```sql
AI_SQL_GENERATION 'Always round monetary values to 2 decimal places.
When asked about revenue, never include orders with status = ''refunded''.'

AI_QUESTION_CATEGORIZATION 'Answer questions about revenue, orders, and customers.
Politely decline questions about PII or internal cost structure.'

AI_VERIFIED_QUERIES (
  order_count_by_customer AS (
    QUESTION 'How many orders does each customer have?'
    VERIFIED_BY 'analyst_name'
    VERIFIED_AT 1750000000
    SQL 'SELECT * FROM SEMANTIC_VIEW(
           DB.SCHEMA.MY_SV
           METRICS orders.order_count
           DIMENSIONS customers.customer_name
         ) ORDER BY order_count DESC'
  )
)
```

**VQR format:** Always use `SEMANTIC_VIEW()` format in VQRs, not physical SQL —
works in both AUTO and REQUIRE modes.

---

## 15. variables

**Problem:** Metric/dimension calculation depends on a user-defined threshold or
weight that shouldn't be hard-coded.

**Detection signals:**
- "adjustable threshold", "scoring weights", "dynamic", "parameterized"
- Different teams/use cases need different values from the same SV

**DDL key:**
```sql
VARIABLES (
  premium_threshold NUMBER(10,2) DEFAULT 500.00,
  rating_weight     NUMBER(3,2)  DEFAULT 0.6
)
DIMENSIONS (
  products.price_tier AS (
    CASE WHEN unit_price >= premium_threshold THEN 'premium'
         WHEN unit_price >= 200              THEN 'standard'
         ELSE                                     'budget' END
  )
)
-- At query time:
-- VARIABLES premium_threshold => 400.00
```

**Gotchas:**
- Variables can only be used in DIMENSIONS, METRICS, FACTS expressions
- Variables CANNOT be used in TABLES or RELATIONSHIPS clauses
- If DEFAULT is omitted, the variable MUST be supplied at every SEMANTIC_VIEW() call

---

## 16. scoped_dataset  ⚠️ Private Preview

**Problem:** One source table contains data for multiple LOBs/regions/tenants.
Need separate SVs scoped to each subset without creating intermediate tables.

**DDL key:**
```sql
TABLES (
  orders AS (
    SELECT * FROM DB.SCHEMA.SALES_TRANSACTIONS WHERE lob = 'Retail'
  ) PRIMARY KEY (transaction_id)
)
```

**Gotchas:**
- Alias is REQUIRED when using `AS (...)`
- Session variables (`$var`) cannot be used in the inline query
- Filter is embedded in DDL — changing requires `CREATE OR REPLACE SEMANTIC VIEW`
- `DESCRIBE SEMANTIC VIEW` shows inline query in DEFINITION property (not BASE_TABLE_NAME)
- ⚠️ Private Preview — requires account-team enablement

---

## 17. inline_sv  ⚠️ Private Preview

**Problem:** Testing DDL before committing, dbt unit tests, rapid prototyping.

**DDL key:**
```sql
WITH adhoc_sv AS SEMANTIC VIEW
TABLES (
  orders,
  customers UNIQUE (customer_id)
)
RELATIONSHIPS (
  orders(customer_id) REFERENCES customers
)
...
SELECT * FROM SEMANTIC_VIEW(adhoc_sv DIMENSIONS ... METRICS ...);
```

**Note:** Not usable with Cortex Analyst. ⚠️ Private Preview.

---

## 18. materialization  ⚠️ Private Preview

**Problem:** SV queries scan large base tables on every request. Pre-aggregate
selected dimension/metric combinations.

**DDL key:**
```sql
-- 1. Set MAX_STALENESS on the SV (minimum 120 seconds)
CREATE SEMANTIC VIEW my_sv ... MAX_STALENESS = '1 hour';

-- 2. Grant privilege
GRANT ADD SEMANTIC VIEW MATERIALIZATION ON SCHEMA db.schema TO ROLE my_role;

-- 3. Add materialization
ALTER SEMANTIC VIEW my_sv ADD MATERIALIZATION revenue_by_customer
  WAREHOUSE = my_wh
  IMMUTABLE WHERE (order_date < '2024-01-01')  -- strongly recommended for historical data
  AS
    DIMENSIONS mat_customers.customer_name, mat_orders.order_year
    METRICS mat_orders.total_revenue;
```

**Cannot be materialized:** Window metrics, semi-additive (NON ADDITIVE BY) metrics,
metrics with USING clause, AVG/COUNT DISTINCT/MEDIAN/PERCENTILE.

**⚠️ Private Preview — requires account-team enablement.**

---

## 19. caller_rights

**Problem:** Base tables have row-level security / column masking policies. Need
the SV to respect the caller's permissions rather than bypassing them via owner rights.

**Detection signals:**
- "row-level security should apply through the SV"
- "caller's policies should apply"
- "SV should not bypass table-level permissions"

**Pattern (not a DDL clause — an RBAC design):**
```sql
-- SV_CREATOR creates the SV (needs base table access to define it)
-- FUTURE GRANT immediately transfers ownership to SV_OWNER
GRANT OWNERSHIP ON FUTURE SEMANTIC VIEWS IN SCHEMA DB.SV TO ROLE SV_OWNER;
-- SV_OWNER owns the SV but has NO access to base tables in DB.DATA schema
-- → queries only succeed if the CALLER has base table access
-- → row/column policies on base tables apply to the caller's role
```

**Gotcha:** `USE SECONDARY ROLES ALL` can grant unexpected access. Test with
`USE SECONDARY ROLES NONE`.

---

## 20. row_access_policies

**Problem:** RAP on a dimension table causes NULL rows in SEMANTIC_VIEW() output,
leaking fact-level metrics for hidden dimensions.

**Detection signals:**
- RAP applied to a dimension table; NULL row appears in SV output with metric values
- User reports data leakage even though dimension values are hidden

**Fix — two options:**
```sql
-- Option A (preferred): apply RAP to the fact table instead of the dimension table
ALTER TABLE DB.SCHEMA.ORDERS
  ADD ROW ACCESS POLICY region_access_policy ON (REGION_ID);

-- Option B: helper view with INNER JOIN (drop orphaned fact rows before SV)
CREATE VIEW orders_filtered AS
  SELECT o.* FROM orders o
  INNER JOIN sales_regions r ON o.region_id = r.region_id;
-- Use orders_filtered as the fact entity in the SV
```

**Anti-pattern:** RAP on dimension table only → LEFT JOIN semantics → NULL rows with
leaked metric values. NEVER rely on AI_SQL_GENERATION instructions as a security boundary.

---

## 21. introspection

**Key commands:**
```sql
DESCRIBE SEMANTIC VIEW DB.SCHEMA.MY_SV;
SHOW SEMANTIC VIEWS IN DB.SCHEMA;
SHOW SEMANTIC METRICS IN DB.SCHEMA.MY_SV;
-- Critical for multi-fact SVs: which dims are compatible with this metric?
SHOW SEMANTIC DIMENSIONS IN DB.SCHEMA.MY_SV FOR METRIC entity.metric_name;
-- Lineage
SELECT * FROM TABLE(SNOWFLAKE.CORE.GET_LINEAGE('DB.SCHEMA.MY_SV', 'SEMANTIC_VIEW', 'UPSTREAM', 5));
SELECT * FROM TABLE(SNOWFLAKE.CORE.GET_LINEAGE('DB.SCHEMA.MY_SV', 'SEMANTIC_VIEW', 'DOWNSTREAM', 5));
```

---

## 22. sv_diagnostics

**Pre-deployment checklist — run mentally on every new SV:**

- [ ] Every fact table with 2+ date FKs: does every metric have `USING`?
- [ ] Every table in TABLES: does it appear in at least one RELATIONSHIP?
- [ ] Every metric: defined at the same or lower grain as its breakout dimensions?
- [ ] Every logical name in DIMENSIONS/METRICS: globally unique within the SV?
- [ ] Every synonym: appears in only one definition? (Especially: revenue, count, total, date, area, segment)
- [ ] Every RELATIONSHIP: `many_side(FK) REFERENCES one_side(PK)` direction?
- [ ] Every PRIMARY KEY declaration: actually unique in that table? (not a FK to a parent)
- [ ] Every SUM metric: flow (ok) or snapshot (needs NON ADDITIVE BY)?

**Cardinality lie (most dangerous — no error, silent inflation):**
```sql
-- Detect: SV total should match raw SQL total
SELECT SUM(amount) FROM DEALS;  -- must equal SV total_amount with no grouping
```
If they don't match, a PRIMARY KEY is declared on a non-unique column.

---

## 23. system_explain_semantic_query

**When to use:** Query fails with `invalid identifier` or metric values look wrong.

```sql
SELECT SYSTEM$EXPLAIN_SEMANTIC_QUERY(
  'DB.SCHEMA.MY_SV',
  $$
  SELECT sv.* FROM SEMANTIC_VIEW(
    DB.SCHEMA.MY_SV
    METRICS entity.my_metric
    DIMENSIONS entity.my_dimension
  ) AS sv
  $$
);
```

Returns the exact SQL the engine would generate — without executing it.
Only accepts `SEMANTIC_VIEW()` query syntax, not general SQL.

---

## 24. standard_sql

**When to use:** Tableau / dbt / BI tools that query the SV with plain SELECT.

```sql
-- Must wrap metric in ANY_VALUE() when combined with non-metric columns
SELECT
  month,
  ANY_VALUE(total_revenue) AS revenue
FROM DB.SCHEMA.MY_SV
WHERE year = 2024
GROUP BY ALL
ORDER BY month;

-- Dimensions only — no wrapper needed, no GROUP BY needed
SELECT DISTINCT customer_name FROM DB.SCHEMA.MY_SV;

-- Metric only — no wrapper needed
SELECT total_revenue FROM DB.SCHEMA.MY_SV WHERE customer_id = 'C001';
```

---

## 25. tags

**When to use:** Governance — track ownership, certification status, lifecycle.

```sql
-- Step 1: create tag objects
CREATE TAG metric_owner;
CREATE TAG metric_status;

-- Step 2: apply in METRICS block
METRICS (
  store_sales.store_revenue AS SUM(revenue)
    WITH SYNONYMS ('store revenue')
    WITH TAG (metric_owner = 'finance_team', metric_status = 'certified')
    COMMENT = '...'
)

-- Step 3: query via tag_references()
SELECT OBJECT_NAME, TAG_NAME, TAG_VALUE
FROM TABLE(DB.INFORMATION_SCHEMA.TAG_REFERENCES(
  'DB.SCHEMA.MY_SV!ENTITY_TABLE.METRIC_LOGICAL_NAME',
  'semantic metric'
));
```
