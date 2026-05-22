-- =============================================================================
-- Single Table Semantic View — Edge Case Test Fixture
-- Minimal: one table, no relationships, facts + dimensions only.
-- Expected result: sv_validator.py passes all checks (single-table is valid)
-- =============================================================================

CREATE OR REPLACE SEMANTIC VIEW MY_DB.ANALYTICS.ORDERS_ONLY_SV
  TABLES (
    orders AS SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.ORDERS
      PRIMARY KEY (O_ORDERKEY)
      COMMENT = 'Customer orders — standalone single-table view'
  )

  FACTS (
    orders.O_TOTALPRICE AS O_TOTALPRICE
      COMMENT = 'Total price of the order'
  )

  DIMENSIONS (
    orders.O_ORDERDATE AS O_ORDERDATE
      COMMENT = 'Date the order was placed',

    orders.O_ORDERSTATUS AS O_ORDERSTATUS
      COMMENT = 'Current order status: O (Open), F (Fulfilled), P (Partial)',

    orders.O_ORDERPRIORITY AS O_ORDERPRIORITY
      COMMENT = 'Order priority level'
  )

  METRICS (
    orders.total_revenue AS SUM(O_TOTALPRICE)
      COMMENT = 'Sum of all order values',

    orders.order_count AS COUNT(DISTINCT O_ORDERKEY)
      COMMENT = 'Count of distinct orders'
  )

  COMMENT = 'Minimal single-table semantic view on TPCH orders';
