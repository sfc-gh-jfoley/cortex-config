---
name: sv-rearchitect
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

# SV Rearchitect Skill

## When to Use

Use this skill when:
- You have multiple domain SVs and want them to work together
- Shared dimensions (customers, products, regions) are duplicated across SVs
- You want a single Cortex Agent with multiple SV tools
- You need to decide: nest SVs or keep them independent?

## Execution Mode

Inherits the session mode declared at the toolkit router (see root `SKILL.md`). Never re-asks.

- **INTERACTIVE**: Composition plan review gates block for explicit operator confirmation.
- **AUTONOMOUS**: Auto-accepts the Pattern 2 hand-off plan (`REARCH-HANDOFF-ACCEPT`, non-mutating),
  logs it, and continues.

This skill never alters a production semantic view. Pattern 1 builds refactored domain SVs as
candidate copies (`<SV>__CAND__<run>`, see `../../references/candidate-promotion.md`); each reaches
production only through gate `SV-PROMOTE`, which pauses in both modes.

---

## Two Composition Patterns

### Pattern 1: Composable SVs via `IMPORTS`

> ⚠️ **`IMPORTS` is not in the public CREATE SEMANTIC VIEW reference.** Only
> `SNOWFLAKE.ACCOUNT_USAGE.SEMANTIC_VIEW_IMPORTS` is documented. Syntax, privileges, limits
> (including the reported lack of Cortex Analyst and Snowsight support) and introspection are
> observed behavior: verify on the target account before relying on them. The rules and
> limitations are kept in one place, `../../references/composable-sv-patterns.md` (Pattern 1).
> If the workflow uses Cortex Analyst or Cortex Agents, use **Pattern 2** instead.

One SV imports entities from another SV via the `IMPORTS` clause. Enables layered semantic models:

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

**Size guardrail — each composed SV should stay under ~100,000 tokens.** Composition is itself a tool for staying under the 100K limit: when a single domain SV grows past ~100K tokens (the combined size of tables, columns, metrics, relationships, and VQRs), Cortex Agents prunes it to fit the context window, adding latency and reducing answer quality. Splitting into a core SV + domain SVs, or into multiple independent SVs composed as separate agent tools, keeps each under the threshold while preserving coverage. Estimate each SV's size (~1 token per ~2.5 chars of serialized DDL) before composing.

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
- SVs span different databases
- Want independent deployment/optimization per domain

---

## Decision Framework

```
Do you need Cortex Analyst / Cortex Agent text-to-sql?
  ├── YES → Pattern 2: Multi-SV Agent Composition (IMPORTS not supported by Analyst)
  └── NO  → Do 2+ domain SVs share dimension tables they always need?
            ├── YES → Pattern 1: Composable SVs via IMPORTS (extract shared dims to core SV)
            └── NO  → Pattern 2: Multi-SV Agent Composition (independent domains)

The fuller nest-vs-separate guidance is in `../../references/composable-sv-patterns.md`.
```

---

## Pattern 1 Workflow: Composable SVs via IMPORTS

### Step 1: Identify shared dimensions

```sql
-- Find tables that appear in multiple SVs
-- INFORMATION_SCHEMA.SEMANTIC_TABLES exists and can be used for metadata discovery.
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

The core SV is a new object: create it with plain `CREATE SEMANTIC VIEW` (it fails if the name
exists; never replace an existing view).

### Step 3: Refactor Domain SVs as candidates

For each domain SV, build a candidate copy from its full `GET_DDL('SEMANTIC_VIEW', ...)`
(`candidate.py new-run`, `name --kind cand`, `rewrite-ddl`, `register`, `guard`). In the
candidate, remove the shared tables and import the core SV instead (syntax unverified; see the
warning above):

```sql
CREATE SEMANTIC VIEW <CAND>   -- from candidate.py name, e.g. <DB>.<SCHEMA>.ORDERS_SV__CAND__R1A2B3C
  IMPORTS (<DB>.<SCHEMA>.CORE_SV)
  TABLES (
    orders AS <DB>.<SCHEMA>.ORDERS,
    order_items AS <DB>.<SCHEMA>.ORDER_ITEMS
  )
  RELATIONSHIPS (
    -- Reference the imported table by logical name; omit its columns (they are not local)
    orders (customer_id) REFERENCES customers
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
- Privileges for composed views are unverified; the reference records the reported rule. Check
  `SHOW GRANTS ON SEMANTIC VIEW` on the core SV before deploying

### Step 4: Validate IMPORTS Resolution

Verify that each candidate resolves entities from the core SV:

```sql
-- 1. Test a query that exercises imported entities using Semantic SQL
SELECT * FROM SEMANTIC_VIEW(
  <DB>.<SCHEMA>.ORDERS_SV__CAND__<run>
  DIMENSIONS customers.region
  METRICS orders.total_revenue
);

-- 2. Compare results with the same query against the production domain SV

-- 3. Inspect the composition (documented source; ACCOUNT_USAGE latency applies)
SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.SEMANTIC_VIEW_IMPORTS
WHERE <filter on the candidate name>;
```

**Validation checklist:**
- [ ] Queries referencing imported entities return the same results as production
- [ ] Privileges checked on the core SV
- [ ] sv-evaluation run on each candidate and on production with the same question set and pinned
      metric version, repeated ≥2 times

### Step 5: Promote

Hand each domain candidate to gate `SV-PROMOTE` (OPERATOR_REQUIRED in both modes) with the DDL diff,
evaluation evidence and discovered consumers. Clean up unpromoted candidates only through
`SV-CANDIDATE-CLEANUP`.

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

Produce the canonical hand-off document defined in `../../references/composable-sv-patterns.md`
("Hand-Off Document Format (canonical)") for `cortex-agent-toolkit`'s `agent-ddl` skill. Use that
schema exactly; the field-to-specification mapping is in the same section.

```json
{
  "agent_name": "<DB>.<SCHEMA>.<AGENT_NAME>",
  "comment": "Multi-domain analytics agent covering orders and support",
  "instructions": {
    "orchestration": "Use orders_analyst for orders and revenue; support_analyst for tickets and resolution times."
  },
  "tools": [
    {
      "name": "orders_analyst",
      "type": "cortex_analyst_text_to_sql",
      "description": "Answers questions about orders, revenue, and customer transactions.",
      "semantic_view": "<DB>.<SCHEMA>.ORDERS_SV",
      "warehouse": "<WAREHOUSE>",
      "domain": "orders",
      "tables_covered": ["orders", "order_items", "customers"],
      "key_metrics": ["total_revenue", "order_count"],
      "example_questions": ["What was total revenue last quarter?"]
    }
  ],
  "routing_hints": {}
}
```

### Step 2b: Validate Tool Descriptions

Before presenting the handoff, validate every `cortex_analyst_text_to_sql` tool:

- `description` is present and non-empty.
- It is one concise sentence about what the tool answers.
- It is specific to the tool's domain and does not overlap another tool's description.
- It does not contain table inventories, metric lists, example questions, routing rules, or implementation details.

Keep detailed metadata in `tables_covered`, `key_metrics`, and `example_questions`. Keep routing
logic in `instructions.orchestration` and `routing_hints`. If a description is missing, vague, overlapping, or overly detailed,
rewrite it before presenting the handoff.

### Step 3: Present and confirm

```
Multi-SV Agent Composition Plan:
  Agent: <AGENT_NAME>
  Tools: 3 (orders_analyst, support_analyst, inventory_analyst)
  
  Domain coverage:
    - Orders: 5 tables, 42 columns, 8 VQRs
    - Support: 3 tables, 28 columns, 5 VQRs
    - Inventory: 4 tables, 35 columns, 6 VQRs

  Next step: Hand off to $agent-ddl to create the agent.
```

**Gate ID:** `REARCH-HANDOFF-ACCEPT`

**INTERACTIVE mode:** Wait for operator confirmation before proceeding to Step 4.
```
Proceed? (yes / adjust)
```
**AUTONOMOUS mode:** Auto-accept the composition plan and log it.
`[AUTO-RESOLVED: REARCH-HANDOFF-ACCEPT → accept (non-mutating handoff plan, autonomous mode)]`

### Step 4: Hand off

Provide the structured JSON to the user with instructions:
```
To create this agent, invoke agent-ddl (from cortex-agent-toolkit):
  $agent-ddl
  "Create an agent with these tools: [paste JSON above]"
```

---

## Integration with Toolkit

- **Input from sv-discovery**: discovery may identify multiple domains → compose them
- **Input from sv-ddl**: after creating multiple SVs, compose them
- **Output to cortex-agent-toolkit**: hand-off format for agent creation
- **Fed by sv-evaluation**: per-SV eval ensures each component is quality before composing
