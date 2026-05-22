---
name: sv-discovery-phase5-handoff
description: Format approved domain recommendations for handoff to sv-ddl skill. Persist state for resumability.
---

# Phase 5: Handoff

## Purpose

Transform approved domain recommendations into a structured format that the `sv-ddl` skill can consume directly. Optionally persist the discovery results for future reference.

**Input variables from Phase 4:** `APPROVED_DOMAINS`, `DOMAIN_ACTIONS`, `FINAL_ORPHANS`, `ADJUSTMENT_LOG`  
**Input variables from earlier phases:** `DISCOVERY_DB`, `DOMAIN_JOIN_KEYS`, `COLUMN_IMPORTANCE`, `BRIDGE_TABLES`, `EXISTING_SVS`, `RELATIONSHIP_GRAPH`, `MODE`

---

## Step 5A: Format Domain Specifications

For each domain in `APPROVED_DOMAINS` where action is `CREATE_NEW`:

```
## Domain: <domain_name>

**Target SV Name:** <DISCOVERY_DB>.<primary_schema>.<DOMAIN_NAME>_SV
**Action:** Create new semantic view

### Source Tables

| Table | Schema | Type | Role | Join Key |
|-------|--------|------|------|----------|
| ORDERS | SALES | base table | Central entity (fact) | ORDER_ID (PK) |
| ORDER_ITEMS | SALES | base table | Detail (fact) | ORDER_ITEM_ID (PK), ORDER_ID (FK→ORDERS) |
| CUSTOMERS | SALES | base table | Dimension | CUSTOMER_ID (PK) |
| PRODUCTS | SALES | base table | Dimension | PRODUCT_ID (PK) |
| REVENUE_DAILY | SALES | dynamic table (lag: 5min) | Pre-aggregated fact | DATE_KEY, PRODUCT_ID |

### Relationships (for SV RELATIONSHIPS section)

| From Table | From Column | To Table | To Column | Type | Confidence |
|-----------|-------------|----------|-----------|------|-----------|
| ORDER_ITEMS | ORDER_ID | ORDERS | ORDER_ID | FK (declared) | 1.0 |
| ORDERS | CUSTOMER_ID | CUSTOMERS | CUSTOMER_ID | FK (declared) | 1.0 |
| ORDER_ITEMS | PRODUCT_ID | PRODUCTS | PRODUCT_ID | Pattern (_ID) | 0.90 |

### Column Recommendations

**Tier 1 — Include in SV (high usage):**
- ORDERS: ORDER_ID, CUSTOMER_ID, ORDER_DATE, TOTAL_AMOUNT, STATUS, CREATED_AT
- ORDER_ITEMS: ORDER_ITEM_ID, ORDER_ID, PRODUCT_ID, QUANTITY, UNIT_PRICE, LINE_TOTAL
- CUSTOMERS: CUSTOMER_ID, CUSTOMER_NAME, EMAIL, REGION, SEGMENT
- PRODUCTS: PRODUCT_ID, PRODUCT_NAME, CATEGORY, SUBCATEGORY, UNIT_COST

**Tier 2 — Optional (moderate usage):**
- ORDERS: DISCOUNT_CODE, SHIPPING_METHOD
- CUSTOMERS: PHONE, CREATED_DATE

**Tier 3 — Exclude (unused/system):**
- ORDERS: _METADATA_FILENAME, _METADATA_FILE_ROW_NUMBER
- CUSTOMERS: ETL_LOAD_TS, IS_DELETED

### Bridge Tables (shared with other domains)
- DIM_DATE: shared with Marketing, Support domains
  - If building multiple SVs, include DIM_DATE in each

### Design Notes
- REVENUE_DAILY is a dynamic table with 5min lag — suitable as pre-aggregated metric source
- CUSTOMERS.REGION could serve as a filter dimension
- ORDER_DATE is the natural time dimension for this domain

### Confidence: HIGH (0.92)
### Detection Methods Used: FK constraints + column patterns + co-occurrence (127 co-queries avg)
```

---

## Step 5B: Format Extend-Existing Specifications

For each domain where action is `EXTEND_EXISTING`:

```
## Domain: <domain_name>

**Existing SV:** <existing_sv_fqn>
**Action:** Extend existing semantic view with new tables

### Tables to Add

| Table | Schema | Type | Relationship to Existing Tables |
|-------|--------|------|---------------------------------|
| ATTRIBUTION | MARKETING | base table | ATTRIBUTION.CAMPAIGN_ID → CAMPAIGNS.CAMPAIGN_ID |

### New Relationships to Add

| From Table | From Column | To Table | To Column | Confidence |
|-----------|-------------|----------|-----------|-----------|
| ATTRIBUTION | CAMPAIGN_ID | CAMPAIGNS | CAMPAIGN_ID | 0.85 |

### New Columns (from added tables)

**Tier 1:** ATTRIBUTION_ID, CAMPAIGN_ID, CHANNEL, ATTRIBUTION_DATE, REVENUE_ATTRIBUTED, MODEL_TYPE
**Tier 2:** UTM_SOURCE, UTM_MEDIUM, FIRST_TOUCH_DATE

### Instruction for sv-ddl
Add these tables and relationships to the existing SV DDL. Run `DESCRIBE SEMANTIC VIEW <existing_sv>` first to get current DDL, then merge.
```

---

## Step 5C: Summary Output

Present the complete handoff summary:

```
╔═══════════════════════════════════════════════════════════════╗
║  DISCOVERY COMPLETE — <DISCOVERY_DB>                         ║
╠═══════════════════════════════════════════════════════════════╣
║                                                               ║
║  Domains to create:    <N>                                   ║
║  Domains to extend:    <N>                                   ║
║  Domains skipped:      <N>                                   ║
║  Total tables covered: <N> / <TOTAL_OBJECT_COUNT>            ║
║  Remaining orphans:    <N>                                   ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝

Next Steps:
  1. sv-ddl — Build the semantic view DDL for each domain above
  2. sv-evaluation — Evaluate accuracy after creating each SV
  3. sv-gepa-optimizer — Optimize if evaluation scores are low

To build a specific domain, say:
  "Build an SV for the Orders domain using the tables above"
  → This invokes sv-ddl with the specification from this handoff
```

---

## Step 5D: Persist State (Optional)

Offer to persist discovery results for future reference:

**GUIDED mode:** Ask the user:
```
Would you like to save this discovery to <DISCOVERY_DB>._SV_TOOLKIT_META.DISCOVERY_STATE?

Benefits:
  - Resume if interrupted
  - Compare discoveries over time (schema evolution)
  - Feed domain context to other toolkit skills

(yes / no)
```

**AUTOPILOT mode:** Auto-persist without asking.

**Persistence SQL:**

```sql
-- Create meta schema if needed
CREATE SCHEMA IF NOT EXISTS <DISCOVERY_DB>._SV_TOOLKIT_META;

-- Create discovery state table
CREATE TABLE IF NOT EXISTS <DISCOVERY_DB>._SV_TOOLKIT_META.DISCOVERY_STATE (
    discovery_id VARCHAR DEFAULT UUID_STRING(),
    discovery_timestamp TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    database_name VARCHAR,
    schemas_analyzed VARIANT,
    domains VARIANT,
    relationship_graph VARIANT,
    orphan_tables VARIANT,
    bridge_tables VARIANT,
    mode VARCHAR,
    existing_svs VARIANT,
    column_importance VARIANT,
    adjustment_log VARIANT,
    PRIMARY KEY (discovery_id)
);

-- Insert this discovery run
INSERT INTO <DISCOVERY_DB>._SV_TOOLKIT_META.DISCOVERY_STATE
    (database_name, schemas_analyzed, domains, relationship_graph, orphan_tables, bridge_tables, mode, existing_svs, column_importance, adjustment_log)
SELECT
    '<DISCOVERY_DB>',
    PARSE_JSON('<schemas_json>'),
    PARSE_JSON('<domains_json>'),
    PARSE_JSON('<graph_json>'),
    PARSE_JSON('<orphans_json>'),
    PARSE_JSON('<bridges_json>'),
    '<MODE>',
    PARSE_JSON('<existing_svs_json>'),
    PARSE_JSON('<column_importance_json>'),
    PARSE_JSON('<adjustment_log_json>');
```

---

## Step 5E: Orphan Table Report

If there are orphan tables, report them separately:

```
Orphan Tables (not assigned to any domain):

| Table | Schema | Type | Reason |
|-------|--------|------|--------|
| STAGING_RAW_EVENTS | STAGING | base table | Zero co-queries, no FK relationships |
| TEMP_LOAD_LOG | PUBLIC | base table | System/ETL table, no analytical relationships |
| AUDIT_LOG | PUBLIC | base table | 2 co-queries (too few for confidence) |

These tables are not recommended for semantic views because:
  - No meaningful relationships detected to other tables
  - Low or zero query activity (not used analytically)
  - May be staging/system tables not intended for end-user queries

If any of these should be included, you can:
  - Manually assign them to a domain by re-running with adjusted scope
  - Add FK constraints to establish relationships
  - Query them alongside other tables to build co-occurrence signal
```

---

## Output (Final Deliverable)

The final output of this skill is the **Domain Specification** format shown in Step 5A/5B. This is consumed by:

- **sv-ddl** — To generate `CREATE SEMANTIC VIEW` DDL
- **The user** — As documentation of the recommended architecture
- **_SV_TOOLKIT_META** — For persistence and future reference

No further phases follow. The discovery skill's job is done once handoff specifications are produced.
