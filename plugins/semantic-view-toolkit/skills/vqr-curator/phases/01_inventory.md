# Phase 1: Inventory

Fetch the SV and build a complete picture before scoring begins.

## Step 1.1 — Quick size check

```sql
DESCRIBE SEMANTIC VIEW <SV_FQN>;
SELECT COUNT(DISTINCT "object_name") AS vqr_count
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE "object_kind" = 'AI_VERIFIED_QUERY';
```

Print immediately:

```
SV:    <SV_FQN>
VQRs:  <N>  [Healthy ≤10 | Acceptable 10–20 | ⚠ Review >20]
```

If VQR count > 20:
> "VQR count exceeds 20. Check each VQR's value against the rubric before adding more."

## Step 1.2 — Fetch all VQRs

```sql
DESCRIBE SEMANTIC VIEW <SV_FQN>;
```

Parse into `VQR_LIST`: list of `{ name, question, sql }`.
Parse into `SV_SCHEMA`: `{ tables: [{logical_name, physical_fqn}], metrics: [...], dimensions: [...], facts: [...] }`,
keeping each dimension and fact `EXPRESSION` (the dry-run in Phase 2 needs them).

If VQR_LIST is empty:
> "No verified queries found on <SV_FQN>. Nothing to curate.
>  Use vqr-generator to create VQRs, or run sv-audit to check coverage."
> STOP.

## Step 1.3 — Token footprint

```sql
SELECT LENGTH(GET_DDL('SEMANTIC_VIEW', '<SV_FQN>')) AS ddl_chars,
       ROUND(LENGTH(GET_DDL('SEMANTIC_VIEW', '<SV_FQN>')) / 2.5) AS estimated_tokens;  -- ~2.5 chars/token for DDL
```

Store as `SV_TOKEN_FOOTPRINT`. Print:
```
Token footprint:  ~<N> tokens   (VQRs account for ~<VQR_N * 300> tokens estimated)
```

## Step 1.4 — Agent flag check (if AGENT_FQN provided)

```sql
DESCRIBE AGENT <AGENT_FQN>;
```

Extract `experimental.EnableVQRFastPath` (undocumented flag; observed behavior, verify before
relying on this). If false or absent:
```
⚠ EnableVQRFastPath is not set on <AGENT_FQN>.
  Fast-path is not expected to trigger; VQRs still act as few-shot examples and eval ground truth.
  Fix: ALTER AGENT ... MODIFY LIVE VERSION SET SPECIFICATION with
       "experimental": {"EnableVQRFastPath": true}
  Continuing with static audit — fast-path activation check (Phase 4) will be skipped.
```
Store `FASTPATH_ENABLED = false`. Phase 4 will be skipped.
