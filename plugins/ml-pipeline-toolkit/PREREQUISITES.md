# ml-pipeline-toolkit Prerequisites

## RBAC Grants

Replace `<database>`, `<schema>`, `<role>`, `<compute_pool>`, and `<event_table>` with your values.

```sql
-- Feature Store (FeatureStore constructor creates the schema)
GRANT CREATE SCHEMA ON DATABASE <database> TO ROLE <role>;

-- ML Experiments
GRANT CREATE EXPERIMENT ON SCHEMA <database>.<schema> TO ROLE <role>;

-- Model Registry + Model Monitor
GRANT CREATE MODEL ON SCHEMA <database>.<schema> TO ROLE <role>;
GRANT CREATE MODEL MONITOR ON SCHEMA <database>.<schema> TO ROLE <role>;

-- Cortex ML Functions
GRANT CREATE SNOWFLAKE.ML.FORECAST ON SCHEMA <database>.<schema> TO ROLE <role>;
GRANT CREATE SNOWFLAKE.ML.ANOMALY_DETECTION ON SCHEMA <database>.<schema> TO ROLE <role>;
GRANT CREATE SNOWFLAKE.ML.CLASSIFICATION ON SCHEMA <database>.<schema> TO ROLE <role>;
GRANT CREATE SNOWFLAKE.ML.TOP_INSIGHTS ON SCHEMA <database>.<schema> TO ROLE <role>;

-- SPCS / REST endpoint deployment
GRANT BIND SERVICE ENDPOINT ON ACCOUNT TO ROLE <role>;  -- required for REST endpoints
GRANT USAGE ON COMPUTE POOL <compute_pool> TO ROLE <role>;

-- Event table (for ml-log-inspector Python exception logs)
GRANT SELECT ON EVENT TABLE <database>.<schema>.<event_table> TO ROLE <role>;
```

## Python Packages

| Package | Minimum Version | Notes |
|---------|----------------|-------|
| `snowflake-ml-python` | `>= 1.25.0` | Full coverage; experiments require >=1.19, REST endpoint requires >=1.25 |
| `snowflake-snowpark-python` | latest | Included with snowflake-ml-python |

Install:
```bash
pip install "snowflake-ml-python>=1.25.0"
```

Or in a Snowflake Notebook (Container Runtime):
```python
# requirements.txt
snowflake-ml-python>=1.25.0
xgboost
scikit-learn
```

## Readiness Checklist

- [ ] Role has `CREATE SCHEMA ON DATABASE` (Feature Store)
- [ ] Role has `CREATE EXPERIMENT ON SCHEMA` (Experiments)
- [ ] Role has `CREATE MODEL ON SCHEMA` (Registry)
- [ ] Role has `CREATE MODEL MONITOR ON SCHEMA` (Observability)
- [ ] Role has `BIND SERVICE ENDPOINT ON ACCOUNT` (SPCS/REST deployment)
- [ ] Compute pool available for SPCS deployment (or use `SYSTEM_COMPUTE_POOL_CPU`)
- [ ] Event table configured (`SHOW PARAMETERS LIKE 'EVENT_TABLE' IN ACCOUNT`) — needed for ml-log-inspector
- [ ] `snowflake-ml-python >= 1.25.0` installed in notebook/environment

## Region Notes

- SPCS / REST endpoint deployment (`create_service()`) is **not available in government regions**
- Cortex ML Functions (FORECAST, ANOMALY_DETECTION, CLASSIFICATION) require supported regions — check `SHOW REGIONS` for availability
