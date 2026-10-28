-- Reference telemetry queries for agent-load-tester.
-- 1) Think vs SQL per eval run (account-wide survey; used to pick load-test candidates)
-- Per eval run: think (planning + response-gen LLM) vs SQL execution time, from AI observability spans.
WITH s AS (
  SELECT
    RECORD_ATTRIBUTES:"snow.ai.observability.run.name"::string   AS run_name,
    RECORD_ATTRIBUTES:"snow.ai.observability.object.name"::string AS agent,
    RECORD_ATTRIBUTES:"ai.observability.record_id"::string        AS record_id,
    RECORD:name::string                                           AS span,
    RECORD_ATTRIBUTES:"snow.ai.observability.agent.tool.sql_execution.warehouse"::string AS wh,
    DATEDIFF('millisecond', START_TIMESTAMP, TIMESTAMP)           AS ms,
    TIMESTAMP AS ts
  FROM SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS
  WHERE RECORD_TYPE = 'SPAN'
    AND RECORD_ATTRIBUTES:"snow.ai.observability.run.name" IS NOT NULL
    AND RECORD_ATTRIBUTES:"snow.ai.observability.object.type"::string ILIKE '%agent%'
), rec AS (
  SELECT run_name, agent, record_id,
    MAX(IFF(span = 'Agent', ms, NULL))                                        AS total_ms,
    SUM(IFF(span LIKE 'ReasoningAgentStepPlanning-%', ms, 0))                 AS plan_ms,
    SUM(IFF(span LIKE 'ReasoningAgentStepResponseGeneration-%', ms, 0))       AS resp_ms,
    SUM(IFF(span LIKE 'SqlExecution%', ms, 0))                                AS sql_ms,
    COUNT_IF(span LIKE 'SqlExecution%')                                       AS sql_calls,
    COUNT_IF(span LIKE 'ReasoningAgentStepPlanning-%')                        AS plan_steps,
    LISTAGG(DISTINCT wh, ',')                                                 AS whs,
    MIN(ts) AS ts
  FROM s GROUP BY 1,2,3
  HAVING MAX(IFF(span = 'Agent', 1, 0)) = 1
)
SELECT agent, run_name, TO_VARCHAR(MIN(ts)::date) AS run_date, COUNT(*) AS records,
  ROUND(AVG(total_ms)/1000, 2)                 AS avg_total_s,
  ROUND(AVG(plan_ms + resp_ms)/1000, 2)        AS avg_think_s,
  ROUND(AVG(sql_ms)/1000, 2)                   AS avg_sql_s,
  ROUND(AVG(total_ms - plan_ms - resp_ms - sql_ms)/1000, 2) AS avg_other_s,
  ROUND(MEDIAN(sql_ms)/1000, 2)                AS p50_sql_s,
  ROUND(APPROX_PERCENTILE(sql_ms, 0.95)/1000, 2) AS p95_sql_s,
  ROUND(100 * SUM(plan_ms + resp_ms) / NULLIF(SUM(total_ms), 0), 1) AS think_pct,
  ROUND(100 * SUM(sql_ms) / NULLIF(SUM(total_ms), 0), 1)            AS sql_pct,
  ROUND(AVG(plan_steps), 1) AS avg_plan_steps, ROUND(AVG(sql_calls), 1) AS avg_sql_calls,
  LISTAGG(DISTINCT whs, ',') AS warehouses
FROM rec GROUP BY 1,2 ORDER BY run_date, agent, run_name;

-- 2) Replay cells for a run (server side)
SELECT SPLIT_PART(query_tag, ':', 4) AS config, SPLIT_PART(query_tag, ':', 5)::int AS users,
       SPLIT_PART(query_tag, ':', 6) AS cache, warehouse_name, COUNT(*) AS queries,
       APPROX_PERCENTILE(total_elapsed_time, .95) AS elapsed_p95_ms,
       APPROX_PERCENTILE(queued_overload_time, .95) AS queued_p95_ms
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE query_tag LIKE 'agent_load:sql:<RUN_ID>:%'
GROUP BY ALL ORDER BY config, users, cache;

-- 3) Cluster scale-out during a run
SELECT timestamp, warehouse_name, event_name, event_reason, cluster_number
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_EVENTS_HISTORY
WHERE warehouse_name LIKE 'LT\\_%' AND timestamp >= '<RUN_START>' ORDER BY timestamp;
