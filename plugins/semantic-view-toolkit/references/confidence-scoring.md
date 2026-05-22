# Confidence Scoring

Unified scoring model for relationship detection confidence. Combines signals from multiple detection methods into a single confidence tier.

## Confidence Tiers

| Tier | Score Range | Meaning |
|------|-------------|---------|
| **HIGH** | 0.85–1.00 | Strong evidence — include in SV without user confirmation |
| **MEDIUM** | 0.60–0.84 | Moderate evidence — suggest to user for confirmation |
| **LOW** | 0.30–0.59 | Weak evidence — mention as possible but don't auto-include |

## Scoring Rules

### Tier Assignment

| Condition | Tier |
|-----------|------|
| FK constraint exists | **HIGH** (1.0) |
| Column pattern match + ≥50 co-queries | **HIGH** |
| ≥50 co-queries alone (no column match) | **HIGH** |
| Column pattern match + 10–49 co-queries | **MEDIUM** |
| Column pattern match alone (no co-queries) | **MEDIUM** |
| Co-query only, <10 occurrences | **LOW** |

### Boost Rules

- **FK/PK boost**: If an FK or PK constraint exists between two tables, always boost one tier:
  - LOW → MEDIUM
  - MEDIUM → HIGH
  - HIGH stays HIGH

- **Data type match boost**: If the joining columns have identical data types, add +0.05 to the raw score.

- **Naming convention boost**: If column names follow a consistent pattern (e.g., both use `_ID` suffix), add +0.03.

### Combined Score Calculation

When multiple signals exist for the same table pair:

```
combined_score = max(individual_scores) + bonus_from_additional_signals
```

Bonus schedule:
- 2 signals agree: +0.05
- 3 signals agree: +0.10
- 4 signals agree: +0.15

Cap at 1.0.

## Edge Cases

### No ACCOUNT_USAGE Available

When `SNOWFLAKE.ACCOUNT_USAGE` is not accessible (Standard Edition or insufficient privileges):

- Only methods 1 (FK constraints) and 2 (column patterns) are available
- Maximum achievable confidence without co-occurrence data:
  - FK: 1.0 (unchanged)
  - Column pattern: 0.70–0.95 (no co-occurrence boost possible)
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
- Maximum confidence: 0.95 (from FK + column match, no co-occurrence boost)
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
  - Co-occurrence: 5 queries
  - Combined: max(0.70, LOW) + 0.05 = 0.75
  - Result: MEDIUM (0.75)

Example 4: LOGS.SESSION_TOKEN → SESSIONS.TOKEN
  - No FK constraint
  - Column pattern: no standard suffix (0.0)
  - Co-occurrence: 3 queries
  - Combined: 0.30 (co-query only)
  - Result: LOW (0.30)
```
