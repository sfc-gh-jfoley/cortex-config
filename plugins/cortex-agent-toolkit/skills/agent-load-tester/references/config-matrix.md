# Config Matrix — Warehouse setup for Side 2 (SQL replay)

All objects are prefixed `LT_` and created in a dedicated schema so teardown is one block.
Gate `LOAD-WH-CREATE` (OPERATOR_REQUIRED): show this DDL with the cost estimate before running.

## Standard multi-cluster (XS / S / M)

```sql
CREATE WAREHOUSE IF NOT EXISTS LT_XS_MC
  WAREHOUSE_SIZE = 'XSMALL' MIN_CLUSTER_COUNT = 1 MAX_CLUSTER_COUNT = <N>   -- default N = 4
  SCALING_POLICY = 'STANDARD' AUTO_SUSPEND = 60 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE
  COMMENT = 'agent-load-tester';
CREATE WAREHOUSE IF NOT EXISTS LT_S_MC  LIKE LT_XS_MC;  ALTER WAREHOUSE LT_S_MC SET WAREHOUSE_SIZE = 'SMALL';
CREATE WAREHOUSE IF NOT EXISTS LT_M_MC  LIKE LT_XS_MC;  ALTER WAREHOUSE LT_M_MC SET WAREHOUSE_SIZE = 'MEDIUM';
GRANT USAGE ON WAREHOUSE LT_XS_MC TO ROLE <ROLE>;  -- repeat per WH, the role that runs sql_replay
```

Multi-cluster requires Enterprise edition or higher. If `MAX_CLUSTER_COUNT > 1` is rejected, run
single-cluster and note it in the report.
Optional extra variant: a single-cluster copy (`MAX_CLUSTER_COUNT = 1`) per size, to show what scale-out buys.

## Interactive warehouse + interactive tables

1. List the objects the captured SQL reads: the distinct FQNs in `sql_mix.jsonl`, usually the
   semantic view's base tables or views.
2. For each object, build an interactive table in `<DB>.LT_INTERACTIVE`. `CLUSTER BY` is **required**:
   use the columns most often filtered in the captured SQL's WHERE clauses.

```sql
CREATE SCHEMA IF NOT EXISTS <DB>.LT_INTERACTIVE;

-- Static copy (load tests don't need refresh)
CREATE OR REPLACE INTERACTIVE TABLE <DB>.LT_INTERACTIVE.<OBJ>
  CLUSTER BY (<filter_col_1>, <filter_col_2>)
  AS SELECT * FROM <SRC_DB>.<SRC_SCHEMA>.<OBJ>;

CREATE INTERACTIVE WAREHOUSE IF NOT EXISTS LT_IWH WAREHOUSE_SIZE = '<XSMALL|SMALL|MEDIUM>';
USE WAREHOUSE <standard_wh>;                       -- CREATE makes LT_IWH current; switch back
ALTER WAREHOUSE LT_IWH SET FALLBACK_WAREHOUSE = LT_S_MC;   -- >5s queries retry here
ALTER WAREHOUSE LT_IWH ADD TABLES (<DB>.LT_INTERACTIVE.<OBJ>, ...);  -- pre-warm cache (≤100 tables)
GRANT USAGE ON WAREHOUSE LT_IWH TO ROLE <ROLE>;
```

3. `configs.json` entry with the rewrite map (source FQN → interactive FQN):

```json
{"name": "IWH", "warehouse": "LT_IWH",
 "table_map": {"SRC_DB.SRC_SCHEMA.OBJ": "DB.LT_INTERACTIVE.OBJ"}}
```

### Interactive caveats (put these in the report)
- **5-second limit.** Longer queries rerun on `FALLBACK_WAREHOUSE`. `collect_metrics` counts these as
  `ran_elsewhere` (account_usage source only). Those latencies belong to the fallback warehouse.
- **Billing.** The minimum `AUTO_SUSPEND` is 86400s (24h), so the warehouse bills for at least a day
  once resumed. A suspend/resume clears the cache, so run warmup before measuring.
- **Limited SQL.** Interactive tables are built for simple SELECTs with selective WHERE clauses.
  Before the sweep, run each rewritten query in `sql_mix.jsonl` once on LT_IWH and drop queries that
  error from the IWH config, listing them in the report.
- Region availability is limited. Check `SHOW WAREHOUSES` / the docs if CREATE fails.
- Materializing a *view* as a static interactive table freezes its logic and drops any row access
  policies. Note this when the source SV relies on policies.

## Ordering

List configs **smallest first** in `configs.json` (XS_MC, S_MC, M_MC, IWH). `build_report --sla-p95`
then picks the first passing config per tier.

## Teardown (gate `LOAD-TEARDOWN`)

```sql
DROP WAREHOUSE IF EXISTS LT_XS_MC; DROP WAREHOUSE IF EXISTS LT_S_MC; DROP WAREHOUSE IF EXISTS LT_M_MC;
DROP WAREHOUSE IF EXISTS LT_IWH;
DROP SCHEMA IF EXISTS <DB>.LT_INTERACTIVE;
-- Phase 3 agent clones, if created:
DROP AGENT IF EXISTS <DB>.<SCHEMA>.<AGENT>_LT_<MODEL>;
```
