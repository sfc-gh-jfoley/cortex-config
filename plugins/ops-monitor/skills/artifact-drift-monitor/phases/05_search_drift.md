---
name: artifact-drift-monitor-phase5
description: Cortex Search index gap — find filter columns not in attribute_columns
---

# Phase 5: Cortex Search Drift Analysis

Inputs: `ARTIFACT_NAME`, `LOOKBACK_DAYS`

---

## Step 5.1: Get current search service definition

```sql
SHOW CORTEX SEARCH SERVICES LIKE '<SEARCH_SERVICE_NAME>' IN SCHEMA <DB>.<SCHEMA>;
```

Extract: `search_column`, `attribute_columns` list, `source_query`, `target_lag`.

---

## Step 5.2: Find filter columns missing from attribute_columns

```sql
WITH search_queries AS (
    SELECT query_id, query_text
    FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
    WHERE start_time >= DATEADD('days', -:LOOKBACK_DAYS, CURRENT_TIMESTAMP())
      AND execution_status = 'SUCCESS'
      AND (UPPER(query_text) LIKE '%CORTEX.SEARCH_PREVIEW%'
        OR UPPER(query_text) LIKE '%CORTEX.SEARCH%')
)
SELECT
    UPPER(REGEXP_SUBSTR(query_text, 'FILTER.*?([A-Z_]+)\\s*=', 1, seq.seq, 'ie', 1)) AS filter_col,
    COUNT(*) AS usage_count
FROM search_queries
CROSS JOIN TABLE(GENERATOR(ROWCOUNT => 10)) seq
WHERE filter_col IS NOT NULL
  AND filter_col NOT IN (<CURRENT_ATTRIBUTE_COLUMNS>)
GROUP BY 1
HAVING usage_count >= 2
ORDER BY usage_count DESC;
```

Score: >= 5 queries → ADD, 2–4 queries → REVIEW.
Store as `INDEX_GAPS`. Pass to Phase 6.
