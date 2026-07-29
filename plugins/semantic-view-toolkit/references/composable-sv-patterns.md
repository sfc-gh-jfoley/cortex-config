# Composable Semantic View Patterns

Two composition patterns for building complex analytical systems from multiple semantic views.

## Pattern 1: Nested Semantic Views

### Concept

A semantic view can reference another semantic view as a source table, creating a hierarchical structure where shared definitions are maintained in one place.

### Syntax

> ⚠️ **Not yet GA — Private Preview only.** Semantic views referencing other semantic views
> are not supported in production accounts. Use Multi-SV Agent Composition (Pattern 2) instead.

```sql
-- Base SV: shared customer dimension
CREATE OR REPLACE SEMANTIC VIEW analytics.shared.customer_dimension
  TABLES (
    customers AS analytics.core.customers
      PRIMARY KEY (customer_id)
      COMMENT = 'Customer master data',
    segments AS analytics.core.customer_segments
      PRIMARY KEY (segment_id)
      COMMENT = 'Customer segments'
  )
  RELATIONSHIPS (
    customers_to_segments AS customers (segment_id) REFERENCES segments
  )
  DIMENSIONS (
    customers.customer_id AS customer_id
      COMMENT = 'Unique customer identifier',
    customers.customer_name AS customer_name
      COMMENT = 'Full customer name',
    customers.email AS email
      COMMENT = 'Customer email address',
    segments.segment_name AS segment_name
      COMMENT = 'Customer segment (Enterprise, SMB, Startup)',
    segments.tier AS tier
      COMMENT = 'Value tier (Gold, Silver, Bronze)'
  )
;

-- Domain SV: references the customer dimension SV
-- ⚠️ Composable SVs (SV referencing another SV) are not yet GA
CREATE OR REPLACE SEMANTIC VIEW analytics.sales.order_analytics
  TABLES (
    orders AS analytics.core.orders
      PRIMARY KEY (order_id)
      COMMENT = 'Order transactions',
    customers AS analytics.shared.customer_dimension  -- References another SV!
      PRIMARY KEY (customer_id)
      COMMENT = 'Shared customer dimension'
  )
  RELATIONSHIPS (
    orders_to_customers AS orders (customer_id) REFERENCES customers
  )
  FACTS (
    orders.order_amount AS order_amount
      COMMENT = 'Order total in USD',
    orders.quantity AS quantity
      COMMENT = 'Number of items ordered'
  )
  DIMENSIONS (
    customers.customer_name AS customer_name
      COMMENT = 'From shared customer dimension',
    customers.segment_name AS segment_name
      COMMENT = 'From shared customer dimension'
  )
  METRICS (
    orders.total_revenue AS SUM(order_amount)
      COMMENT = 'Total revenue from orders'
  )
;
```

### Use Case

- **Shared dimensions:** Customer, Product, Geography, Time dimensions defined once, reused across domain SVs
- **Consistency:** Changes to the base dimension SV automatically propagate to all referencing SVs
- **Governance:** Single source of truth for dimension definitions

### Limitations and Gotchas

| Issue | Description | Workaround |
|-------|-------------|------------|
| Circular references | SV A → SV B → SV A | Not allowed; design acyclic hierarchy |
| Depth limit | Deep nesting (3+ levels) may impact query planning | Keep hierarchy flat (max 2 levels) |
| ALTER propagation | Altering base SV may break referencing SVs | Test all dependents after change |
| Column resolution | Ambiguous columns across nested SVs | Always use table alias prefix |
| Performance | Additional indirection layer | Negligible for most queries |
| Evaluation | VQR evaluation tests the full resolved query | Base SV changes can affect domain SV eval scores |

### Best Practices

1. **Keep base SVs simple:** Only shared dimensions, no complex metrics
2. **One level of nesting:** Base → Domain (avoid Base → Intermediate → Domain)
3. **Clear naming:** Prefix shared SVs with `shared_` or place in dedicated schema
4. **Document dependencies:** Note which SVs depend on which base SVs

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
