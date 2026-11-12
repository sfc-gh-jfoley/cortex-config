---
name: vqr-generator
description: >
  Auto-generate verified query (VQR) candidates for a semantic view from query history
  patterns. Validates candidates execute correctly against source tables before adding.
  Use when your SV has few or no VQRs and you need them for evaluation.
triggers:
  - generate VQRs
  - verified queries
  - need more examples
  - grow eval set
  - generate questions
  - bootstrap VQRs
  - I have no verified queries
  - add VQRs to my SV
---

# VQR Generator Skill

## When to Use

Use this skill when:
- Your SV has 0 VQRs and you need them to run evaluations
- You want to grow your VQR set for better eval coverage
- You want data-driven question suggestions based on actual user behavior
- You're bootstrapping a new SV and need initial example queries

**VQRs are the foundation of SV evaluation and optimization.** Without them, sv-evaluation and sv-iterative-optimizer cannot run.

**Size note — VQRs count toward the SV's token budget.** Every VQR adds its question + SQL to the serialized SV definition. Keep the SV under ~100,000 tokens total (tables + columns + metrics + relationships + VQRs): above that, Cortex Agents prunes the SV to fit the context window, adding latency and reducing answer quality. This is why "more VQRs is better" is wrong past a point — 10–20 well-chosen VQRs beat 40 trivial ones. Curate hard; don't bulk-add.

---

## Execution Mode

Inherits the session mode declared at the toolkit router (see root `SKILL.md`). Never re-asks.

- **INTERACTIVE**: Phase 4 STOP Gate blocks for operator approval of candidates before any SV mutation.
- **AUTONOMOUS**: Phase 4 auto-selects only `VALID` candidates (discards `INVALID`, holds `NEEDS_FIX` for review), logs selections, and proceeds. **Phase 5 builds a candidate copy only after explicit mutation authorization (`VQR-GEN-INSERT`) in BOTH modes, and production changes only at `SV-PROMOTE`.** Auto-generation of candidates is allowed; auto-insertion into a customer SV is not.

---

## Workflow

```
Phase 1: Connect & Analyze SV      → get SV structure, existing VQRs, source tables
    ↓
Phase 2: Mine Query History         → find real questions users have asked
    ↓
Phase 3: Synthesize Candidates      → generate question + SQL pairs
    ↓
Phase 4: Validate                   → execute each candidate SQL, verify it works
    ↓ [STOP: user approves candidates]
Phase 5: Apply                      → candidate copy with new VQRs → evaluate → SV-PROMOTE
```

---

## Phase 1: Connect & Analyze SV

### 1.1 Get SV FQN and describe it

```sql
DESCRIBE SEMANTIC VIEW <SV_FQN>;
```

Extract:
- Tables and their columns
- Existing VQRs (if any)
- Metrics defined (these suggest natural questions)
- Dimensions defined (these suggest filter/grouping patterns)
- Relationships (these suggest cross-table questions)

### 1.2 Assess gaps

```
Current state:
  Tables: N
  Metrics: M
  Dimensions: D
  Existing VQRs: V
  
  Recommended VQR count: 10-20 (based on SV complexity)
  Gap: need ~X more VQRs
```

---

## Phase 2: Mine Query History

### 2.1 Find queries referencing SV tables

```sql
SELECT
    ah.QUERY_ID,
    qh.QUERY_TEXT,
    qh.USER_NAME,
    qh.START_TIME
FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah,
    LATERAL FLATTEN(input => ah.BASE_OBJECTS_ACCESSED) obj
JOIN SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY qh
    ON ah.QUERY_ID = qh.QUERY_ID
WHERE ah.QUERY_START_TIME >= DATEADD('day', -90, CURRENT_TIMESTAMP())
    AND obj.value:objectName::STRING IN (<SV_TABLE_FQNS>)
    AND qh.QUERY_TYPE = 'SELECT'
    AND qh.EXECUTION_STATUS = 'SUCCESS'
ORDER BY qh.START_TIME DESC
LIMIT 500;
```

### 2.2 Extract patterns

From the query set, identify:
- **Common aggregations**: GROUP BY patterns, SUM/AVG/COUNT usage
- **Common filters**: WHERE clause patterns (date ranges, status values)
- **Common joins**: which tables are joined and how
- **Top N patterns**: ORDER BY ... LIMIT queries
- **Trend patterns**: date-based grouping (by month, by quarter)

### 2.3 Cluster into question types

| Pattern Type | Example Question | Coverage |
|---|---|---|
| Simple aggregation | "What's the total revenue?" | Metrics |
| Filtered aggregation | "Revenue in California last month?" | Metrics + Dimensions |
| Top-N ranking | "Top 10 customers by revenue?" | Metrics + Dimensions |
| Trend over time | "Monthly revenue trend for 2024?" | Metrics + Time Dimensions |
| Cross-table | "Revenue by product category?" | Relationships |
| Comparison | "Revenue this quarter vs last?" | Time Dimensions |

---

## Phase 3: Synthesize Candidates

For each pattern type, generate 2-3 VQR candidates:

### VQR Format

```sql
-- Logical column names only (the names defined in DIMENSIONS/FACTS), never physical columns.
-- Here the SV defines orders.order_total AS o_totalprice and orders.order_date AS o_orderdate.
SELECT SUM(order_total) AS total_revenue
FROM __orders
WHERE order_date >= '2024-01-01' AND order_date < '2025-01-01';
```

### Generation rules

1. **Use logical column names**: Column names as defined in the SV (the `AS` alias), not physical column names. Columns stay plain — no `__` prefix on columns.
2. **Use logical table names, preferably `__`-prefixed**: The YAML verified-query docs use `FROM __sales_data`; the `CREATE SEMANTIC VIEW` example uses the bare logical name (`FROM orders AS o`). Prefer `__`. Never reference physical FQNs (`FROM PROD_DB.PUBLIC.ORDERS`).
3. **Use absolute dates**: Never `CURRENT_DATE` or relative dates — always fixed dates for reproducibility
4. **Target specific capabilities**: Each VQR should test a different SV feature (metric, dimension, relationship, filter)
5. **Keep SQL minimal**: write the smallest SQL that exercises the target capability. Simple is good; a single-table aggregate is still worth registering when it is the only VQR covering that metric (see `references/vqr-strategy.md`).
6. **Alias output to metric name, aggregate the row-level fact column**: If the SV defines `total_revenue = SUM(amount)`, write `SUM(amount) AS total_revenue` in the VQR — NOT `SUM(total_revenue)`. Metric names are not columns; referencing them inside an aggregate creates SQL that the engine expands into a broken CTE. The pattern is always `SUM(<fact_column>) AS <metric_name>`, where `<fact_column>` is the logical fact name exposed by the SV (matching the `AS` alias in the FACTS clause). See the code example above.
7. **Validate filter alignment**: If VQR SQL aggregates a fact column rather than relying on a metric, apply the same `CASE WHEN` or `WHERE` filter used in the metric definition. If `net_revenue` is defined as `SUM(CASE WHEN status <> 'CANCELLED' THEN amount END)`, the VQR SQL must include the same filter.
8. **Cross-VQR filter consistency**: If any existing VQR for the same metric already applies a filter, all new VQRs targeting that metric must apply the same filter. Inconsistent filter coverage creates contradictory ground truth.
9. **Avoid nested subqueries** (unverified heuristic): Analyst may rarely generate `WHERE col IN (SELECT ...)` or `EXISTS (SELECT ...)` shapes, so such a VQR may score poorly regardless of SV quality. No documentation states this; see Check 8 in `../../references/vqr-eval-health.md`. CTEs (for example the self-join CTEs in `vqr-strategy.md`) are fine. For cross-table filters, prefer an SV relationship and a JOIN-based condition.

### Present candidates

```
| # | Question | SQL | Tests |
|---|----------|-----|-------|
| 1 | "What was total revenue in Q1 2024?" | SELECT SUM(revenue)... | Metric: total_revenue |
| 2 | "Top 5 customers by order count?" | SELECT customer_name... | Dim + Metric + TopN |
| 3 | "Monthly revenue trend for 2024?" | SELECT DATE_TRUNC... | Time grouping |
| ... | ... | ... | ... |
```

---

## Phase 4: Validate

For each candidate, run the shared dry-run procedure in `../../references/vqr-eval-health.md`
("VQR Dry-Run"), which maps logical names to physical ones via DESCRIBE `EXPRESSION` rows. A
dry-run `FAIL` marks the candidate `NEEDS_FIX`, not `INVALID`: the translation itself may be at
fault.

Check:
- ✓ Dry-run result is `PASS`
- ✓ Returns non-empty results
- ✓ Results are reasonable (not NULL, not obviously wrong)
- ✓ Uses correct logical column names from SV definition
- ✓ If VQR SQL uses raw column aggregation (not a logical metric name), the aggregate applies the same filter as the corresponding metric definition
- ✓ Filter logic is consistent with all other VQRs that test the same metric (no VQR applies the filter while a new one omits it)

Mark each candidate: VALID / INVALID / NEEDS_FIX

**INTERACTIVE mode (STOP Gate):** Present validated candidates for user approval before proceeding to Phase 5.
**AUTONOMOUS mode:** Auto-select `VALID` candidates, discard `INVALID`, hold `NEEDS_FIX`. Log: `[AUTO-RESOLVED: VQR-GEN-VALID-SELECT → N VALID selected, M INVALID discarded, K NEEDS_FIX held]`. **Still requires explicit mutation authorization before Phase 5 applies any VQR to the customer SV.**

---

## Phase 5: Apply

> **OPERATOR_REQUIRED gate [VQR-GEN-INSERT] — required in BOTH modes:**
> Inserting VQRs into an existing customer SV is a write mutation. Explicit operator
> authorization is required before executing this phase, regardless of mode.
> Present the selected candidates and the DDL diff; do not apply until confirmed.

For approved candidates, add the VQRs to a **candidate copy**, never to production in place. Follow
`../../references/candidate-promotion.md`:

1. `RUN=$(python3 scripts/candidate.py new-run | jq -r .run)`;
   `CAND=$(python3 scripts/candidate.py name --source <SV_FQN> --kind cand --run "$RUN" | jq -r .candidate)`.
2. `SELECT GET_DDL('SEMANTIC_VIEW', '<SV_FQN>');` and save the full DDL. `DESCRIBE` returns
   property rows, not DDL text, and `ALTER SEMANTIC VIEW` cannot add verified queries.
3. Append the new entries inside the existing `AI_VERIFIED_QUERIES ( ... )` block; keep every
   existing entry and every other clause unchanged:
   ```sql
   <vqr_name> AS (
     QUESTION '<natural language question>'
     VERIFIED_AT <epoch seconds>
     ONBOARDING_QUESTION FALSE
     VERIFIED_BY '(<purpose> = <contact>)'
     SQL '<verified SQL using logical names>'
   )
   ```
   The SQL is a string literal: double every single quote inside it (`'2024-01-01'` becomes
   `''2024-01-01''`). Use `ONBOARDING_QUESTION TRUE` only for questions meant to be suggested to end
   users.
4. `candidate.py rewrite-ddl` + `register`, then `candidate.py guard`, then deploy with plain
   `CREATE SEMANTIC VIEW <CAND>`. Verify with `DESCRIBE SEMANTIC VIEW <CAND>` that the VQRs appear.
5. Evaluate the candidate (sv-evaluation), then stop at gate `SV-PROMOTE`. Replacing production
   there applies the full approved DDL with `CREATE OR ALTER`, which unsets anything omitted.

---

## Integration with Toolkit

- **Fed by sv-ddl**: after creating a SV, bootstrap VQRs
- **Feeds sv-evaluation**: VQRs enable running evals
- **Feeds sv-iterative-optimizer**: more VQRs = better eval coverage for optimization
- **Can be triggered by sv-evaluation**: if eval fails due to too few VQRs, route here

---

## Tips

- **Quality over quantity**: 10 well-crafted VQRs > 30 trivial ones
- **Cover all tools**: each metric, key dimension, and relationship should be tested by at least 1 VQR
- **Diverse difficulty**: mix simple (single table) and complex (multi-table, filtered) questions
- **User language**: phrase questions how real users would ask, not like SQL queries
