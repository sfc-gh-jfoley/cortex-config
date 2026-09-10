# Phase 1: Inventory

Fetch the SV and build a complete picture before scoring begins.

## Step 1.1 — Quick size check

```sql
SELECT GET_DDL('semantic_view', '<SV_FQN>') AS sv_ddl;
```

Count `AI_VERIFIED_QUERY` rows in DESCRIBE output. Print immediately:

```
SV:    <SV_FQN>
VQRs:  <N>  [Healthy ≤10 | Acceptable 10–20 | ⚠ Review >20]
```

If VQR count > 20:
> "VQR count exceeds 20. This often signals an SV covering multiple semantic domains.
>  After curation, consider running sv-audit to check whether splitting is warranted."

## Step 1.2 — Fetch all VQRs

```sql
DESCRIBE SEMANTIC VIEW <SV_FQN>;
```

Parse into `VQR_LIST`: list of `{ name, question, sql }`.
Parse into `SV_SCHEMA`: `{ tables: [{logical_name, physical_fqn}], metrics: [...], dimensions: [...] }`.

If VQR_LIST is empty:
> "No verified queries found on <SV_FQN>. Nothing to curate.
>  Use vqr-generator to create VQRs, or run sv-audit to check coverage."
> STOP.

## Step 1.3 — Token footprint

```sql
SELECT LENGTH(GET_DDL('semantic_view', '<SV_FQN>')) AS ddl_chars,
       ROUND(LENGTH(GET_DDL('semantic_view', '<SV_FQN>')) / 4) AS estimated_tokens;
```

Store as `SV_TOKEN_FOOTPRINT`. Print:
```
Token footprint:  ~<N> tokens   (VQRs account for ~<VQR_N * 300> tokens estimated)
```

## Step 1.4 — Agent flag check (if AGENT_FQN provided)

```sql
DESCRIBE AGENT <AGENT_FQN>;
```

Extract `experimental.EnableVQRFastPath`. If false or absent:
```
⚠ EnableVQRFastPath is not set on <AGENT_FQN>.
  ALL VQRs will be ignored for fast-path regardless of SQL quality.
  Fix: ALTER AGENT ... MODIFY LIVE VERSION SET SPECIFICATION with
       "experimental": {"EnableVQRFastPath": true}
  Continuing with static audit — fast-path activation check (Phase 4) will be skipped.
```
Store `FASTPATH_ENABLED = false`. Phase 4 will be skipped.
