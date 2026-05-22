---
name: sv-discovery-phase4-recommend
description: Present discovered semantic view domains to the user for review, adjustment, and explicit approval before generating handoff documents
---

# Phase 4: Recommend

## Purpose
Present the analysis results to the user in a clear, actionable format. The user must explicitly approve the domain groupings before we generate handoff documents. This is the primary decision gate.

---

## Step 4A: Present domain summary

Format and present the full discovery results:

```
# Semantic View Discovery Results

Database: <DISCOVERY_DB>
Schemas analyzed: <DISCOVERY_SCHEMAS>
Analysis window: last 30 days of query activity

---

## Recommended Domains

### Domain 1: [Name] (Confidence: HIGH)
- **Tables:** TABLE_A, TABLE_B, TABLE_C, TABLE_D
- **Central entity:** TABLE_A
- **Column count:** 47 (Standard — good single SV)
- **Join keys:**
  - TABLE_A.ID → TABLE_B.A_ID (FK constraint)
  - TABLE_B.C_ID → TABLE_C.ID (column inference + 156 co-queries)
  - TABLE_A.D_CODE → TABLE_D.CODE (column inference + 89 co-queries)
- **Evidence:** 234 avg co-queries between tables, 3 FK constraints, 87% isolation
- **Suggested SV name:** <DISCOVERY_DB>.<SCHEMA>.<DOMAIN_NAME>_SV

### Domain 2: [Name] (Confidence: MEDIUM)
- **Tables:** TABLE_E, TABLE_F, TABLE_G
- **Central entity:** TABLE_E
- **Column count:** 31 (Standard — good single SV)
- **Join keys:**
  - TABLE_E.F_ID → TABLE_F.ID (column inference + 45 co-queries)
  - TABLE_E.G_ID → TABLE_G.ID (column inference + 23 co-queries)
- **Evidence:** 34 avg co-queries, 0 FK constraints, 72% isolation
- **Suggested SV name:** <DISCOVERY_DB>.<SCHEMA>.<DOMAIN_NAME>_SV

---

## Cross-Domain Bridges
These tables appear in multiple domains and should be included in each:

- **CUSTOMERS** — shared between "Orders" and "Support" domains
  Include in both SVs as a shared dimension.
- **PRODUCTS** — shared between "Orders" and "Inventory" domains
  Include in both SVs as a shared dimension.

---

## Orphan Tables (no SV recommended)
These tables had no detectable relationships or query co-occurrence:

- TABLE_X: 0 co-queries, no FK/column relationships detected
- TABLE_Y: staging table pattern (prefixed with STG_), 0 downstream usage
- TABLE_Z: 12 rows, last altered 18 months ago (likely deprecated)
```

---

## Step 4B: Present adjustment options

After the summary, present clear options:

```
How would you like to proceed?

  1. Approve these groupings as-is
  2. Move a table from one domain to another
  3. Merge two domains into one
  4. Split a domain into two
  5. Exclude specific tables from all domains
  6. Include an orphan table in a domain
  7. Re-run scan with a different time window (e.g., 90 days instead of 30)
  8. Rename a domain or its suggested SV name

Select one or more (e.g., "1" or "2: move TABLE_X from Orders to Inventory"):
```

---

## Step 4C: Apply adjustments (loop until approved)

If the user requests changes:

### Move table
- Remove table from source domain
- Add to target domain
- Recalculate cohesion and isolation scores for both affected domains
- Re-present updated summary for the affected domains only

### Merge domains
- Combine table lists
- Recalculate all scores
- Check if merged domain exceeds size thresholds (> 100 columns → warn)
- Re-present merged domain

### Split domain
- Ask user which tables go in each half (or suggest a split based on relationship density)
- Create two new domains
- Recalculate scores for both
- Re-present both new domains

### Exclude tables
- Remove from domain
- Move to orphan list with reason: "excluded by user"
- Recalculate affected domain scores

### Include orphan
- Ask which domain to add it to
- Add and recalculate scores
- Re-present affected domain

### Re-run scan
- Return to Phase 2 with adjusted time window
- Re-run co-occurrence queries with new DATEADD range
- Return to Phase 3 for re-analysis
- Return to Phase 4 to re-present

### Rename
- Update domain name and/or suggested SV name
- Re-present affected domain

**Loop**: After each adjustment, re-present the affected section and ask again:
```
Updated. Any other changes, or approve to proceed?
```

---

## ⚠️ MANDATORY GATE

**Do NOT proceed to Phase 5 until the user explicitly approves the domain groupings.**

Recognized approval phrases:
- "approve", "approved", "looks good", "yes", "ok", "proceed", "go ahead", "1" (selecting option 1)

If ambiguous, ask: "Just to confirm — you're approving these domain groupings as final?"

---

## Output variables passed to next phase

| Variable | Contents |
|----------|----------|
| `APPROVED_DOMAINS` | Final list of domains with tables, join keys, scores, and SV names |
| `BRIDGE_TABLES` | Cross-domain shared dimensions (unchanged or updated) |
| `ORPHAN_TABLES` | Final orphan list (may have changed from user adjustments) |
