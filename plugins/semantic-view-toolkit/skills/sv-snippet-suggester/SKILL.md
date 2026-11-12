---
name: sv-snippet-suggester
description: >
  Pattern recognition and snippet suggestion for Snowflake Semantic Views.
  Given a user's table schema, business question, or partial DDL, identifies
  which of the 25 canonical SV patterns apply and explains how to implement them.
  Invoked automatically by sv-ddl (Phase 3, 4, 5) and sv-audit when patterns
  are detected or recommended. Can also be invoked directly.
triggers:
  - "what pattern should I use"
  - "how do I model"
  - "snapshot table"
  - "semi-additive"
  - "non additive by"
  - "two date columns"
  - "role playing"
  - "scd2"
  - "valid_from valid_to"
  - "asof join"
  - "window function"
  - "time intelligence"
  - "sply yoy mom"
  - "multi fact"
  - "derived metric"
  - "scoped dataset"
  - "variables semantic view"
  - "parameterized"
  - "row access policy null"
  - "caller rights sv"
  - "materialization semantic view"
  - "which snippet"
---

# SV Snippet Suggester

## Purpose

Identify which canonical Semantic View patterns apply to the user's data model
and explain concretely how to implement them. This skill covers all 25 patterns
from the official `coco-skills` snippet library.

When invoked from **sv-ddl**, it runs automatically during Phase 3 (classify),
Phase 4 (relationships), and Phase 5 (generate DDL) — injecting pattern-specific
DDL guidance at the point of use. See `../../references/sv-snippet-patterns.md` for
the full pattern catalog that drives those phases.

When invoked **directly**, run the detection flow below.

---

## Detection Flow

### Step 1 — Collect signals

Gather signals from any of: table column names, table COMMENTs, BUSINESS_CONTEXT,
existing partial DDL, or the user's plain-language description.

### Step 2 — Score against the pattern catalog

Read only the **Index** table at the top of `../../references/sv-snippet-patterns.md` and
shortlist the patterns whose signals plausibly fit. Then read only the shortlisted sections: find
each with `grep -n '^## <N>\. ' ../../references/sv-snippet-patterns.md` and read from that line to the
next `## ` heading. Do not load the whole catalog. For each shortlisted pattern, check its
**detection signals** against the collected signals. Score: MATCH / POSSIBLE / NO.

Present only MATCH and POSSIBLE results.

### Step 3 — Present ranked suggestions

Format:

```
## Detected Patterns

### [HIGH] Semi-Additive Metric  →  snippet: semi_additive_metric
Signal: BALANCE_DATE column, BALANCE_USD fact on a table named ACCOUNT_BALANCES
Problem: Summing account balances across dates double-counts.
Fix: Use NON ADDITIVE BY (balance_date) on the total_balance metric.
     Define a separate avg_daily_balance AS AVG(BALANCE_USD) for trend queries.
Synonym discipline: total_balance → "current balance", "snapshot balance", "balance as of date"
                    avg_daily_balance → "average balance", "balance trend"

### [HIGH] Range Join (SCD2, Preview)  →  snippet: range_join
Signal: VALID_FROM + VALID_TO columns on CUSTOMER_SEGMENTS
Problem: Joining orders to current customer tier silently mis-attributes historical revenue.
Fix: CONSTRAINT segment_period DISTINCT RANGE BETWEEN VALID_FROM AND VALID_TO EXCLUSIVE
     Relationship: orders(CUSTOMER_ID, ORDER_DATE) REFERENCES customer_segments(CUSTOMER_ID, BETWEEN VALID_FROM AND VALID_TO EXCLUSIVE)
Gotcha: VALID_TO must be EXCLUSIVE (first day NOT active). If data uses inclusive end dates, add +1 day in a view.

### [POSSIBLE] Role-Playing Dimensions  →  snippet: role_playing_dimensions
Signal: Two FK columns in ORDERS both ending in _DATE
...
```

### Step 4 — Ask which to implement (if interactive)

If more than one MATCH exists, ask:

> Which pattern(s) should I implement now? (Type pattern numbers, "all", or "skip")

Then generate the exact DDL additions for each selected pattern.

---

## Pattern Quick-Reference

The Index table at the top of `../../references/sv-snippet-patterns.md` is the quick reference
(pattern, signal → construct, section link). It is the only copy; do not duplicate it here.

---

## Availability Notes

Before generating DDL for these patterns, state the status:

| Pattern | Status |
|---|---|
| `materialization` | Preview (Open, all accounts). Helps Semantic SQL only; Cortex Analyst, Cortex Agents and CoWork physical SQL do not benefit |
| `range_join` | Preview |
| `multi_path_metrics`, `accumulating_snapshot` (`USING`) | Preview |
| `scoped_dataset` (SQL query as a logical table) | Generally available |
| `inline_sv` (`WITH ... AS SEMANTIC VIEW`) | Not found in Snowflake docs — verify before relying on this |
