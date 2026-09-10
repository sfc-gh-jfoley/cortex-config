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
```

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
Gap: metric TOTAL_COST on REQUESTS table
Suggested VQR:
  Question: "What is the total cost per agent including AI function credits?"
  SQL skeleton:
    SELECT r.agent_name, SUM(r.token_credits + COALESCE(r.ai_function_credits, 0)) AS total_cost
    FROM __requests r
    WHERE r.start_time >= '2024-01-01'
    GROUP BY r.agent_name ORDER BY total_cost DESC
```

Present as suggestions — user accepts or modifies in Phase 6.
