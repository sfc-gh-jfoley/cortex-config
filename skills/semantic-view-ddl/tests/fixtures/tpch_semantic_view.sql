-- =============================================================================
-- TPCH Semantic View — E2E Test Fixture
-- Uses SNOWFLAKE_SAMPLE_DATA.TPCH_SF1 tables exclusively.
-- Expected result: sv_validator.py passes 17/17 checks (+ overall_summary = 18/18)
-- =============================================================================

CREATE OR REPLACE SEMANTIC VIEW MY_DB.ANALYTICS.TPCH_REVENUE_SV
  TABLES (
    orders AS SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.ORDERS
      PRIMARY KEY (O_ORDERKEY)
      WITH SYNONYMS = ('sales orders', 'purchase orders')
      COMMENT = 'Customer orders with total price and status',

    customers AS SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.CUSTOMER
      PRIMARY KEY (C_CUSTKEY)
      WITH SYNONYMS = ('clients', 'buyers')
      COMMENT = 'Customer master data including market segment and nation',

    line_items AS SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.LINEITEM
      PRIMARY KEY (L_ORDERKEY, L_LINENUMBER)
      COMMENT = 'Individual line items within each order',

    parts AS SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.PART
      PRIMARY KEY (P_PARTKEY)
      WITH SYNONYMS = ('products', 'items')
      COMMENT = 'Parts catalog with brand, type, and size information',

    suppliers AS SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.SUPPLIER
      PRIMARY KEY (S_SUPPKEY)
      WITH SYNONYMS = ('vendors')
      COMMENT = 'Supplier master data including nation and account balance',

    nations AS SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.NATION
      PRIMARY KEY (N_NATIONKEY)
      COMMENT = 'Nation reference table with region assignment',

    regions AS SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.REGION
      PRIMARY KEY (R_REGIONKEY)
      COMMENT = 'Region reference table (Africa, Americas, Asia, Europe, Middle East)'
  )

  RELATIONSHIPS (
    orders_to_customers AS orders (O_CUSTKEY) REFERENCES customers,
    lineitem_to_orders AS line_items (L_ORDERKEY) REFERENCES orders,
    lineitem_to_parts AS line_items (L_PARTKEY) REFERENCES parts,
    supplier_to_nation AS suppliers (S_NATIONKEY) REFERENCES nations,
    nation_to_region AS nations (N_REGIONKEY) REFERENCES regions,
    customer_to_nation AS customers (C_NATIONKEY) REFERENCES nations
  )

  FACTS (
    line_items.L_QUANTITY AS L_QUANTITY
      WITH SYNONYMS = ('quantity', 'qty')
      COMMENT = 'Quantity of the line item ordered',

    line_items.L_EXTENDEDPRICE AS L_EXTENDEDPRICE
      WITH SYNONYMS = ('extended price', 'line price')
      COMMENT = 'Extended price before discount (quantity * part price)',

    line_items.L_DISCOUNT AS L_DISCOUNT
      WITH SYNONYMS = ('discount rate', 'rebate')
      COMMENT = 'Discount percentage applied to the line item',

    line_items.L_TAX AS L_TAX
      COMMENT = 'Tax rate applied to the line item',

    orders.O_TOTALPRICE AS O_TOTALPRICE
      WITH SYNONYMS = ('order total', 'order value')
      COMMENT = 'Total price of the entire order',

    line_items.discounted_price AS L_EXTENDEDPRICE * (1 - L_DISCOUNT)
      COMMENT = 'Line item price after applying discount'
  )

  DIMENSIONS (
    orders.O_ORDERDATE AS O_ORDERDATE
      WITH SYNONYMS = ('order date', 'date ordered')
      COMMENT = 'Date the order was placed',

    orders.order_year AS YEAR(O_ORDERDATE)
      COMMENT = 'Calendar year the order was placed',

    orders.O_ORDERSTATUS AS O_ORDERSTATUS
      WITH SYNONYMS = ('order status', 'status')
      COMMENT = 'Current order status: O (Open), F (Fulfilled), P (Partial)',

    customers.C_NAME AS C_NAME
      WITH SYNONYMS = ('customer name', 'client name')
      COMMENT = 'Full name of the customer',

    customers.C_MKTSEGMENT AS C_MKTSEGMENT
      WITH SYNONYMS = ('market segment', 'segment')
      COMMENT = 'Market segment the customer belongs to',

    nations.N_NAME AS N_NAME
      WITH SYNONYMS = ('nation', 'country')
      COMMENT = 'Nation name from the nation reference table',

    regions.R_NAME AS R_NAME
      WITH SYNONYMS = ('region', 'geographic region')
      COMMENT = 'Region name (Africa, Americas, Asia, Europe, Middle East)',

    parts.P_NAME AS P_NAME
      WITH SYNONYMS = ('part name', 'product name')
      COMMENT = 'Name of the part or product',

    parts.P_BRAND AS P_BRAND
      WITH SYNONYMS = ('brand')
      COMMENT = 'Brand of the part',

    orders.O_ORDERPRIORITY AS O_ORDERPRIORITY
      WITH SYNONYMS = ('priority', 'order priority')
      COMMENT = 'Order priority level (1-URGENT through 5-LOW)',

    line_items.L_SHIPDATE AS L_SHIPDATE
      WITH SYNONYMS = ('ship date', 'shipping date')
      COMMENT = 'Date the line item was shipped'
  )

  METRICS (
    orders.total_revenue AS SUM(O_TOTALPRICE)
      WITH SYNONYMS = ('revenue', 'total sales')
      COMMENT = 'Sum of all order values',

    orders.order_count AS COUNT(DISTINCT O_ORDERKEY)
      WITH SYNONYMS = ('number of orders')
      COMMENT = 'Count of distinct orders',

    orders.avg_order_value AS AVG(O_TOTALPRICE)
      WITH SYNONYMS = ('average order value', 'AOV')
      COMMENT = 'Average value per order',

    line_items.total_quantity AS SUM(L_QUANTITY)
      WITH SYNONYMS = ('total qty', 'quantity sold')
      COMMENT = 'Sum of all line item quantities'
  )

  COMMENT = 'TPC-H revenue and customer analytics semantic view covering orders, line items, parts, suppliers, nations, and regions'

  AI_SQL_GENERATION 'Always filter orders by O_ORDERSTATUS when a status is mentioned. Use O_ORDERDATE for all time-based filtering. Prefer COUNT(DISTINCT O_ORDERKEY) for unique order counts. Use C_MKTSEGMENT for segment analysis. Use N_NAME and R_NAME for geographic breakdowns.'

  AI_VERIFIED_QUERIES (
    top_customers_by_revenue AS (
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
    ),
    revenue_by_region AS (
      QUESTION 'What is revenue by region?'
      ONBOARDING_QUESTION TRUE
      SQL 'SELECT R_NAME, SUM(O_TOTALPRICE) AS revenue
           FROM orders
           JOIN customers ON O_CUSTKEY = C_CUSTKEY
           JOIN nations ON C_NATIONKEY = N_NATIONKEY
           JOIN regions ON N_REGIONKEY = R_REGIONKEY
           GROUP BY R_NAME ORDER BY revenue DESC'
    )
  );
