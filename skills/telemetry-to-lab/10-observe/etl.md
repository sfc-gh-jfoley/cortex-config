# Observe pillar: ETL

**Templates:** O3 (CALLed procedures), O2 (on warehouses classed etl), O1 filtered to etl warehouses.

## Collect
1. **Pipeline inventory** (O3): procedures by hours, runs, p50 and top error. Infer each pipeline's *purpose*
   from the procedure and target names (ingest raw → stage → fact/aggregate; CDC merge; API landing).
2. **Failure modes** to detect:
   | Signal | Detection | Better pattern |
   |---|---|---|
   | Parent-cancel cascades | `090230 child job cancelled upon parent termination` | break the monolith into a task graph or dynamic tables; make it idempotent |
   | Timeouts | `000630` on CALL | incremental (stream + task / DT), set-based, smaller units |
   | Lock contention | same `UPDATE` hash, tiny rows but p50 > 30s, high hours | per-process watermark rows, append-only control, streams |
   | Schema drift | `View definition declared N columns, but view query produces M` | `CREATE OR REPLACE` discipline, schema evolution, DMFs |
   | NOT NULL / type failures | 100072, 100038 | error tables / DML error logging, data quality checks |
   | External catalog/auth | 004177/004109 (catalog integration), 003001 on external volume | credential rotation, integration grants, monitoring |
   | Hot CDC merges | large JSON `MERGE ... data_column:"x"::varchar` repeated hourly | Snowpipe Streaming / Openflow + dynamic tables |
3. **Landing patterns**: VARIANT `data_column` JSON landing, S3 raw stages, CRM/ITSM-style SaaS replication,
   Iceberg / external catalogs. Record source *types* only.
4. **Warehouse fit**: ETL warehouses with high fail % (>5%) or extreme p95. Note misnamed warehouses.

## Emit `findings.json.etl`
Same schema as query_bi. Include `pipeline_shape`, e.g. `"s3 raw → stage → 30min agg fact → daily agg"`.
That shape becomes a lab archetype in 40-lookalike.
