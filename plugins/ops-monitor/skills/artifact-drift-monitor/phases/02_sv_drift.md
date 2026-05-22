---
name: artifact-drift-monitor-phase2
description: SV query-history drift — detect gaps and score each with ADD/SKIP reasoning
---

# Phase 2: Semantic View Drift Analysis

Inputs: `ARTIFACT_NAME`, `SV_TABLES`, `SV_COLUMNS`, `SV_METRICS`, `SV_COLUMN_COUNT`, `LOOKBACK_DAYS`

---

## Step 2.1: Measure base query population

```sql
WITH sv_queries AS (
    SELECT query_id, user_name, query_text, start_time, total_elapsed_time
    FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
    WHERE start_time >= DATEADD('days', -:LOOKBACK_DAYS, CURRENT_TIMESTAMP())
      AND execution_status = 'SUCCESS'
      AND (
          UPPER(query_text) LIKE '%<TABLE_1_SHORT>%'
          OR UPPER(query_text) LIKE '%<TABLE_2_SHORT>%'
          -- repeat per SV source table
      )
)
SELECT COUNT(DISTINCT query_id) AS total_queries,
       COUNT(DISTINCT user_name) AS unique_users
FROM sv_queries;
```

Store as `QUERY_POPULATION_SIZE`. Flag if < 20 queries (low signal warning).

---

## Step 2.2: Missing table detection + scoring

Find tables co-queried with SV source tables but not included in the SV.

```sql
WITH sv_queries AS (
    SELECT query_id, user_name, query_text
    FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
    WHERE start_time >= DATEADD('days', -:LOOKBACK_DAYS, CURRENT_TIMESTAMP())
      AND execution_status = 'SUCCESS'
      AND (UPPER(query_text) LIKE '%<TABLE_1_SHORT>%' OR ...)
),
table_refs AS (
    SELECT
        query_id,
        user_name,
        UPPER(REGEXP_SUBSTR(
            query_text,
            '(?:FROM|JOIN)\\s+(?:[A-Z0-9_$]+\\.){0,2}([A-Z0-9_$]+)',
            1, seq4.seq, 'ie', 1
        )) AS candidate_table
    FROM sv_queries
    CROSS JOIN TABLE(GENERATOR(ROWCOUNT => 20)) seq4
    WHERE candidate_table IS NOT NULL AND LENGTH(candidate_table) > 3
)
SELECT
    candidate_table,
    COUNT(DISTINCT query_id)  AS query_count,
    COUNT(DISTINCT user_name) AS unique_users,
    ROUND(query_count / :QUERY_POPULATION_SIZE * 100, 1) AS pct_of_queries
FROM table_refs
WHERE candidate_table NOT IN (<SV_TABLE_SHORT_NAMES>)
  AND candidate_table NOT IN ('SELECT','WHERE','FROM','JOIN','ON','AND','OR','AS','NULL')
GROUP BY 1
HAVING query_count >= 5
ORDER BY query_count DESC
LIMIT 15;
```

### Scoring each TABLE_GAP candidate

For each candidate table, fetch its column count and build a suggestion:

```sql
SELECT COUNT(*) AS candidate_col_count
FROM <DB>.INFORMATION_SCHEMA.COLUMNS
WHERE table_name = '<CANDIDATE_TABLE>';
```

Apply this reasoning framework:

| Signal | Score adjustment |
|--------|----------------|
| pct_of_queries >= 30% | +3 (high demand) |
| pct_of_queries 10–29% | +2 (moderate demand) |
| pct_of_queries 5–9% | +1 (low demand) |
| unique_users >= 5 | +2 (broad usage — not one person's habit) |
| candidate_col_count <= 10 | +1 (small table — low complexity to add) |
| candidate_col_count > 30 | -2 (large table — adds many new dimensions, may confuse Cortex Analyst) |
| SV_COLUMN_COUNT + candidate_col_count > 100 | -3 (SV already large — adding more columns risks model confusion) |
| Table name contains ETL/audit patterns (_LOG, _AUDIT, _HIST, _STG, _RAW) | -3 (unlikely to be a user-facing query target) |
| Direct join to an existing SV table on a known key | +1 (clean join path) |

**Recommendation**:
- Score >= 4: **ADD** — strong evidence, manageable complexity
- Score 1–3: **REVIEW** — moderate evidence; user should decide based on business context
- Score <= 0: **SKIP** — low signal or adds too much complexity

Store each candidate as:
```json
{
  "type": "TABLE_GAP",
  "table": "<CANDIDATE_TABLE>",
  "query_count": N,
  "unique_users": N,
  "pct_of_queries": N,
  "candidate_col_count": N,
  "score": N,
  "recommendation": "ADD|REVIEW|SKIP",
  "add_reason": "...",
  "skip_reason": "..."
}
```

---

## Step 2.3: Missing column detection + scoring

Find columns referenced in queries that are absent from the SV.

```sql
WITH sv_queries AS (
    SELECT query_id, user_name, query_text
    FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
    WHERE start_time >= DATEADD('days', -:LOOKBACK_DAYS, CURRENT_TIMESTAMP())
      AND execution_status = 'SUCCESS'
      AND (UPPER(query_text) LIKE '%<TABLE_1_SHORT>%' OR ...)
),
col_refs AS (
    SELECT
        query_id,
        user_name,
        UPPER(REGEXP_SUBSTR(
            query_text,
            '(?:WHERE|AND|OR|GROUP BY|ORDER BY|SELECT)[\\s,]+([A-Z_][A-Z0-9_]+)',
            1, seq4.seq, 'ie', 1
        )) AS candidate_col,
        CASE
            WHEN UPPER(query_text) LIKE '%WHERE%' || candidate_col || '%'
                 OR UPPER(query_text) LIKE '%AND%' || candidate_col || '%' THEN 'filter'
            WHEN UPPER(query_text) LIKE '%GROUP BY%' || candidate_col || '%' THEN 'group_by'
            ELSE 'select'
        END AS usage_context
    FROM sv_queries
    CROSS JOIN TABLE(GENERATOR(ROWCOUNT => 30)) seq4
    WHERE candidate_col IS NOT NULL AND LENGTH(candidate_col) > 3
)
SELECT
    candidate_col,
    COUNT(DISTINCT query_id)  AS query_count,
    COUNT(DISTINCT user_name) AS unique_users,
    LISTAGG(DISTINCT usage_context, ', ') WITHIN GROUP (ORDER BY usage_context) AS usage_contexts
FROM col_refs
WHERE candidate_col NOT IN (<SV_COLUMN_NAMES>)
  AND candidate_col NOT IN ('FROM','WHERE','JOIN','NULL','TRUE','FALSE','CASE','WHEN','THEN','ELSE','END','LIMIT')
GROUP BY 1
HAVING query_count >= 3
ORDER BY query_count DESC
LIMIT 20;
```

### Scoring each COLUMN_GAP candidate

| Signal | Score adjustment |
|--------|----------------|
| usage_context includes 'filter' | +3 (users filter on this — Cortex Analyst needs it as a dimension) |
| usage_context includes 'group_by' | +2 (users group by this — important dimension) |
| unique_users >= 3 | +2 (not one person's query) |
| query_count >= 10 | +1 (high frequency) |
| Column name matches ETL/audit patterns | -3 (unlikely business column) |
| Column name matches PII patterns (EMAIL, SSN, PHONE, DOB) | -2 (should SKIP for access reasons — note in reason) |
| Column name already has a synonym/alias in SV COMMENT | -2 (may already be covered under different name) |

**Recommendation**:
- Score >= 4: **ADD**
- Score 1–3: **REVIEW**
- Score <= 0: **SKIP**

---

## Step 2.4: Dimension enrichment gaps

Dimensions with no `sample_values` in COMMENT hurt Cortex Analyst literal-value matching.

```sql
SELECT column_name, data_type
FROM <DB>.INFORMATION_SCHEMA.COLUMNS
WHERE table_name   = '<SV_SHORT_NAME>'
  AND data_type IN ('TEXT','VARCHAR','CHAR')
ORDER BY column_name;
```

For each VARCHAR dimension, check if the COMMENT contains pipe-separated values. If not, fetch top 10 values:
```sql
SELECT DISTINCT <col> FROM <source_table> WHERE <col> IS NOT NULL ORDER BY 1 LIMIT 10;
```

**Recommendation**: Always **ADD** sample values — zero downside, improves literal matching.

---

## Step 2.5: Bypass / direct-SQL signals

```sql
SELECT
    user_name,
    COUNT(DISTINCT query_id) AS direct_queries,
    MAX(start_time) AS last_seen,
    ANY_VALUE(LEFT(query_text, 200)) AS sample_query
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE start_time >= DATEADD('days', -:LOOKBACK_DAYS, CURRENT_TIMESTAMP())
  AND execution_status = 'SUCCESS'
  AND (UPPER(query_text) LIKE '%<TABLE_1_FULL>%' OR ...)
  AND UPPER(query_text) NOT LIKE '%<SV_SHORT_NAME>%'
GROUP BY user_name
HAVING direct_queries >= 3
ORDER BY direct_queries DESC;
```

Bypass signals are informational — they indicate user education gaps or SV coverage gaps. Note in the manifest but do not generate DDL for them.

---

## Step 2.6: Pass to Phase 6

Output all scored gaps as `GAP_SUGGESTIONS` array. Pass to `phases/06_manifest_remediate.md`.
