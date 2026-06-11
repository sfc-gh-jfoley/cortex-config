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

### Pattern 1: Nested SVs

> ⚠️ **Not yet GA — do not recommend to customers**
> Semantic views referencing other semantic views ("composable SVs") are not supported
> in production accounts. The sv-ddl reference confirms: "Semantic views referencing
> other semantic views are not yet GA."
>
> **Default to multi-SV Agent composition instead**: configure multiple
> `cortex_analyst_text_to_sql` tools on the Cortex Agent, one per semantic view.
> Each SV handles its domain; the agent routes between them. This pattern is fully GA
> and works for all accounts today.

One SV references columns/tables from another SV. Enables layered semantic models:

```
Core SV (customers, products, regions)
  ├── Orders SV (references Core for customer dimensions)
  ├── Support SV (references Core for customer dimensions)
  └── Inventory SV (references Core for product dimensions)
```

**When to use nested:**
- Shared entity tables (customers, products, employees) used by 2+ domain SVs
- Want single source of truth for dimension definitions
- Domain SVs always need the shared dimensions for their queries

**Limitations:**
- Nested SVs must be in the same database
- Changes to the parent SV affect all child SVs (tighter coupling)
- More complex DDL to maintain

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
Do your SVs share > 2 tables?
  ├── YES → Are shared tables dimension tables (customers, products)?
  │         ├── YES → Pattern 1: Nested SVs (extract shared dims to core SV)
  │         └── NO  → Likely need to merge into one SV (not compose)
  └── NO  → Pattern 2: Multi-SV Agent Composition
```

---

## Pattern 1 Workflow: Nested SVs

### Step 1: Identify shared dimensions

```sql
-- Find tables that appear in multiple SVs
WITH sv_tables AS (
    SELECT SEMANTIC_VIEW_NAME, TABLE_NAME
    FROM <DB>.INFORMATION_SCHEMA.SEMANTIC_TABLES
)
SELECT TABLE_NAME, COUNT(DISTINCT SEMANTIC_VIEW_NAME) AS sv_count
FROM sv_tables
GROUP BY TABLE_NAME
HAVING sv_count > 1
ORDER BY sv_count DESC;
```

### Step 2: Design Core SV

Extract shared tables into a "core" or "shared dimensions" SV:
- Include: dimension tables referenced by 2+ domain SVs
- Define: all relationships between shared tables
- Define: common dimensions and metrics on shared tables

### Step 3: Refactor Domain SVs

Remove shared tables from domain SVs and reference the core SV instead. DDL pattern:

```sql
CREATE OR REPLACE SEMANTIC VIEW <DB>.<SCHEMA>.ORDERS_SV
  TABLES (
    <DB>.<SCHEMA>.ORDERS AS orders,
    <DB>.<SCHEMA>.ORDER_ITEMS AS order_items
  )
  -- Reference columns from core SV for shared dimensions
  RELATIONSHIPS (
    orders (customer_id) REFERENCES <DB>.<SCHEMA>.CORE_SV.customers (customer_id)
  )
  ...
```

### Step 4: Validate

- DESCRIBE each SV to confirm structure
- Run sv-evaluation on each refactored SV
- Compare accuracy vs pre-refactor baseline

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
