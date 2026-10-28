---
name: telemetry-to-lab-lookalike
description: Phase 40. Design de-identified lookalike datasets (archetypes) that mirror the shape of the customer workload, plus shape-based remap signatures.
parent_skill: telemetry-to-lab
---

# 40 — Lookalike data spec

**Input:** `internal/selection.json`, `internal/findings.json`. **Outputs:** `data_spec.yaml`, `remap.md`,
`internal/evidence_map.md`.

The lab data must *feel* like their world (same grain, keys, column roles, JSON layout, skew, failure modes) and use
**none** of their names. Think "generic telco/retail/bank in their industry", not "their account with labels swapped".

## 1. Gather shape (internal only)
For each real object behind the selected intents:
- columns actually used: O9 (access history), top 20–30 by reads
- types and nullability: O10
- grain and keys: infer from GROUP BY / MERGE ON / JOIN keys in O2 SQL heads
- VARIANT layout: from `data_column:"field"` / `RECORD_ATTRIBUTES:"x"` paths in SQL heads
- volume ratios: run counts × rows per run where visible. Otherwise use relative sizes (fact ≈ 100× dim)

## 2. Define archetypes
Each archetype is a neutral table name plus **column roles**:

| Role | Meaning |
|---|---|
| `pk` / `fk:<archetype>` | keys |
| `event_ts` / `event_date` / `interval_30m` | time grain |
| `dim:<concept>` | categorical; give a value list with skew (e.g. 3 values covering 80%) |
| `measure:<unit>` | numeric with a distribution (lognormal / poisson / power-law) |
| `text:transcript` / `text:summary` | free text; generate synthetic with templates or AI_COMPLETE at setup |
| `variant:<layout>` | JSON with listed paths |
| `control:watermark` | process-control row (for the lock-contention failure moment) |

Rename every column to a generic industry term. Keep counts of columns per role similar (±30%), not identical.

## 3. Seed the failure moment
Encode the selected `failure_moment.generic_form` as data plus a broken starter object that lab-builder will turn into the
failure exercise, for example:
- `starter_proc: enrich_rowwise` loops AI_COMPLETE per row with `STATEMENT_TIMEOUT_IN_SECONDS=60` → times out at lab scale
- `starter_update: single shared watermark row` updated by 4 concurrent tasks → visible queuing
- `starter_view` that declares N columns while the base table has N+1 → schema drift error

## 4. Write `data_spec.yaml` (customer-safe)
```yaml
domain: specialty retail e-commerce     # industry, not company
hero_question: "Which product features are driving negative reviews this month, and in which stores?"
scale: {small: 5_000, medium: 50_000}  # rows for the largest fact
archetypes:
  - name: PRODUCT_REVIEWS_RAW
    grain: one row per submitted review
    columns:
      - {name: REVIEW_ID, type: VARCHAR(36), role: pk}
      - {name: REVIEW_DATE, type: DATE, role: event_date}
      - {name: CATEGORY, type: VARCHAR, role: "dim:category", values: {Apparel: 0.5, Home: 0.3, Other: 0.2}}
      - {name: CHANNEL, type: VARCHAR, role: "dim:channel", values: {web: 0.55, app: 0.3, in_store: 0.15}}
      - {name: PAYLOAD, type: VARIANT, role: "variant:review_doc", paths: [rating, text, photos[].url, product.sku]}
failure_moment:
  starter: enrich_rowwise
  description: nightly full rebuild of a review rollup that times out as volume grows
  fix: set-based AI_CLASSIFY into an incremental dynamic table with a process-once key
modules_hint: [ETL, GenAI, Query, ML]
```

## 5. Write `remap.md` (customer-safe)
For each archetype, a **shape signature** CoCo can use in the customer's account to find their equivalent objects. Phrase it
as "look for tables that...", never as "your table X":
```
PRODUCT_REVIEWS_RAW — find tables that: have one row per review id (36-char key); a DATE or DATE_*-suffixed column;
a VARIANT or long-text column with rating + free text; 2–4 low-cardinality category columns (category, channel,
language). Suggested discovery: cortex search object "product reviews ratings text", then inspect columns.
```

## 6. Write `internal/evidence_map.md` (SE only)
Archetype ↔ real object FQN, the evidence queries used, and caveats. This file never leaves `internal/`.
