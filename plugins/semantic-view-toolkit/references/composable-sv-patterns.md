# Composable Semantic View Patterns

Two composition patterns for building complex analytical systems from multiple semantic views.

## Pattern 1: Nested Semantic Views

### Concept

A semantic view can import another semantic view via the `IMPORTS` clause, pulling in its tables, dimensions, facts, metrics, and relationships. By default all public calculations are imported; you can also selectively import only specific calculations using FACTS/DIMENSIONS/METRICS sub-clauses. This creates a reusable, shared semantic layer where common business definitions are authored once and referenced by many downstream views.

### Syntax

> ⚠️ **Cortex Analyst does not support IMPORTS-based composed views.** Queries sent through
> Cortex Analyst or Cortex Agents that reference a composed semantic view will fail.
> Use Pattern 2 (Multi-SV Agent Composition) for any Analyst/Agent workflow.
> Pattern 1 is valid only for direct `SEMANTIC_VIEW()` function queries.

```sql
-- Base SV: shared account dimension (standalone — no IMPORTS needed)
CREATE OR REPLACE SEMANTIC VIEW analytics.shared.sv_account_dimension
  TABLES (
    accounts AS analytics.core.accounts
      PRIMARY KEY (d_account_id)
      COMMENT = 'Account master data'
  )
  DIMENSIONS (
    accounts.d_account_id AS account_id
      COMMENT = 'Unique account identifier',
    accounts.d_account_name AS account_name
      WITH SYNONYMS = ('company', 'client')
      COMMENT = 'Account name',
    accounts.d_industry AS industry
      COMMENT = 'Industry vertical',
    accounts.d_region AS region
      COMMENT = 'Geographic region'
  )
  METRICS (
    accounts.m_account_count AS COUNT(account_id)
      COMMENT = 'Total number of accounts'
  )
;

-- Domain SV: imports the shared account dimension via IMPORTS clause
CREATE OR REPLACE SEMANTIC VIEW analytics.sales.sv_sales
  IMPORTS (sv_account_dimension)           -- ← brings in ALL entities from sv_account_dimension
  TABLES (
    sales AS analytics.core.sales
      PRIMARY KEY (sale_id)
      COMMENT = 'Sales transactions'
  )
  DIMENSIONS (
    sales.d_sale_date AS sale_date
      COMMENT = 'Date of sale',
    sales.d_account_id AS account_id
      COMMENT = 'FK to accounts'
  )
  METRICS (
    sales.m_total_revenue AS SUM(amount)
      COMMENT = 'Total revenue from sales',
    sales.m_deal_count AS COUNT(sale_id)
      COMMENT = 'Number of deals'
  )
  RELATIONSHIPS (
    sales_to_accounts AS sales (d_account_id) REFERENCES accounts
  )
;

-- Query: revenue by industry (imported dimension + local metric)
SELECT * FROM SEMANTIC_VIEW(
  sv_sales
  DIMENSIONS accounts.d_industry
  METRICS sales.m_total_revenue
);
```

**Key syntax rules:**
- `IMPORTS` clause appears **before** `TABLES`
- By default, all public calculations (dims, facts, metrics) from the imported SV are imported, including associated entities, relationships, PKs, synonyms, comments, `ai_sql_generation`, `ai_question_categorization`, and VQRs
- To import only specific calculations, use FACTS/DIMENSIONS/METRICS sub-clauses inside IMPORTS (see Selective Imports below)
- Reference imported entities by their logical table name and calc name (e.g. `accounts.d_region`)
- Cannot reference physical columns of imported entities — only their defined dimensions/facts/metrics
- Relationships to imported entities use logical dimension/fact names
- Transitive: if SV_A imports SV_B which imports SV_C, SV_A sees all of C's entities too
- **Diamond imports are supported**: if the same upstream SV is reachable through multiple import paths, its entities appear exactly once. Name collisions between *different* (unrelated) imported views still cause a creation error.
  > ⚠️ **Exception: selective imports do not support diamond dedup.** Sub-clause syntax `IMPORTS (sv_a METRICS(...), sv_b METRICS(...))` does not deduplicate when sv_a and sv_b share a common ancestor — results in `duplicate alias 'X'`. Use full imports when any shared ancestor exists.
- TABLES can be omitted entirely if the composed view only uses imported entities
- A composed view can define new local metrics on imported entities (shadow table pattern)

### Use Case

- **Shared dimensions:** Customer, Product, Geography, Time dimensions defined once, reused across domain SVs
- **Consistency:** Changes to the base dimension SV automatically propagate to all referencing SVs
- **Governance:** Single source of truth for dimension definitions

### Limitations and Gotchas

| Issue | Description | Workaround |
|-------|-------------|------------|
| No Cortex Analyst support | Queries via Cortex Analyst/Agents fail on IMPORTS views | Use Pattern 2 (multi-SV agent) for Analyst workflows |
| No Snowsight support | Cannot view or manage composed SVs in Snowsight | Use SQL or GET_DDL to inspect |
| Not replicated | IMPORTS-based SVs are skipped during account/database replication | Recreate in target account |
| Selective vs. full import | By default all public calcs are imported. Use FACTS/DIMENSIONS/METRICS sub-clauses inside IMPORTS to restrict to specific calcs (only listed calcs are queryable; dependent calcs auto-included via minimal subgraph but not directly queryable). ⚠️ Selective imports do not support diamond deduplication — if two imported SVs share a common ancestor, use full imports. | Use full IMPORTS when any shared ancestor exists; selective IMPORTS only when imported SVs have independent entity graphs |
| Diamond imports supported | Same upstream SV reachable through multiple paths: entities appear exactly once (deduped by owning-view identity). Cross-source name collisions (two *different* views defining the same calc name) still cause a creation error. ⚠️ Only full IMPORTS deduplicates — selective imports (with METRICS/DIMS/FACTS sub-clauses) do not. | Ensure unique calc names across unrelated imported views; use full IMPORTS for diamond patterns |
| Duplicate column name in imported + local entity | If a column name is already a dimension in an imported SV, a local table with the same physical column name cannot expose that column under any alias — not even a different alias. Must omit the local dimension entirely and query via the imported one. | Omit local dimension; query via the imported dimension |
| Logical names only | Cannot reference physical columns of imported entities | Use only the defined dims/facts/metrics from the source SV |
| Late binding | Imported objects resolved at query time — if source SV drops an entity, queries fail (error 000904) | Monitor source SVs for breaking changes |
| Variables not imported | Variables defined in the source SV are not available in the composing view — importing a view with variables has no effect on the composing view's variable namespace | Define needed variables directly on the composing view |
| TABLES optional when composing | A composed view can omit TABLES entirely if it only uses imported entities | N/A — this is intentional |

### Best Practices

1. **Keep base SVs simple:** Only shared dimensions, no complex metrics
2. **One level of nesting:** Base → Domain (avoid Base → Intermediate → Domain)
3. **Clear naming:** Prefix shared SVs with `shared_` or place in dedicated schema
4. **Document dependencies:** Note which SVs depend on which base SVs
5. **Privilege setup:** Creating a composed view requires both `REFERENCES` and `SELECT` on each imported SV. At query time, imported base tables resolve under the source SV's owner role — users don't need direct access to the underlying tables.

### Selective Imports

To import only specific calculations from a source SV, list them by name using FACTS, DIMENSIONS, and METRICS sub-clauses inside IMPORTS:

```sql
CREATE OR REPLACE SEMANTIC VIEW sv_subset
  IMPORTS (
    sv_large
      DIMENSIONS ( nation.d_nation_name )
      METRICS ( orders.m_order_count )
  );
```

**Rules:**
- Only the explicitly listed calculations are directly queryable in the composed view
- Any sub-clause omitted imports nothing for that calculation type (e.g. specifying only `METRICS(...)` means no dims or facts are imported)
- Snowflake automatically imports the **minimal subgraph** of entities and relationships needed to support the listed calcs: each entity that owns a listed calc is included, plus all entities and relationships along any path between included entities
- Dependent calculations (calcs that the listed calcs reference internally) are auto-included as part of the minimal subgraph but are **not directly queryable** unless also explicitly listed

**Use case — top-down decomposition**: Start with a large SV and extract smaller scoped views for specific teams by importing only the calcs they need, without creating new SVs from scratch.

### Introspection

**DESCRIBE SEMANTIC VIEW — MODE option:**
```sql
DESC SEMANTIC VIEW <db>.<schema>.<sv_name> MODE = EXPANDED;  -- default: all entities incl. transitive imports
DESC SEMANTIC VIEW <db>.<schema>.<sv_name> MODE = COMPACT;   -- local definitions + IMPORTS clause only
```

DESCRIBE output row types for composed views:
- **IMPORT rows** — one row per directly imported SV with properties `IMPORTED_SEMANTIC_VIEW_DATABASE_NAME`, `IMPORTED_SEMANTIC_VIEW_SCHEMA_NAME`, `IMPORTED_SEMANTIC_VIEW_NAME`
- **Shadow TABLE rows** — appear when the composed view defines a local calc on an imported entity (empty `BASE_TABLE_*` values); associated METRIC/DIMENSION rows then appear under the shadow table

**SHOW SEMANTIC VIEWS** — includes an `imports` column listing direct imports as an array of FQNs:
```sql
SHOW SEMANTIC VIEWS LIKE 'SV_COMPOSED';
-- imports column: ["MY_DB.PUBLIC.SV_CUSTOMERS","MY_DB.PUBLIC.SV_ORDERS"]

SHOW SEMANTIC VIEWS LIKE 'SV_CUSTOMERS';
-- imports column: []   (non-composed views show empty array)
```

**SYSTEM$READ_YAML_FROM_SEMANTIC_VIEW** — returns the YAML representation of a composed SV, including an `imported_semantic_models` block with the full YAML of every SV in the transitive import closure:
```sql
SELECT SYSTEM$READ_YAML_FROM_SEMANTIC_VIEW('db.schema.sv_composed');
```

### YAML Format

Composable SVs are supported in the YAML format. Use the `imports` top-level block:

```yaml
imports:
  - database_name: <DB>
    schema_name: <SCHEMA>
    name: <SEMANTIC_VIEW_NAME>
```

When a composed view defines a local calc on an imported entity (shadow table), the exported YAML marks that table entry with `is_imported: true`:

```yaml
tables:
  - name: ORDERS
    is_imported: true
    metrics:
      - name: M_DOUBLE_TOTAL
        expr: orders.m_total * 2
        access_modifier: public_access
```

The `SYSTEM$READ_YAML_FROM_SEMANTIC_VIEW` output also includes an `imported_semantic_models` block containing the full YAML body of every SV in the transitive import closure.

---

## Pattern 2: Multi-SV Agent Composition

### Concept

Multiple independent semantic views become separate `cortex_analyst_text_to_sql` tools in a single Cortex Agent. The agent routes questions to the appropriate SV based on domain.

### Architecture

```
User Question
     │
     ▼
┌─────────────┐
│ Cortex Agent │  (routes to appropriate tool)
└─────┬───────┘
      │
      ├── Tool: "sales_analyst" → Sales SV
      ├── Tool: "marketing_analyst" → Marketing SV
      └── Tool: "finance_analyst" → Finance SV
```

### Agent DDL

```sql
CREATE OR REPLACE CORTEX AGENT my_analytics_agent
  TOOLS = (
    cortex_analyst_text_to_sql(
      SEMANTIC_VIEW => 'analytics.sales.order_analytics',
      DESCRIPTION => 'Answer questions about sales orders, revenue, and customer purchases'
    ),
    cortex_analyst_text_to_sql(
      SEMANTIC_VIEW => 'analytics.marketing.campaign_analytics',
      DESCRIPTION => 'Answer questions about marketing campaigns, conversions, and ad spend'
    ),
    cortex_analyst_text_to_sql(
      SEMANTIC_VIEW => 'analytics.finance.budget_analytics',
      DESCRIPTION => 'Answer questions about budgets, forecasts, and financial actuals'
    )
  )
  DESCRIPTION = 'Multi-domain analytics agent covering sales, marketing, and finance'
;
```

### Hand-Off Document Format

When the semantic-view-toolkit produces SVs intended for multi-SV agent composition, it generates a structured hand-off document that can be consumed by `cortex-agent-toolkit`'s `cortex-agent-ddl` skill:

```json
{
  "agent_composition": {
    "agent_name": "analytics.agents.my_analytics_agent",
    "description": "Multi-domain analytics agent",
    "tools": [
      {
        "type": "cortex_analyst_text_to_sql",
        "semantic_view": "analytics.sales.order_analytics",
        "tool_description": "Answer questions about sales orders, revenue, and customer purchases",
        "domain": "sales",
        "tables_covered": ["orders", "order_items", "customers"],
        "key_metrics": ["total_revenue", "avg_order_value", "customer_count"],
        "example_questions": [
          "What was total revenue last quarter?",
          "Who are our top 10 customers by spend?"
        ]
      },
      {
        "type": "cortex_analyst_text_to_sql",
        "semantic_view": "analytics.marketing.campaign_analytics",
        "tool_description": "Answer questions about marketing campaigns, conversions, and ad spend",
        "domain": "marketing",
        "tables_covered": ["campaigns", "conversions", "ad_spend"],
        "key_metrics": ["conversion_rate", "cpa", "roas"],
        "example_questions": [
          "What is our best performing campaign?",
          "What's the cost per acquisition this month?"
        ]
      }
    ],
    "routing_hints": {
      "overlap_handling": "If question spans domains, route to the domain with most relevant metrics",
      "ambiguous_terms": {
        "revenue": "sales",
        "spend": "marketing (ad_spend) or finance (budget_spend) — ask for clarification",
        "customers": "sales (customer purchases) or marketing (customer acquisition)"
      }
    }
  }
}
```

### Design Guidance: When to Nest vs When to Keep Separate

| Criterion | Use Nested SVs | Use Multi-SV Agent |
|-----------|----------------|-------------------|
| Shared dimensions | Yes — define once, reuse | No — each SV is independent |
| Domain boundaries | Single domain, multiple fact tables | Multiple distinct domains |
| Query complexity | Questions span multiple related tables | Questions target one domain at a time |
| Team ownership | Same team owns all tables | Different teams own different domains |
| Evaluation | Single evaluation covers all | Evaluate each SV independently |
| Scale | < 10 tables total | 10+ tables across domains |

### Decision Framework

```
Question: "Do these tables serve the same analytical purpose?"
  ├── YES → Single SV (possibly with nested shared dimensions)
  └── NO → Separate SVs composed in an Agent
      └── "Do they share dimension tables?"
          ├── YES → Nested base SV + domain SVs in Agent
          └── NO → Fully independent SVs in Agent
```

### Example: Hybrid Approach

```
shared.customer_dimension (Nested SV — shared)
    ↑                        ↑
sales.order_analytics     marketing.campaign_analytics
    (references shared)      (references shared)
         ↓                        ↓
    ┌──────────────────────────────┐
    │    Multi-SV Agent             │
    │  Tool 1: sales analyst        │
    │  Tool 2: marketing analyst    │
    └──────────────────────────────┘
```

This combines both patterns:
- Shared dimensions (nested SV pattern) ensure consistent customer definitions
- Multi-SV agent (composition pattern) enables domain routing
- Each domain SV is independently optimizable with GEPA

### Routing Quality

The agent routes based on tool descriptions. To improve routing accuracy:
1. Make tool descriptions specific and non-overlapping
2. Include key entity names in descriptions
3. Add `routing_hints` for ambiguous terms
4. Test with edge-case questions that could go either way
