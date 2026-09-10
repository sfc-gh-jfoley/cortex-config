---
name: cortex-search-lifecycle
description: >
  Snowflake Cortex Search Service (CSS) lifecycle management. Create and configure search services,
  manage resource budgets, monitor usage and guardrails violations. Use when setting up semantic search,
  enforcing credit limits, or monitoring search service health.
triggers:
  - cortex search
  - cortex search service
  - css setup
  - css lifecycle
  - search service
  - search budgets
  - search monitoring
  - semantic search
  - cortex search guardrails
  - search service monitoring
---

> **Cortex Search Service (CSS) is Snowflake's semantic search engine.** Use this plugin to set up search services, configure budgets and credit limits, and monitor guardrails compliance. GA as of July 2, 2026.

# Cortex Search Service (CSS) Lifecycle Plugin

Complete workflow for creating, managing, and monitoring Snowflake Cortex Search Services. Three sub-skills cover the full lifecycle:

- **CSS Setup**: DDL patterns, warehouse configuration, source table setup, best practices
- **CSS Budgets**: Monthly credit limits, automated enforcement (revoke/suspend), resource governance
- **CSS Monitor**: ACCOUNT_USAGE queries, guardrails tracking, health metrics

---

## When to Use CSS Lifecycle Plugin

| Need | Use This Plugin |
|------|-----------------|
| Create a new search service | ✓ (css-setup) |
| Configure target_lag and warehouse | ✓ (css-setup) |
| Set credit limits for search | ✓ (css-budgets) |
| Monitor search guardrails violations | ✓ (css-monitor) |
| Investigate search service performance | ✓ (css-monitor) |
| Manage search service budget alerts | ✓ (css-budgets) |
| Troubleshoot search service health | ✓ (css-monitor) |

---

## Quick Navigation

### 1. **I want to create a new Cortex Search Service**

→ **`css-setup`** sub-skill

Use when:
- Setting up semantic search for the first time
- Creating a search service for a new source table
- Configuring warehouse and target_lag for search indexing

[Open css-setup workflow](#css-setup-workflow)

### 2. **I want to manage search service budgets and enforce credit limits**

→ **`css-budgets`** sub-skill

Use when:
- Setting monthly credit limits for search services
- Preventing runaway search costs
- Automating budget enforcement (revoke/suspend on overspend)
- Tracking search spending against budgets

[Open css-budgets workflow](#css-budgets-workflow)

### 3. **I want to monitor search service health and guardrails compliance**

→ **`css-monitor`** sub-skill

Use when:
- Checking search service status and usage
- Analyzing guardrails violations (rate limiting, resource constraints)
- Investigating search performance issues
- Monitoring search index freshness (target_lag)

[Open css-monitor workflow](#css-monitor-workflow)

---

## Sub-Skills

### css-setup

**Location**: `plugins/cortex-search-lifecycle/skills/css-setup/SKILL.md`

CREATE CORTEX SEARCH SERVICE DDL patterns, warehouse selection, target_lag configuration, and source table setup best practices.

- CREATE CORTEX SEARCH SERVICE syntax and required parameters
- Warehouse selection (compute, sizing, shared vs. dedicated)
- target_lag: index freshness configuration (1 minute to 24 hours)
- Source table requirements (column selection, supported types)
- Common patterns and GA feature availability

### css-budgets

**Location**: `plugins/cortex-search-lifecycle/skills/css-budgets/SKILL.md`

Resource budgets for Cortex Search Services (GA Jul 3, 2026). Monthly credit limits, automated enforcement actions, and ALTER SERVICE SET BUDGET syntax.

- CREATE/ALTER RESOURCE BUDGET for search services
- Monthly credit limit enforcement
- Automated actions: REVOKE (suspend search), NOTIFY (alert), or custom webhook
- Budget tracking and cost governance
- Resource quotas per service

### css-monitor

**Location**: `plugins/cortex-search-lifecycle/skills/css-monitor/SKILL.md`

ACCOUNT_USAGE monitoring for Cortex Search Services. CORTEX_AI_GUARDRAILS_USAGE_HISTORY view (GA Jun 16, 2026) for guardrails compliance analysis and performance troubleshooting.

- ACCOUNT_USAGE.CORTEX_SEARCH_SERVICES view: service status, indexing progress
- CORTEX_AI_GUARDRAILS_USAGE_HISTORY: rate limiting, concurrency, resource violation tracking
- Query patterns for health checks, performance analysis, and cost estimation
- Common issues and remediation steps

---

## CSS Setup Workflow {#css-setup-workflow}

```
Need to search data
  ├─ Pick source table(s)
  ├─ Select warehouse (compute for indexing)
  ├─ Configure target_lag (1 min to 24 hours)
  │   └─ Freshness vs. resource tradeoff
  │
  ├─ Choose columns to index (limit to relevant columns)
  │
  └─ Execute: CREATE CORTEX SEARCH SERVICE
       └─ Service is ready when state = READY
            └─ Start querying with semantic similarity
```

---

## CSS Budgets Workflow {#css-budgets-workflow}

```
Resource governance for search services
  ├─ Define monthly credit limits per service
  ├─ Set enforcement action (REVOKE = suspend, NOTIFY = alert, webhook)
  │   └─ When service hits limit, action fires automatically
  │
  ├─ Create/ALTER RESOURCE BUDGET
  │   └─ Syntax: CREATE RESOURCE BUDGET ... FOR CORTEX_SEARCH_SERVICES ... MONTHLY_LIMIT = N CREDITS
  │
  └─ Monitor budget consumption
       └─ ALTER SERVICE ... SET RESOURCE_BUDGET = 'budget_name'
```

---

## CSS Monitor Workflow {#css-monitor-workflow}

```
Monitor service health and usage
  ├─ Query ACCOUNT_USAGE.CORTEX_SEARCH_SERVICES
  │   ├─ Check state (READY, INDEXING, FAILED, etc.)
  │   ├─ Monitor index progress (% complete)
  │   └─ Track cumulative credits consumed
  │
  ├─ Query CORTEX_AI_GUARDRAILS_USAGE_HISTORY
  │   ├─ Rate limiting violations (requests/sec exceeded)
  │   ├─ Concurrency limit violations (simultaneous queries)
  │   ├─ Resource constraint violations (memory, CPU)
  │   └─ Cost estimation from violation patterns
  │
  └─ Health checks
       ├─ Service availability (state = READY)
       ├─ Index freshness (current_timestamp - last_index_update_ts)
       └─ Error rates and recovery
```

---

## Prerequisites

### For CSS Setup:
- Snowflake account with Cortex Search Service enabled (GA Jul 2, 2026)
- At least one source table with searchable columns (VARCHAR, STRING, etc.)
- A warehouse for search index computation (can be shared or dedicated)
- `CREATE CORTEX SEARCH SERVICE` privilege on your schema
- See `PREREQUISITES.md` for detailed setup checklist

### For CSS Budgets:
- Cortex Search Service already created
- `CREATE RESOURCE BUDGET` privilege (account admin or role with budget management)
- Optional: webhook URL for custom enforcement actions
- See `PREREQUISITES.md` for resource quota configuration

### For CSS Monitor:
- Query access to ACCOUNT_USAGE views (requires `MONITOR` grant)
- At least one active Cortex Search Service
- Optional: Data warehouse for storing monitoring results
- See `PREREQUISITES.md` for monitoring setup

---

## Positioning Relative to Other Skills

| Skill | Scope | Handoff |
|-------|-------|--------|
| `cortex-search-lifecycle` (this plugin) | Search service setup, budgets, monitoring | Creates + manages CSS |
| `cortex-agent-toolkit` | Agent creation and evaluation | Can consume CSS results via agents |
| `semantic-view-toolkit` | Semantic view lifecycle | Feeds structured data; CSS indexes unstructured |
| `cowork` | Investigation and sharing | Can include CSS results in deep research |

**Chain**: Source table → `$cortex-search-lifecycle` (setup + monitor) → Semantic search → `$cortex-agent-toolkit` (build agents on search results)

---

## Entry Points

### Via skill-loader

```bash
$cortex-search-lifecycle
"I want to create a new search service"
```
→ Routes to `css-setup`

```bash
$cortex-search-lifecycle
"I need to set credit limits for my search service"
```
→ Routes to `css-budgets`

```bash
$cortex-search-lifecycle
"I'm getting guardrails violations on my search service"
```
→ Routes to `css-monitor`

### Direct sub-skill invocation

```bash
$cortex-search-lifecycle:css-setup
# Opens CSS setup workflow directly
```

```bash
$cortex-search-lifecycle:css-budgets
# Opens CSS budgets workflow directly
```

```bash
$cortex-search-lifecycle:css-monitor
# Opens CSS monitoring workflow directly
```

---

## Quick Start

**Setup**: Create a search service for semantic search
```bash
$cortex-search-lifecycle:css-setup
→ Phase 1: Select source table and columns
→ Phase 2: Pick warehouse and configure target_lag
→ Phase 3: Execute CREATE CORTEX SEARCH SERVICE DDL
```

**Budgets**: Set and enforce monthly credit limits
```bash
$cortex-search-lifecycle:css-budgets
→ Phase 1: Define monthly credit limit
→ Phase 2: Choose enforcement action
→ Phase 3: Create resource budget and attach to service
```

**Monitor**: Check service health and guardrails compliance
```bash
$cortex-search-lifecycle:css-monitor
→ Phase 1: Query service status and usage
→ Phase 2: Analyze guardrails violations
→ Phase 3: Identify issues and remediate
```

---

## Troubleshooting

**Q: "Cortex Search Service API not available"**  
A: Cortex Search Services are GA as of Jul 2, 2026. Check your account's CS_ENABLED flag and region availability.

**Q: "Service stuck in INDEXING state"**  
A: Index computation is in progress. Check target_lag setting and warehouse compute. Use css-monitor sub-skill to track progress.

**Q: "I'm hitting guardrails rate limits"**  
A: Search service has per-account rate limits. Use css-budgets to enforce per-service limits and css-monitor to track violations.

**Q: "How do I know if my search index is fresh?"**  
A: Query ACCOUNT_USAGE.CORTEX_SEARCH_SERVICES and check last_index_update_ts vs. current_timestamp. Use css-monitor for details.

---

## Support

For setup examples, budget patterns, and monitoring queries, see `README.md`.
