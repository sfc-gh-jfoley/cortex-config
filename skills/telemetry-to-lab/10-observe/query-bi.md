# Observe pillar: Query / BI

**Templates:** O1, O2 (on warehouses classed interactive/app), R2.

## Collect
1. **Error classes** (O1). Bucket into:
   - *compile* (001003 syntax, 001006 invalid parameter, 000904 invalid identifier, 002061 window ORDER BY): hand-written or generated SQL that doesn't compile; candidates for semantic views and governed metrics
   - *discoverability/RBAC* (002003, 002043, 003001): users can't find or reach the data
   - *timeouts/cancels* (000630, 000604): runaway queries
   For each bucket record `n`, `users` and `warehouses`, plus one masked sample.
2. **BI tools in use.** Infer from service-user and warehouse naming patterns (Tableau, Qlik, Sigma, Power BI, Looker)
   and from `tag` JSON. Record the tool *type* only.
3. **Hot query shapes** (O2 on the top 3 interactive warehouses). For the top recurring hashes, record shape:
   aggregation grain, the dimension columns grouped by, time filters. These feed metric and SV design.
4. **Serving anti-patterns.** One service user running more than 100K/week identical point lookups (`WHERE key = ? LIMIT 1`)
   or `SELECT 1` keepalives. The better pattern is a hybrid table, interactive table/warehouse, or caching.
5. **Environment smells.** Production-volume reads from UAT/DEV databases.

## Emit `findings.json.query_bi`
```json
[{"id":"Q1","pattern":"compile_errors_at_scale","metric":{"jobs":197000,"users":330},
  "impact":{"users":330},"better":"semantic view + verified metrics so users stop hand-writing SQL",
  "evidence_ref":"O1 001003/001006/000904","confidence":"verified"}]
```
`confidence` is `verified` (directly measured) or `inferred` (reasoned from indirect signal; say why).
