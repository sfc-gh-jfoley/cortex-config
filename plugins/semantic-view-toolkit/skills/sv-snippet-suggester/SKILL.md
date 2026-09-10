---
name: sv-snippet-suggester
description: >
  Pattern recognition and snippet suggestion for Snowflake Semantic Views.
  Given a user's table schema, business question, or partial DDL, identifies
  which of the 25 canonical SV patterns apply and explains how to implement them.
  Invoked automatically by sv-ddl (Phase 3, 4, 5) and sv-audit when patterns
  are detected or recommended. Can also be invoked directly.
triggers:
  - "what pattern should I use"
  - "how do I model"
  - "snapshot table"
  - "semi-additive"
  - "non additive by"
  - "two date columns"
  - "role playing"
  - "scd2"
  - "valid_from valid_to"
  - "asof join"
  - "window function"
  - "time intelligence"
  - "sply yoy mom"
  - "multi fact"
  - "derived metric"
  - "scoped dataset"
  - "variables semantic view"
  - "parameterized"
  - "row access policy null"
  - "caller rights sv"
  - "materialization semantic view"
  - "which snippet"
---

# SV Snippet Suggester

## Purpose

Identify which canonical Semantic View patterns apply to the user's data model
and explain concretely how to implement them. This skill covers all 25 patterns
from the official `coco-skills` snippet library.

When invoked from **sv-ddl**, it runs automatically during Phase 3 (classify),
Phase 4 (relationships), and Phase 5 (generate DDL) — injecting pattern-specific
DDL guidance at the point of use. See `../reference/sv-snippet-patterns.md` for
the full pattern catalog that drives those phases.

When invoked **directly**, run the detection flow below.

---

## Detection Flow

### Step 1 — Collect signals

Gather signals from any of: table column names, table COMMENTs, BUSINESS_CONTEXT,
existing partial DDL, or the user's plain-language description.

### Step 2 — Score against the pattern catalog

Read `../reference/sv-snippet-patterns.md`. For each pattern, check its
**detection signals** against the collected signals. Score: MATCH / POSSIBLE / NO.

Present only MATCH and POSSIBLE results.

### Step 3 — Present ranked suggestions

Format:

```
## Detected Patterns

### [HIGH] Semi-Additive Metric  →  snippet: semi_additive_metric
Signal: BALANCE_DATE column, BALANCE_USD fact on a table named ACCOUNT_BALANCES
Problem: Summing account balances across dates double-counts.
Fix: Use NON ADDITIVE BY (balance_date) on the total_balance metric.
     Define a separate avg_daily_balance AS AVG(BALANCE_USD) for trend queries.
Synonym discipline: total_balance → "current balance", "snapshot balance", "balance as of date"
                    avg_daily_balance → "average balance", "balance trend"

### [HIGH] Range Join (SCD2)  →  snippet: range_join
Signal: VALID_FROM + VALID_TO columns on CUSTOMER_SEGMENTS
Problem: Joining orders to current customer tier silently mis-attributes historical revenue.
Fix: CONSTRAINT segment_period DISTINCT RANGE BETWEEN VALID_FROM AND VALID_TO EXCLUSIVE
     Relationship: orders(CUSTOMER_ID, ORDER_DATE) REFERENCES customer_segments(CUSTOMER_ID, BETWEEN VALID_FROM AND VALID_TO EXCLUSIVE)
Gotcha: VALID_TO must be EXCLUSIVE (first day NOT active). If data uses inclusive end dates, add +1 day in a view.

### [POSSIBLE] Role-Playing Dimensions  →  snippet: role_playing_dimensions
Signal: Two FK columns in ORDERS both ending in _DATE
...
```

### Step 4 — Ask which to implement (if interactive)

If more than one MATCH exists, ask:

> Which pattern(s) should I implement now? (Type pattern numbers, "all", or "skip")

Then generate the exact DDL additions for each selected pattern.

---

## Pattern Quick-Reference

See full catalog: `../reference/sv-snippet-patterns.md`

| Pattern | Key signals | Primary DDL construct |
|---------|------------|----------------------|
| `semi_additive_metric` | snapshot table, balance, headcount, inventory | `NON ADDITIVE BY (time_col)` |
| `range_join` | valid_from + valid_to, SCD2 | `DISTINCT RANGE BETWEEN ... EXCLUSIVE` |
| `asof_join` | single effective_date, no valid_to | `REFERENCES dim(id, ASOF date_col)` |
| `accumulating_snapshot` | pipeline stages, multiple milestone dates | `USING (rel)` per metric |
| `role_playing_dimensions` | two+ FK dates in same fact table | double alias in TABLES |
| `multi_path_metrics` | two paths to same physical table | `USING (rel)` per metric |
| `time_intelligence` | SPLY, YoY, MoM, prior period | shifted FACT join key + role alias |
| `window_metrics` | rolling avg, YTD, LAG, rank | `OVER (PARTITION BY EXCLUDING ...)` |
| `derived_metrics` | cross-entity totals, ratios | no-prefix metric on right-hand refs |
| `entity_facts` | LTV, segment from aggregate | `PRIVATE ... AS SUM(other_table.col)` |
| `fact_as_relationship_key` | computed FK, no physical FK col | FACT as derived expression + REFERENCES |
| `multi_fact_table` | multiple independent fact tables | separate TABLES + shared dims |
| `shared_degenerate_dimension` | categorical col on multiple facts, no dim table | UNION helper view → UNIQUE entity |
| `ai_metadata` | steer SQL style, reject OOB questions | `AI_SQL_GENERATION`, VQRs |
| `variables` | adjustable thresholds, weights | `VARIABLES (...) DEFAULT` |
| `scoped_dataset` | LOB filter, pre-join ⚠️ Private Preview | `AS (SELECT ... WHERE ...)` in TABLES |
| `inline_sv` | prototyping, dbt unit test ⚠️ Private Preview | `WITH ... AS SEMANTIC VIEW` |
| `materialization` | pre-aggregate hot queries ⚠️ Private Preview | `ADD MATERIALIZATION ... AS DIMENSIONS ... METRICS` |
| `caller_rights` | enforce base-table ACL through SV | owner-with-no-table-access pattern |
| `row_access_policies` | region/tenant RAP + SV | apply RAP to FACT table, not dim |
| `introspection` | discover SV structure, lineage | `SHOW SEMANTIC METRICS`, `SHOW SEMANTIC DIMENSIONS FOR METRIC`, `GET_LINEAGE` |
| `sv_diagnostics` | debugging, wrong numbers | pre-deploy checklist, cardinality lie detection |
| `system_explain_semantic_query` | debug generated SQL | `SYSTEM$EXPLAIN_SEMANTIC_QUERY(sv, query)` |
| `standard_sql` | Tableau/dbt query without SEMANTIC_VIEW() | `ANY_VALUE(metric)` wrapper |
| `tags` | ownership, certification governance | `WITH TAG (key = 'value')` on metrics |

---

## Private Preview Guard

For any pattern marked ⚠️ Private Preview, always include this note before
generating DDL:

> ⚠️ This feature (`<feature_name>`) is Private Preview — not GA. It requires
> account-team enablement. Confirm availability before deploying:
> `SELECT SYSTEM$BEHAVIOR_CHANGE_BUNDLE_STATUS('2025_01');` (or relevant bundle).
> Generating DDL anyway for reference.

Patterns in Private Preview: `scoped_dataset` (inline SQL in TABLES),
`inline_sv` (WITH ... AS SEMANTIC VIEW), `materialization`.
