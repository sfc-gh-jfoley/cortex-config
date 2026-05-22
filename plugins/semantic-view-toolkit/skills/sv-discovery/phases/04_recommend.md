---
name: sv-discovery-phase4-recommend
description: Present domain grouping recommendations to the user with interactive adjustment capability
---

# Phase 4: Recommend

## Purpose

Present the analysis results as actionable recommendations. Allow the user to adjust domain boundaries before finalizing. Gate checkpoint before handoff.

**Input variables from Phase 3:** `NAMED_DOMAINS`, `BRIDGE_TABLES`, `ORPHAN_TABLES`, `DOMAIN_JOIN_KEYS`, `COLUMN_IMPORTANCE`, `FULLY_COVERED_DOMAINS`  
**Input variables from Phase 1:** `DISCOVERY_DB`, `EXISTING_SVS`, `COVERED_TABLES`, `MODE`

---

## Step 4A: Present Recommendations

Format each domain as a recommendation card:

```
═══════════════════════════════════════════════════════════════════
 SEMANTIC VIEW RECOMMENDATIONS — <DISCOVERY_DB>
═══════════════════════════════════════════════════════════════════

━━━ Domain 1: Orders ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Confidence: HIGH (0.92)
Coverage: NOT COVERED (no existing SV)
Recommended action: CREATE NEW SV

Tables (5):
  • SALES.ORDERS (base table) — central entity, 12 relationships
  • SALES.ORDER_ITEMS (base table) — detail entity
  • SALES.CUSTOMERS (base table) — dimension
  • SALES.PRODUCTS (base table) — dimension
  • SALES.REVENUE_DAILY (dynamic table, lag: 5min) — pre-aggregated

Join Keys:
  • ORDER_ITEMS.ORDER_ID → ORDERS.ORDER_ID (FK, confidence: 1.0)
  • ORDERS.CUSTOMER_ID → CUSTOMERS.CUSTOMER_ID (FK, confidence: 1.0)
  • ORDER_ITEMS.PRODUCT_ID → PRODUCTS.PRODUCT_ID (pattern, confidence: 0.90)

Bridge tables included:
  • DIM_DATE (also in: Marketing, Support)

Column stats:
  • Tier 1 (include): 47 columns across 5 tables
  • Tier 2 (optional): 12 columns
  • Tier 3 (exclude): 8 columns (system/unused)

━━━ Domain 2: Marketing ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Confidence: MEDIUM (0.71)
Coverage: PARTIALLY COVERED (CAMPAIGNS in existing MARKETING_SV)
Recommended action: EXTEND EXISTING SV or CREATE NEW

Tables (3):
  • MARKETING.CAMPAIGNS (base table) — already in MARKETING_SV
  • MARKETING.LEADS (base table) — already in MARKETING_SV
  • MARKETING.ATTRIBUTION (base table) — NOT in any SV

Options:
  A) Add ATTRIBUTION to existing MARKETING_SV
  B) Create separate SV for ATTRIBUTION + related tables
  C) Skip (existing coverage is sufficient)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ORPHAN TABLES (no clear domain affiliation):
  • STAGING.RAW_EVENTS — 0 co-queries with other tables
  • PUBLIC.TEMP_LOAD_LOG — system table, likely not for analytics

FULLY COVERED (skip):
  • Finance domain (4 tables) — covered by ANALYTICS_DB.PUBLIC.FINANCE_SV
```

---

## Step 4B: Interactive Adjustment (GUIDED mode)

In GUIDED mode, present adjustment options:

```
Adjustments available:
  1) Move a table from one domain to another
  2) Split a domain into two
  3) Merge two domains together
  4) Add an orphan table to a domain
  5) Remove a table from a domain (make it orphan)
  6) Skip a domain entirely (don't build SV)
  7) Accept all recommendations as-is

Which adjustments would you like to make? (or "accept" to proceed)
```

**Adjustment loop:**
- After each adjustment, re-display the affected domain(s)
- Re-calculate confidence for adjusted domains
- Continue loop until user says "accept" or "done"

---

## Step 4C: AUTOPILOT Mode Behavior

In AUTOPILOT mode:
- **HIGH confidence domains:** Auto-approve, no gate
- **MEDIUM confidence domains:** Auto-approve with note "medium confidence — review recommended"
- **LOW confidence domains:** STOP and ask user
  ```
  Domain "<name>" has LOW confidence (<score>). The relationships are weak.
  
  Options:
  A) Include anyway (may produce a low-quality SV)
  B) Skip this domain
  C) Switch to GUIDED mode for this domain
  ```
- **FULLY_COVERED domains:** Auto-skip (report "skipped — already covered")
- **PARTIALLY_COVERED domains:** STOP and ask user (need decision on extend vs new)

---

## Step 4D: Final Confirmation

After all adjustments (or auto-approval):

```
Final Recommendations:

| # | Domain | Tables | Action | Confidence |
|---|--------|--------|--------|------------|
| 1 | Orders | 5 | Create new SV | HIGH |
| 2 | Marketing | 1 | Add to existing SV | MEDIUM |
| 3 | Support | 4 | Create new SV | HIGH |
| 4 | Finance | — | Skip (covered) | — |

Domains to build: <N>
Total tables covered: <N>
Remaining orphans: <N> (not included in any SV)

Proceed to handoff? (yes / adjust more)
```

**GUIDED mode:** Mandatory gate — wait for explicit "yes" or "proceed".
**AUTOPILOT mode:** Auto-proceed (unless any LOW confidence domains were included).

---

## Output Variables Passed to Phase 5

| Variable | Contents |
|----------|----------|
| `APPROVED_DOMAINS` | Final list of domains approved for SV creation |
| `SKIPPED_DOMAINS` | Domains user chose to skip |
| `DOMAIN_ACTIONS` | Per-domain action: CREATE_NEW, EXTEND_EXISTING, SKIP |
| `FINAL_ORPHANS` | Tables not assigned to any domain after adjustments |
| `ADJUSTMENT_LOG` | Record of user adjustments (for persistence) |
