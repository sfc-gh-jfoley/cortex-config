# Phase 5: Coverage Gaps

Identify metrics and dimensions in the SV that have no VQR testing them.
These are eval blind spots — if the SV schema changes and breaks these columns,
no VQR failure will catch it.

## Step 5.1 — Column coverage map

From `SV_SCHEMA`, collect all metrics and dimensions.
From `VQR_LIST`, collect all column names referenced in VQR SQL.

```
covered_columns   = columns referenced in at least one VQR SQL
uncovered_columns = SV_SCHEMA columns NOT in covered_columns
sole_coverage[v]  = true if VQR v is the only VQR referencing some metric or dimension
```

Phases 3 and 6 use `sole_coverage`.

## Step 5.2 — Report gaps by category

```
Coverage: <N>/<total> columns tested by at least one VQR

Uncovered metrics (no VQR tests these aggregates):
  - <metric_name>: <expression>

Uncovered dimensions (no VQR groups by or filters on these):
  - <dim_name>: <expression>

Uncovered tables (entire table has zero VQR coverage):
  - <logical_table_name>
```

## Step 5.3 — Gap prioritization

Prioritize uncovered columns by type:

| Priority | Type | Why |
|---------|------|-----|
| HIGH | Metric on primary fact table | Core business metrics; most likely to be queried |
| MEDIUM | Dimension used in relationships | Join keys; if schema changes here, joins break silently |
| LOW | Dimension on secondary table | Less commonly queried; eval can wait |

Report only HIGH and MEDIUM gaps unless user asks for full coverage.

## Step 5.4 — VQR candidate suggestions

For each HIGH-priority gap, suggest a VQR question and skeleton SQL:

```
Gap: metric total_revenue on ORDERS table
Suggested VQR:
  Question: "What was total revenue by region in 2024?"
  SQL skeleton:
    SELECT o.region, SUM(o.order_total) AS total_revenue
    FROM __orders o
    WHERE o.order_date >= '2024-01-01' AND o.order_date < '2025-01-01'
    GROUP BY o.region ORDER BY total_revenue DESC
```

Present as suggestions — user accepts or modifies in Phase 6. New VQRs are created through
vqr-generator Phase 4–5 (dry-run, then candidate copy).
