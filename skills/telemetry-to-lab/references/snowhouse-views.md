# Snowhouse Views & Query Templates (verified 2026-10-28)

Placeholders: `<DEP>` = `SNOWHOUSE_IMPORT` schema for the deployment (e.g. `PROD2`), `<ACCT>` = numeric
account id, `<DAYS>` = window. Always pass `timeout_seconds` (600–1200 for `JOB_ETL_V`).

## View catalog

| Need | View | Key columns / notes |
|---|---|---|
| Customer → accounts | `FINANCE.CUSTOMER.SUBSCRIPTION` | `salesforce_account_name`, `snowflake_account_id`, `snowflake_account_name`, `snowflake_deployment` |
| Spend by product | `FINANCE.CUSTOMER.USAGE_DAILY` | `total_credits`, `total_warehouse_credits`, `total_ai_credits`, `ai_functions_ai_credits`, `snowflake_intelligence_ai_credits`, `cortex_agents_ai_credits`, `cortex_code_ai_credits`, `cortex_search_ai_credits`, `snowpark_container_credits`, `serverless_task_credits`, `snowpipe_credits` |
| Jobs / errors / latency | `<DEP>.JOB_ETL_V` | `error_code`, `error_message`, `warehouse_name`, `user_name`, `role_name`, `total_duration` (ms), `description` (SQL text), `tag` (query tag), `query_parameterized_hash`, `parent_job_id`, `database_name`, `schema_name`, `created_on` |
| Object/column access | `<DEP>.ACCESS_HISTORY_LOG_RAW_V` | `base_access_info_set` (array of `{objectName, objectDomain, columns[{columnName}]}`), `user_name`, `created_on` |
| Column types | `<DEP>.TABLE_COLUMN_ETL_V` | join by table id; verify column names with `INFORMATION_SCHEMA.COLUMNS` before use |
| Semantic views | `<DEP>.SEMANTIC_VIEW_ETL_V` | `id`, `name`, `comment`, `parent_id` (schema id), `created_on`, `deleted_on`; `dpo:"SemanticViewDPO:primary"` |
| Agents | `<DEP>.CORTEX_AGENT_ETL_V` | `id`, `name`, `comment`, `created_on`, `deleted_on` |
| SI / CoCo threads | `<DEP>.CORTEX_THREAD_ETL_V` | `origin_application` (`sf_intelligence`, `coding_agent`, `coco:desktop`, `sql_function`, ...), `status` (codes undocumented: report raw), `user_id` |
| Search services | `<DEP>.CORTEX_SEARCH_SERVICE_ETL_V` | count distinct `id` where `deleted_on IS NULL` |
| SPCS jobs | `<DEP>.SPCS_JOB_HISTORY_ETL_V` | presence check |
| Fine-tuning | `<DEP>.CORTEX_TRAINING_JOB_ETL_V` | presence check |
| Dynamic tables | `<DEP>.DYNAMIC_TABLE_REFRESH_HISTORY_RAW_V` | refresh failures |

## Gotchas (each one has bitten)

1. **Account IDs are only unique per deployment.** Always join on `(account_id, deployment)`.
2. `CUSTOMER_WAREHOUSE_BY_DAY` is deployment-local; use `USAGE_DAILY` to rank across deployments.
3. Use `JOB_ETL_V` typed columns, not `JOB_RAW_V` `dpo:` JSON.
4. **Keyword matching lies.** `FORECAST` matched column names ~100x more than ML calls;
   `AI_` matched ordinary columns whose names start with `ai_` (e.g. `ai_score_band`). Match *call syntax*: `AI_[A-Z_]+\s*\(`,
   `SNOWFLAKE\.CORTEX\.[A-Z_]+\s*\(`, `SNOWFLAKE\.ML\.`, `!PREDICT`, `!FORECAST`, `!DETECT_ANOMALIES`.
5. **AI spend hides inside procedures/tasks.** Top-level text is `CALL x()`; the AI calls are child jobs.
   Roll up children via `parent_job_id`. If AI credits ≫ visible AI SQL, say "likely inside procs" and
   label it inferred.
6. `feature_family_name` is almost always NULL; don't rely on it.
7. Object DPOs have no database name; SV/agent placement needs `parent_id` → schema resolution.
8. Thread `status` codes are undocumented; report counts by raw code, don't interpret.
9. Names repeat across schemas: count `DISTINCT id` *and* `DISTINCT name` to detect copy sprawl.
10. Mask error messages before storing: `REGEXP_REPLACE(msg, '''[^'']*''', '?')`.

## Templates

### R1 — accounts + spend (00-resolve)
```sql
SELECT u.snowflake_account_name, u.snowflake_deployment, u.snowflake_account_id,
  ROUND(SUM(total_credits)) total_cr, ROUND(SUM(total_warehouse_credits)) wh_cr,
  ROUND(SUM(total_ai_credits)) ai_cr, ROUND(SUM(ai_functions_ai_credits)) aifn_cr,
  ROUND(SUM(snowflake_intelligence_ai_credits)) si_cr, ROUND(SUM(cortex_agents_ai_credits)) agent_cr,
  ROUND(SUM(cortex_code_ai_credits)) coco_cr, ROUND(SUM(snowpark_container_credits)) spcs_cr
FROM FINANCE.CUSTOMER.USAGE_DAILY u
JOIN (SELECT DISTINCT snowflake_account_id, snowflake_deployment FROM FINANCE.CUSTOMER.SUBSCRIPTION
      WHERE salesforce_account_name ILIKE '%<CUSTOMER>%') s
  ON u.snowflake_account_id = s.snowflake_account_id AND u.snowflake_deployment = s.snowflake_deployment
WHERE usage_date >= DATEADD(day, -30, CURRENT_DATE())
GROUP BY 1,2,3 ORDER BY total_cr DESC LIMIT 10;
```

### R2 — workload map by warehouse
```sql
SELECT warehouse_name, COUNT(*) jobs, COUNT_IF(error_code IS NOT NULL) failed,
  ROUND(100*failed/jobs,1) fail_pct, COUNT(DISTINCT user_name) users,
  ROUND(SUM(total_duration)/3.6e6,1) hours,
  ROUND(MEDIAN(total_duration)/1000,1) p50_s, ROUND(APPROX_PERCENTILE(total_duration,0.95)/1000,1) p95_s
FROM SNOWHOUSE_IMPORT.<DEP>.JOB_ETL_V
WHERE account_id = <ACCT> AND created_on >= DATEADD(day,-7,CURRENT_TIMESTAMP()) AND warehouse_name IS NOT NULL
GROUP BY 1 ORDER BY hours DESC LIMIT 30;
```

### O1 — error classes
```sql
SELECT error_code, LEFT(REGEXP_REPLACE(ANY_VALUE(error_message),'''[^'']*''','?'),200) sample_msg,
  COUNT(*) n, COUNT(DISTINCT user_name) users, COUNT(DISTINCT warehouse_name) whs
FROM SNOWHOUSE_IMPORT.<DEP>.JOB_ETL_V
WHERE account_id = <ACCT> AND created_on >= DATEADD(day,-7,CURRENT_TIMESTAMP()) AND error_code IS NOT NULL
GROUP BY 1 ORDER BY n DESC LIMIT 25;
```

### O2 — top recurring statements on a warehouse set (shape + cost)
```sql
SELECT warehouse_name wh, query_parameterized_hash h, ANY_VALUE(user_name) usr, COUNT(*) runs,
  COUNT_IF(error_code IS NOT NULL) failed, ROUND(SUM(total_duration)/3.6e6,1) hours,
  ROUND(MEDIAN(total_duration)/1000,1) p50_s,
  LEFT(REGEXP_REPLACE(REGEXP_REPLACE(ANY_VALUE(description),'''[^'']*''','?'),'\\s+',' '),350) sql_head
FROM SNOWHOUSE_IMPORT.<DEP>.JOB_ETL_V
WHERE account_id = <ACCT> AND created_on >= DATEADD(day,-7,CURRENT_TIMESTAMP())
  AND warehouse_name IN (<WHS>)
GROUP BY 1,2 QUALIFY ROW_NUMBER() OVER (PARTITION BY wh ORDER BY hours DESC) <= 8
ORDER BY wh, hours DESC;
```

### O3 — CALLed procedures (ETL/AI pipelines)
```sql
SELECT warehouse_name wh, LEFT(REGEXP_REPLACE(TRIM(description),'\\(.*$',''),110) proc,
  ANY_VALUE(user_name) usr, COUNT(*) runs, COUNT_IF(error_code IS NOT NULL) failed,
  ROUND(SUM(total_duration)/3.6e6,1) hours, ROUND(MEDIAN(total_duration)/1000) p50_s,
  LEFT(REGEXP_REPLACE(MODE(IFF(error_code IS NOT NULL, error_code||': '||error_message, NULL)),'''[^'']*''','?'),160) top_err
FROM SNOWHOUSE_IMPORT.<DEP>.JOB_ETL_V
WHERE account_id = <ACCT> AND created_on >= DATEADD(day,-7,CURRENT_TIMESTAMP())
  AND UPPER(TRIM(description)) LIKE 'CALL %'
GROUP BY 1,2 ORDER BY hours DESC LIMIT 25;
```

### O4 — real AI function calls (call syntax only)
```sql
WITH f AS (
  SELECT j.warehouse_name, j.user_name, j.error_code, j.total_duration, j.parent_job_id, UPPER(m.value::STRING) fn
  FROM SNOWHOUSE_IMPORT.<DEP>.JOB_ETL_V j,
       LATERAL FLATTEN(REGEXP_SUBSTR_ALL(UPPER(j.description), '(SNOWFLAKE\\.CORTEX\\.[A-Z_]+|AI_[A-Z_]+)\\s*\\(')) m
  WHERE j.account_id = <ACCT> AND j.created_on >= DATEADD(day,-7,CURRENT_TIMESTAMP())
    AND REGEXP_LIKE(j.description, '.*(SNOWFLAKE\\.CORTEX\\.|AI_[A-Z_]+\\s*\\().*', 'is'))
SELECT REGEXP_REPLACE(fn,'\\s*\\($','') fn, COUNT(*) jobs, COUNT_IF(error_code IS NOT NULL) failed,
  COUNT_IF(parent_job_id IS NOT NULL) in_proc, COUNT(DISTINCT user_name) users,
  ROUND(SUM(total_duration)/3.6e6,1) hours
FROM f GROUP BY 1 ORDER BY hours DESC LIMIT 25;
```
Note: this also matches table functions such as `GET_AI_OBSERVABILITY_EVENTS(`; route those to ai-ops.

### O5 — real ML calls
```sql
SELECT CASE WHEN description ILIKE '%SNOWFLAKE.ML.FORECAST%' OR description ILIKE '%!FORECAST%' THEN 'ml_forecast'
            WHEN description ILIKE '%ANOMALY_DETECTION%' OR description ILIKE '%!DETECT_ANOMALIES%' THEN 'ml_anomaly'
            WHEN description ILIKE '%!PREDICT%' THEN 'registry_predict'
            WHEN description ILIKE '%SNOWFLAKE.ML.%' THEN 'other_snowflake_ml'
            ELSE 'false_positive' END k,
  COUNT(*) jobs, COUNT_IF(error_code IS NOT NULL) failed, COUNT(DISTINCT user_name) users
FROM SNOWHOUSE_IMPORT.<DEP>.JOB_ETL_V
WHERE account_id = <ACCT> AND created_on >= DATEADD(day,-7,CURRENT_TIMESTAMP())
  AND REGEXP_LIKE(description, '.*(FORECAST|ANOMALY_DETECTION|!DETECT|!PREDICT|SNOWFLAKE\\.ML).*', 'is')
GROUP BY 1 ORDER BY jobs DESC;
```

### O6 — AI build-out inventory
```sql
SELECT 'semantic_views' k, COUNT(DISTINCT id) ids, COUNT(DISTINCT name) names, COUNT(DISTINCT parent_id) schemas,
  COUNT(DISTINCT IFF(comment IS NULL, id, NULL)) no_comment
FROM SNOWHOUSE_IMPORT.<DEP>.SEMANTIC_VIEW_ETL_V WHERE account_id = <ACCT> AND deleted_on IS NULL
UNION ALL
SELECT 'agents', COUNT(DISTINCT id), COUNT(DISTINCT name), COUNT(DISTINCT parent_id), COUNT(DISTINCT IFF(comment IS NULL, id, NULL))
FROM SNOWHOUSE_IMPORT.<DEP>.CORTEX_AGENT_ETL_V WHERE account_id = <ACCT> AND deleted_on IS NULL
UNION ALL
SELECT 'search_services', COUNT(DISTINCT id), COUNT(DISTINCT name), COUNT(DISTINCT parent_id), NULL
FROM SNOWHOUSE_IMPORT.<DEP>.CORTEX_SEARCH_SERVICE_ETL_V WHERE account_id = <ACCT> AND deleted_on IS NULL;
```

### O7 — threads by origin (30d)
```sql
SELECT origin_application, status, COUNT(*) threads, COUNT(DISTINCT user_id) users
FROM SNOWHOUSE_IMPORT.<DEP>.CORTEX_THREAD_ETL_V
WHERE account_id = <ACCT> AND created_on >= DATEADD(day,-30,CURRENT_TIMESTAMP())
GROUP BY 1,2 ORDER BY threads DESC LIMIT 25;
```

### O8 — AI observability / evaluation failures
```sql
SELECT error_code, LEFT(REGEXP_REPLACE(error_message,'''[^'']*''','?'),260) msg, COUNT(*) n, COUNT(DISTINCT user_name) users
FROM SNOWHOUSE_IMPORT.<DEP>.JOB_ETL_V
WHERE account_id = <ACCT> AND created_on >= DATEADD(day,-7,CURRENT_TIMESTAMP())
  AND REGEXP_LIKE(description, '.*(AI_OBSERVABILITY|AI_EVALUATION|EXECUTE_AI_EVALUATION|GET_AI_EVALUATION).*', 'is')
  AND error_code IS NOT NULL
GROUP BY 1,2 ORDER BY n DESC LIMIT 15;
```

### O9 — table/column shape for an object (40-lookalike)
```sql
SELECT f.value:objectName::STRING obj, c.value:columnName::STRING col, COUNT(*) reads
FROM SNOWHOUSE_IMPORT.<DEP>.ACCESS_HISTORY_LOG_RAW_V a,
     LATERAL FLATTEN(a.base_access_info_set) f, LATERAL FLATTEN(f.value:columns) c
WHERE a.account_id = <ACCT> AND a.created_on >= DATEADD(day,-3,CURRENT_TIMESTAMP())
  AND f.value:objectName::STRING IN (<OBJECTS>)
GROUP BY 1,2 ORDER BY obj, reads DESC;
```
### O10 — column types for a table (verified join: `TABLE_COLUMN_ETL_V.parent_id = TABLE_ETL_V.id`)
```sql
SELECT t.name tbl, c.name col, c.ordinal,
  c.data_type_encoded:type::STRING dtype, c.data_type_encoded:nullable::BOOLEAN nullable
FROM SNOWHOUSE_IMPORT.<DEP>.TABLE_ETL_V t
JOIN SNOWHOUSE_IMPORT.<DEP>.TABLE_COLUMN_ETL_V c ON c.parent_id = t.id AND c.account_id = t.account_id
WHERE t.account_id = <ACCT> AND t.name = '<TABLE>' AND t.deleted_on IS NULL AND c.deleted_on IS NULL
ORDER BY t.id, c.ordinal;
```
`data_type_encoded` is JSON: `{"type":"TEXT","length":36,"nullable":false}`. Table names repeat across
schemas; disambiguate by `t.parent_id` (schema id) when multiple ids return. Row counts are not reliable
here (`total_row_count_in_last_table_sample` is often NULL); estimate volume from job/DML telemetry instead.
