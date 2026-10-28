---
name: telemetry-to-lab-resolve
description: Phase 00. Resolve the customer to the right Snowflake account(s) and build the workload map.
parent_skill: telemetry-to-lab
---

# 00 — Resolve

**Inputs:** customer name (as known in Salesforce), optional angle hint (DE / analyst / AI-ML / exec).
**Outputs:** `internal/account.json`, workload map in `internal/findings.json.workload`.

## Steps

1. **Pick a neutral slug** (industry + theme + number, e.g. `retail-loyalty-01`) and create `~/telemetry-labs/<slug>/internal/`.
   Never use the customer name in the slug or any path outside `internal/`.
   Seed `internal/deny_extra.txt` with brand variants the scanner can't derive: abbreviations and spellings without
   punctuation (`Acme&Co` → `ACMECO`, `ACMEANDCO`), subsidiaries, product and platform codenames, and internal app names you
   spot in warehouse or database names (e.g. an in-house tool's name). Add more during 10-observe as you find them.
2. **Rank accounts** with template R1 (`references/snowhouse-views.md`). Salesforce names vary
   ("Corp" vs "Corporation"), so use a loose `ILIKE` and dedupe. Join usage on `(account_id, deployment)`.
3. **Pick the target.** Usually one account dominates. If two or more have material spend
   (>15% of the top), list them and **ask** which to analyze (multi-account is supported, with one observe run per account).
   Map `snowflake_deployment` → `SNOWHOUSE_IMPORT` schema (uppercase: `prod2` → `PROD2`). Verify the schema
   exists with a `LIMIT 1` probe on `JOB_ETL_V` filtered by account.
4. **Workload map** with R2. Classify each warehouse by behavior, not name:
   - *interactive/BI*: high job count, p50 < 1s, many users
   - *ETL/batch*: few service users, long p95, CALL/MERGE/INSERT heavy
   - *app/serving*: one service user, huge counts of tiny lookups
   - *AI*: AI function / agent traffic (confirmed in 10-observe/genai)
   Note names that disagree with behavior (e.g. a "GENAI" warehouse doing plain ETL).
5. Write `internal/account.json`:
```json
{"slug":"retail-loyalty-01","customer":"<real name>","account_name":"...","account_id":0,
 "deployment":"prod2","schema":"PROD2","window_days":7,
 "spend_30d":{"total":0,"wh":0,"ai":0,"ai_fn":0,"si":0,"agents":0,"coco":0,"spcs":0},
 "warehouse_classes":{"<WH>":"interactive|etl|app|ai|misc"}}
```

## Gate
Confirm the account (and secondary accounts, if any) before 10-observe. In AUTONOMOUS mode, auto-pick
only when one account holds more than 85% of spend.
