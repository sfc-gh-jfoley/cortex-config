---
name: sv-composer
description: >
  Compose multiple semantic views together — either as nested SVs (one references another)
  or as multi-SV agent tools. Handles shared dimensions, cross-domain queries, and
  generates hand-off documents for cortex-agent-toolkit.
triggers:
  - compose semantic views
  - nested SV
  - multiple SVs
  - SV references another
  - multi-domain SV
  - multi-SV agent
  - shared dimensions across SVs
  - composable semantic views
---

# SV Composer Skill

## When to Use

Use this skill when:
- You have multiple domain SVs and want them to work together
- Shared dimensions (customers, products, regions) are duplicated across SVs
- You want a single Cortex Agent with multiple SV tools
- You need to decide: nest SVs or keep them independent?

---

## Two Composition Patterns

### Pattern 1: Composable SVs via `IMPORTS`

> ⚠️ **Cortex Analyst does NOT support `IMPORTS`-based views.**
> If your workflow involves Cortex Analyst or Cortex Agents with `cortex_analyst_text_to_sql`
> tools, use **Pattern 2 (multi-SV agent)** instead. The `IMPORTS` clause is GA for direct
> `SEMANTIC_VIEW()` function queries only. Snowsight also does not support composed views.

One SV imports all entities from another SV via the `IMPORTS` clause. Enables layered semantic models:

```
Core SV (customers, products, regions)
  ├── Orders SV (references Core for customer dimensions)
  ├── Support SV (references Core for customer dimensions)
  └── Inventory SV (references Core for product dimensions)
```

**When to use IMPORTS:**
- Shared entity tables (customers, products, employees) used by 2+ domain SVs
- Want single source of truth for dimension definitions
- Domain SVs always need the shared dimensions for their queries
- You do NOT need Cortex Analyst or Snowsight on the importing SV

**Key Rules:**
- **Default imports all calcs**: By default, IMPORTS brings in every public calculation (dims, facts, metrics, VQRs, AI instructions) from the imported SV. To import only specific calcs, use FACTS/DIMENSIONS/METRICS sub-clauses inside IMPORTS (selective import).
- **Diamond imports supported**: if the same upstream SV is reachable via multiple import paths, its entities appear exactly once (deduped by owning-view identity). Name collisions between *different* (unrelated) imported views still cause a creation error.
  > ⚠️ **Selective imports do not support diamond dedup.** Using `IMPORTS (sv_a METRICS(...), sv_b METRICS(...))` sub-clauses when sv_a and sv_b share a common upstream SV produces `duplicate alias 'X'`. Only full imports (no sub-clauses) correctly deduplicate. If any two SVs you're importing share an ancestor, use full IMPORTS.
- **Logical-name references only**: Reference imported entities by logical name (e.g. `accounts.d_region`), not physical columns
- **Late binding**: Imported entities resolve at query time, not DDL time — changes to the source SV propagate automatically
- **Privileges**: Requires REFERENCES on the imported SV + SELECT on its underlying tables (base tables resolve under the source SV owner's role)
- **Transitive resolution**: If A imports B and B imports C, then A sees C's entities

**Limitations:**
- Cortex Analyst does NOT support IMPORTS-based views
- Snowsight does NOT support IMPORTS-based views
- Not replicated across accounts
- Variables from imported SVs are not available in the composing view (variables clause is not supported in composability)

**Size guardrail — each composed SV should stay under ~100,000 tokens.** Composition is itself a tool for staying under the 100K limit: when a single domain SV grows past ~100K tokens (the combined size of tables, columns, metrics, relationships, and VQRs), Cortex Agents prunes it to fit the context window, adding latency and reducing answer quality. Splitting into a core SV + domain SVs, or into multiple independent SVs composed as separate agent tools, keeps each under the threshold while preserving coverage. Estimate each SV's size (~1 token per ~4 chars of serialized DDL) before composing.

### Pattern 2: Multi-SV Agent Composition

Multiple independent SVs become separate `cortex_analyst_text_to_sql` tools in one Cortex Agent:

```
Cortex Agent
  ├── Tool: orders_analyst (→ ORDERS_SV)
  ├── Tool: support_analyst (→ SUPPORT_SV)
  └── Tool: inventory_analyst (→ INVENTORY_SV)
```

**When to use multi-SV agent:**
- Domains are genuinely independent (different business areas)
- Want the agent to route questions to the right domain
- SVs have minimal overlap (< 2 shared tables)
- SVs span different databases
- Want independent deployment/optimization per domain

---

## Decision Framework

```
Do you need Cortex Analyst / Cortex Agent text-to-sql?
  ├── YES → Pattern 2: Multi-SV Agent Composition (IMPORTS not supported by Analyst)
  └── NO  → Do your SVs share > 2 dimension tables?
            ├── YES → Pattern 1: Composable SVs via IMPORTS (extract shared dims to core SV)
            └── NO  → Pattern 2: Multi-SV Agent Composition (independent domains)
```

---

## Pattern 1 Workflow: Composable SVs via IMPORTS

### Step 1: Identify shared dimensions

```sql
-- Find tables that appear in multiple SVs
-- INFORMATION_SCHEMA.SEMANTIC_TABLES does not exist; use SHOW + DESCRIBE pattern
SHOW SEMANTIC VIEWS IN DATABASE <DB>;
-- For each SV in the result, run: DESCRIBE SEMANTIC VIEW <DB>.<SCHEMA>.<SV_NAME>;
-- Then aggregate table references across all DESCRIBE outputs to find shared tables.
-- Filter DESCRIBE output for TABLE entries and count how many SVs reference each table:
-- SELECT table_name, COUNT(DISTINCT sv_name) AS sv_count ... GROUP BY table_name HAVING sv_count > 1
```

### Step 2: Design Core SV

Extract shared tables into a "core" or "shared dimensions" SV:
- Include: dimension tables referenced by 2+ domain SVs
- Define: all relationships between shared tables
- Define: common dimensions and metrics on shared tables

### Step 3: Refactor Domain SVs

Remove shared tables from domain SVs and import the core SV instead using the `IMPORTS` clause:

```sql
CREATE OR REPLACE SEMANTIC VIEW <DB>.<SCHEMA>.ORDERS_SV
  IMPORTS (<DB>.<SCHEMA>.CORE_SV)
  TABLES (
    orders AS <DB>.<SCHEMA>.ORDERS,
    order_items AS <DB>.<SCHEMA>.ORDER_ITEMS
  )
  RELATIONSHIPS (
    -- Reference imported entities by logical name
    orders (customer_id) REFERENCES customers (customer_id)
  )
  FACTS (
    orders.order_total AS order_total COMMENT = 'Order Total'
  )
  METRICS (
    orders.total_revenue AS SUM(orders.order_total) COMMENT = 'Total Revenue'
  );
```

**Notes:**
- `IMPORTS` must appear before `TABLES`
- You reference imported entities (e.g. `customers`) by their logical name from the core SV
- You cannot reference physical columns of imported tables directly — only their defined entities
- Grant REFERENCES on the core SV and SELECT on its base tables to the domain SV owner

### Step 4: Validate IMPORTS Resolution

Verify that the importing SV correctly resolves entities from the imported SV:

```sql
-- 1. Confirm the IMPORTS relationship is established
DESCRIBE SEMANTIC VIEW <DB>.<SCHEMA>.ORDERS_SV;
-- Look for rows with kind = 'IMPORT' — these show the imported SVs

-- 2. Verify imported entities are visible
-- DESCRIBE output should list imported dimensions/facts/metrics
-- with their source SV indicated

-- 3. Test a query that exercises imported entities
SELECT * FROM TABLE(
  SNOWFLAKE.CORTEX.RUN_SEMANTIC_VIEW_QUERY(
    '<DB>.<SCHEMA>.ORDERS_SV',
    'What is total revenue by region?'  -- 'region' comes from imported CORE_SV
  )
);

-- 4. Validate privilege chain
SHOW GRANTS ON SEMANTIC VIEW <DB>.<SCHEMA>.CORE_SV;
-- Confirm the domain SV owner role has REFERENCES
-- Confirm SELECT exists on CORE_SV's underlying tables
```

**Validation checklist:**
- [ ] `DESCRIBE` shows IMPORT rows for each imported SV
- [ ] Imported entities (dimensions, facts, metrics) appear in DESCRIBE output
- [ ] Queries referencing imported entities return correct results
- [ ] Privilege chain is complete (REFERENCES + SELECT on base tables)
- [ ] Run sv-evaluation on each refactored SV — compare accuracy vs pre-refactor baseline

---

## Pattern 2 Workflow: Multi-SV Agent Composition

### Step 1: Inventory existing SVs

```sql
SHOW SEMANTIC VIEWS IN DATABASE <DB>;
```

For each SV, collect:
- FQN, table count, column count
- Domain / business area
- VQR count (for eval readiness)

### Step 2: Generate hand-off document

Produce structured output for `cortex-agent-toolkit`'s `cortex-agent-ddl` skill:

```json
{
  "agent_name": "<AGENT_NAME>",
  "description": "Multi-domain analytics agent covering orders, support, and inventory",
  "tools": [
    {
      "name": "orders_analyst",
      "type": "cortex_analyst_text_to_sql",
      "description": "Answer questions about orders, revenue, and customer transactions",
      "semantic_view": "<DB>.<SCHEMA>.ORDERS_SV",
      "warehouse": "<WAREHOUSE>"
    },
    {
      "name": "support_analyst",
      "type": "cortex_analyst_text_to_sql",
      "description": "Answer questions about support tickets, resolution times, and customer satisfaction",
      "semantic_view": "<DB>.<SCHEMA>.SUPPORT_SV",
      "warehouse": "<WAREHOUSE>"
    }
  ],
  "instructions": "Route questions to the appropriate analyst tool based on the business domain. If a question spans multiple domains, use the most relevant tool first."
}
```

### Step 3: Present and confirm

```
Multi-SV Agent Composition Plan:
  Agent: <AGENT_NAME>
  Tools: 3 (orders_analyst, support_analyst, inventory_analyst)
  
  Domain coverage:
    - Orders: 5 tables, 42 columns, 8 VQRs
    - Support: 3 tables, 28 columns, 5 VQRs
    - Inventory: 4 tables, 35 columns, 6 VQRs

  Next step: Hand off to $cortex-agent-ddl to create the agent.
  
  Proceed? (yes / adjust)
```

### Step 4: Hand off

Provide the structured JSON to the user with instructions:
```
To create this agent, invoke cortex-agent-ddl (from cortex-agent-toolkit):
  $cortex-agent-ddl
  "Create an agent with these tools: [paste JSON above]"
```

---

## Integration with Toolkit

- **Input from sv-discovery**: discovery may identify multiple domains → compose them
- **Input from sv-ddl**: after creating multiple SVs, compose them
- **Output to cortex-agent-toolkit**: hand-off format for agent creation
- **Fed by sv-evaluation**: per-SV eval ensures each component is quality before composing
