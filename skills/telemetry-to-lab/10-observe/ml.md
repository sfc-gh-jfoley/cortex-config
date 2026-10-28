# Observe pillar: ML

**Templates:** O5 (real ML calls), presence checks on `SPCS_JOB_HISTORY_ETL_V`, `CORTEX_TRAINING_JOB_ETL_V`,
`USAGE_DAILY.snowpark_container_credits`, O3 filtered to Python procedures.

## Collect
1. **What ML exists**: count only call syntax (gotcha #4). Classes: `ml_forecast`, `ml_anomaly`, `registry_predict`,
   `other_snowflake_ml`, SPCS jobs, fine-tuning jobs, Python UDF/proc training (`LANGUAGE PYTHON` with sklearn/xgboost/torch imports).
   Report `false_positive` counts too. They show how misleading naive matching is.
2. **Failures** in any of the above (O1 restricted to those jobs).
3. **Missed ML opportunities** (always `inferred`): aggregates the customer computes repeatedly that are classic model targets
   when no model exists, for example:
   - churn / port-out / cancellation tables → classification with Feature Store + Model Registry
   - order / visit / usage volume by interval → `SNOWFLAKE.ML.FORECAST`
   - threshold / exception reporting on metrics → anomaly detection
   - topic / category tagging done with LLMs on every row → a cheaper classifier trained on LLM labels
   Name the pattern, the source *shape*, and the Snowflake feature path.
4. **External ML signs**: Databricks / Unity Catalog integrations, S3 model artifact stages. These suggest ML happens off-platform.

## Emit `findings.json.ml`
Same schema. When ML presence is zero, say so explicitly. "No training, registry or SPCS in 30d" is itself a finding.
