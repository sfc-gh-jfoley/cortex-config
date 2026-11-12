# Confidence Scoring

Unified scoring model for relationship detection confidence. Combines signals from multiple detection methods into a single confidence tier.

## Confidence Tiers

| Tier | Score Range | Meaning |
|------|-------------|---------|
| **HIGH** | 0.85–1.00 | Strong evidence. Include without confirmation **only if the edge has resolved join columns** |
| **MEDIUM** | 0.60–0.84 | Moderate evidence — suggest to user for confirmation |
| **LOW** | 0.30–0.59 | Weak evidence — mention as possible but don't auto-include |

## Signal Scores

Each detection method gives a table pair one numeric score. There are at most three pairwise
signals; column usage frequency (Step 2D) ranks columns and is not a pair signal.

| Signal | Score | Join columns? |
|--------|-------|---------------|
| Declared FK constraint | 1.00 | Yes |
| Column name pattern | Suffix score from `relationship-detection.md` (0.70–0.95), +0.05 if the target PK/UNIQUE column has the same data type, capped at 0.95 | Yes |
| Co-occurrence ≥ 50 queries | 0.85 | **No** |
| Co-occurrence 10–49 queries | 0.65 | **No** |
| Co-occurrence 3–9 queries | 0.40 | **No** |

### Combined Score

```
combined_score = max(signal_scores) + 0.05 × (number_of_signals − 1)
```

Cap at 1.0. Two signals add 0.05, three add 0.10.

### Join-key rule

Co-occurrence is a table-level signal. An edge whose only signal is co-occurrence has no join
columns: record it with `join_columns = null` and `needs_join_key = true`. It may support domain
clustering but must never be emitted as a RELATIONSHIP or join key until a column pair is
confirmed (by the user, an FK, or a column-pattern match).

## Edge Cases

### No ACCOUNT_USAGE Available

When `SNOWFLAKE.ACCOUNT_USAGE` is not accessible (Standard Edition or insufficient privileges):

- Only methods 1 (FK constraints) and 2 (column patterns) are available
- Achievable confidence without co-occurrence data:
  - FK: 1.0
  - Column pattern alone: 0.70–0.95
- Warn user: "Co-occurrence analysis unavailable. Relationship confidence is based on schema metadata only."

### Zero Constraints

When no FK/PK/UNIQUE constraints exist in the schema:

- Method 1 produces no results
- Rely on column patterns (method 2) and co-occurrence (method 3)
- Set a flag: `constraints_available = false` for downstream decisions
- Consider suggesting the user add constraints for better discovery

### Zero History

When ACCESS_HISTORY has no data (new account, no queries yet):

- Method 3 produces no results
- Rely on constraints and column patterns only
- FK edges still score 1.0; pattern-only edges score at most 0.95
- Note: "No query history available. Run queries against these tables to improve relationship detection."

### Ambiguous Matches

When a column could match multiple target tables:

- Score each match independently
- Present top 3 candidates to user ranked by confidence
- If top two candidates are within 0.05 of each other, flag as ambiguous
- Ambiguous matches are always demoted one tier

## Scoring Examples

```
Example 1: ORDERS.CUSTOMER_ID → CUSTOMERS.CUSTOMER_ID
  - FK constraint exists: confidence = 1.0
  - Result: HIGH (1.0)

Example 2: ORDERS.PRODUCT_KEY → PRODUCTS.PRODUCT_KEY
  - No FK constraint
  - Column pattern match (_KEY suffix): 0.85
  - Co-occurrence: 73 queries
  - Combined: 0.85 + 0.05 (two signals) = 0.90
  - Result: HIGH (0.90)

Example 3: EVENTS.USER_REF → USERS.USER_ID
  - No FK constraint
  - Column pattern: weak match (0.70, _REF not standard)
  - Co-occurrence: 5 queries (0.40)
  - Combined: max(0.70, 0.40) + 0.05 = 0.75
  - Result: MEDIUM (0.75)

Example 4: LOGS ↔ SESSIONS
  - No FK constraint, no column pattern match
  - Co-occurrence: 3 queries (0.40)
  - Result: LOW (0.40), needs_join_key = true — not a relationship

Example 5: ORDERS ↔ WEB_EVENTS
  - No FK constraint, no column pattern match
  - Co-occurrence: 120 queries (0.85)
  - Result: HIGH (0.85) for clustering, needs_join_key = true — ask for the join columns
```

---

## Domain-Level Confidence (sv-discovery)

Edge confidence scores above apply to individual table-pair relationships. When
scoring an entire domain (cluster of tables), use a weighted average of all
internal edge confidences. The weight floor of 1 keeps FK- and pattern-only edges in the
average and avoids a zero denominator:

```
weight            = MAX(edge_co_query_count, 1)
domain_confidence = SUM(edge_confidence × weight) / SUM(weight)
```

Without ACCESS_HISTORY every weight is 1, which is the simple average.

**Tier assignment** (same thresholds as edge-level):
- ≥ 0.85 → HIGH
- 0.60–0.84 → MEDIUM
- 0.30–0.59 → LOW

**Example:**
```
Domain: Orders (3 internal edges)
  ORDERS ↔ ORDER_ITEMS: confidence=1.0, co_query_count=127
  ORDERS ↔ CUSTOMERS:   confidence=1.0, co_query_count=98
  ORDER_ITEMS ↔ PRODUCTS: confidence=0.85, co_query_count=64

domain_confidence = (1.0×127 + 1.0×98 + 0.85×64) / (127+98+64)
                  = (127 + 98 + 54.4) / 289
                  = 279.4 / 289
                  = 0.967 → HIGH
```
