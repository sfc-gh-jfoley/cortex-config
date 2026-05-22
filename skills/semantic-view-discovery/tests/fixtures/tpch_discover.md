# Discover Mode Fixture: TPCH_SF1

## Scenario

Run Discover mode against `SNOWFLAKE_SAMPLE_DATA.TPCH_SF1`.

## Expected Behavior

### Phase 1: Connect & Scope

- Database: SNOWFLAKE_SAMPLE_DATA
- Schema: TPCH_SF1
- Tables found: 8 (CUSTOMER, LINEITEM, NATION, ORDERS, PART, PARTSUPP, REGION, SUPPLIER)

### Phase 2: Scan

**FK/PK Constraints:** SNOWFLAKE_SAMPLE_DATA does not have declared constraints (sample data). Expect: "No FK/PK constraints found — proceeding with column inference."

**Column Name Inference — Expected Matches:**

| Source Table | Target Table | Join Column | Confidence |
|---|---|---|---|
| ORDERS | CUSTOMER | O_CUSTKEY → C_CUSTKEY | MEDIUM |
| LINEITEM | ORDERS | L_ORDERKEY → O_ORDERKEY | MEDIUM |
| LINEITEM | PARTSUPP | L_PARTKEY + L_SUPPKEY → PS_PARTKEY + PS_SUPPKEY | MEDIUM |
| PARTSUPP | PART | PS_PARTKEY → P_PARTKEY | MEDIUM |
| PARTSUPP | SUPPLIER | PS_SUPPKEY → S_SUPPKEY | MEDIUM |
| SUPPLIER | NATION | S_NATIONKEY → N_NATIONKEY | MEDIUM |
| CUSTOMER | NATION | C_NATIONKEY → N_NATIONKEY | MEDIUM |
| NATION | REGION | N_REGIONKEY → R_REGIONKEY | MEDIUM |

Note: TPCH uses `_KEY` suffix pattern (CUSTKEY, ORDERKEY, etc.) — the column inference step should detect these.

**Co-occurrence:** Depends on whether the account has TPCH query history. If SNOWFLAKE_SAMPLE_DATA is rarely queried, co-occurrence may be LOW.

### Phase 3: Analyze

**Expected Domains (approximate):**

1. **Orders Domain** (5-6 tables)
   - ORDERS, LINEITEM, CUSTOMER, PART, PARTSUPP, SUPPLIER
   - Central entity: ORDERS
   - Size: ~60 columns — Standard/Large

2. **Geography Domain** (2 tables)
   - NATION, REGION
   - Central entity: NATION
   - Size: ~7 columns — Compact

**Alternative valid clustering:**

1. **Orders + Customers** (ORDERS, LINEITEM, CUSTOMER)
2. **Supply Chain** (PART, PARTSUPP, SUPPLIER)
3. **Geography** (NATION, REGION)

Both are acceptable — the skill should note that TPCH is highly interconnected and present options.

### Phase 4: Recommend

Should present 2-3 domain options with:
- Table lists
- Join keys
- Confidence scores (likely MEDIUM since no FKs declared, co-occurrence depends on usage)

### Phase 5: Handoff

Each domain should produce a block like:
```
## Domain: Orders
Tables: SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.ORDERS, SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.LINEITEM, ...
Join Keys: ORDERS.O_ORDERKEY → LINEITEM.L_ORDERKEY, ...
→ Invoke $semantic-view-ddl with these tables
```

## Validation Criteria

- [ ] All 8 TPCH tables discovered
- [ ] At least 5 relationships inferred from column names
- [ ] Tables clustered into 2-3 domains (not 1 mega-domain, not 8 singletons)
- [ ] NATION/REGION grouped together (geography dimension)
- [ ] ORDERS and LINEITEM always in same domain
- [ ] Handoff output includes FQNs and join keys
- [ ] No Snowhouse queries used
- [ ] User approval gate reached before handoff
