# Customer Guide: Semantic View Discovery

## Overview

This skill helps you answer: **"I have hundreds of tables — which ones should be in my semantic views, and how should I group them?"**

It works in two modes:

1. **Discover** — Scan a database and get data-driven recommendations on which tables to group into semantic views
2. **Audit** — Take an existing semantic view and find out what's missing or unused

---

## Before You Start

### Required Access

Your Snowflake role needs:
- `IMPORTED PRIVILEGES` on the `SNOWFLAKE` database (for ACCOUNT_USAGE views)
- Read access to the database/schemas you want to analyze

Check your access:
```sql
SELECT COUNT(*) FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY LIMIT 1;
-- If this returns a count, you have access.
```

### Best Results

- **30+ days of query history** gives the most meaningful co-occurrence data
- **Active users** — the tool works best when real analysts have been querying the database
- **Declared FK/PK constraints** boost confidence significantly — if your tables have them, the tool will find them automatically

---

## Discover Mode Walkthrough

### Step 1: Start

Tell the skill which database to analyze:

```
"Help me discover semantic views for ANALYTICS_DB"
```

Or scope to specific schemas:

```
"Discover semantic views for ANALYTICS_DB.SALES and ANALYTICS_DB.MARKETING"
```

### Step 2: Scope Confirmation

The skill will show you:
- Number of schemas and tables found
- Table counts per schema
- Ask you to confirm the scope

### Step 3: Automatic Scanning

The skill runs three scans (no action needed from you):

1. **FK/PK scan** — finds declared relationships in table constraints
2. **Column inference** — matches `_ID`/`_KEY` columns across tables to infer joins
3. **Query co-occurrence** — analyzes 30 days of query history to find which tables are queried together

### Step 4: Review Recommendations

You'll see domain groupings like:

```
Domain: Orders (Confidence: HIGH)
- Tables: ORDERS, ORDER_ITEMS, CUSTOMERS, PRODUCTS
- Join keys: ORDERS.CUSTOMER_ID → CUSTOMERS.ID, ORDER_ITEMS.PRODUCT_ID → PRODUCTS.ID
- Evidence: 234 avg co-queries, 2 FK constraints
- Size: 47 columns — good single SV
```

You can:
- Approve as-is
- Move tables between domains
- Merge or split domains
- Exclude tables
- Re-run with different parameters

### Step 5: Handoff

Once you approve, the skill outputs structured instructions ready for `semantic-view-ddl`:

```
→ To build this SV, invoke $semantic-view-ddl with the tables listed above.
```

---

## Audit Mode Walkthrough

### Step 1: Start

Provide the semantic view FQN:

```
"Audit ANALYTICS_DB.PUBLIC.SALES_SV"
```

### Step 2: Structure Analysis

The skill describes your SV and shows coverage stats:
- Tables included
- Columns defined vs total available
- Relationships defined
- Verified queries present

### Step 3: Usage Scan

The skill analyzes how your SV's tables are actually used:
- Which columns are queried most (and are they in the SV?)
- Which tables are joined together (and is there a RELATIONSHIP?)
- Which tables appear in JOINs with SV tables but aren't included

### Step 4: Recommendations

Prioritized improvements:

| Priority | Category | Example |
|----------|----------|---------|
| HIGH | Relationship gaps | "ORDERS and SHIPMENTS are joined in 89 queries but have no RELATIONSHIP defined" |
| HIGH | Missing tables | "SHIPMENTS is joined with ORDERS in 89 queries but not in the SV" |
| MEDIUM | Missing columns | "DISCOUNT_PCT is accessed 1,203 times but not exposed in the SV" |
| LOW | Unused columns | "FAX_NUMBER has zero accesses in 30 days" |

### Step 5: Apply

After you approve, invoke `semantic-view-ddl` to rebuild the SV with improvements applied.

---

## Confidence Scoring

Recommendations include confidence scores based on evidence:

| Score | Meaning | Based On |
|-------|---------|----------|
| HIGH | Strong recommendation | 50+ co-queries AND/OR declared FK constraint |
| MEDIUM | Good indication | 10-49 co-queries OR column name match |
| LOW | Weak signal | < 10 co-queries, no FK, inference only |

FK/PK constraints always boost confidence by one tier.

---

## Tips

1. **Start with Discover** on your most-queried database first — it will have the richest co-occurrence data
2. **Run Audit** on existing SVs quarterly to catch drift (new tables added, usage patterns changed)
3. **Cross-domain bridge tables** (like CUSTOMERS) can appear in multiple SVs — this is normal and expected
4. **Orphan tables** (no relationships, no co-queries) often don't need SV coverage — they may be staging, ETL temp, or deprecated
5. **Large domains** (100+ columns) should be split — Cortex Analyst performs better with focused SVs

---

## FAQ

**Q: Does this modify my data or create anything?**
A: No. This skill is read-only. It only runs SELECT queries against ACCOUNT_USAGE and INFORMATION_SCHEMA. Nothing is created or modified until you explicitly invoke `semantic-view-ddl` as a next step.

**Q: What if I don't have ACCOUNT_USAGE access?**
A: The FK/PK constraint scan and column inference still work (they use INFORMATION_SCHEMA only). You'll miss the co-occurrence analysis but still get useful relationship detection.

**Q: How long does it take?**
A: Typically 2-5 minutes depending on the number of tables and query history volume.

**Q: Can I re-run with different parameters?**
A: Yes — at the recommendation step, you can request a different time window, scope to different schemas, or adjust the confidence threshold.
