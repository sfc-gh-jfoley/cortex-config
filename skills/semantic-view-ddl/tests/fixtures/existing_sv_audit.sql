-- =============================================================================
-- Deliberately Flawed Semantic View — Audit Test Fixture
-- Contains 4 intentional issues for sv_validator.py to catch:
--   1. Missing PK on referenced table (customers has no PRIMARY KEY)
--   2. Orphan table (suppliers not in any relationship)
--   3. Duplicate synonym ('revenue' on both a fact and a metric)
--   4. Alias/physical mismatch (orders.order_dt AS O_ORDERDATE should fail check 2)
-- Expected result: sv_validator.py exits 1 with errors/warnings
-- =============================================================================

CREATE OR REPLACE SEMANTIC VIEW MY_DB.ANALYTICS.FLAWED_AUDIT_SV
  TABLES (
    orders AS SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.ORDERS
      PRIMARY KEY (O_ORDERKEY)
      COMMENT = 'Customer orders',

    customers AS SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.CUSTOMER
      COMMENT = 'Customer data — deliberately missing PRIMARY KEY',

    suppliers AS SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.SUPPLIER
      PRIMARY KEY (S_SUPPKEY)
      COMMENT = 'Supplier data — orphan table, not in any relationship'
  )

  RELATIONSHIPS (
    orders_to_customers AS orders (O_CUSTKEY) REFERENCES customers
  )

  FACTS (
    orders.O_TOTALPRICE AS O_TOTALPRICE
      WITH SYNONYMS = ('revenue', 'order total')
      COMMENT = 'Total price of the order'
  )

  DIMENSIONS (
    orders.order_dt AS O_ORDERDATE
      COMMENT = 'Date the order was placed — alias does not match physical name',

    customers.C_NAME AS C_NAME
      COMMENT = 'Customer name'
  )

  METRICS (
    orders.total_revenue AS SUM(O_TOTALPRICE)
      WITH SYNONYMS = ('revenue', 'total sales')
      COMMENT = 'Sum of all order values — synonym overlaps with fact'
  )

  COMMENT = 'Deliberately flawed SV for audit testing';
