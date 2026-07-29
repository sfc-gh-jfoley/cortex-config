This plugin provides Snowflake Cortex Search Service (CSS) lifecycle management:

- **css-setup** — Create CORTEX SEARCH SERVICE, configure warehouses and target_lag, select source tables
- **css-budgets** — Set monthly credit limits for search services, enforce budgets with automated actions (Jul 3 2026 GA)
- **css-monitor** — Monitor service health, track ACCOUNT_USAGE, analyze guardrails violations (Jun 16 2026 GA for guardrails history)

To enable: `cortex plugin enable cortex-search-lifecycle`

## Prerequisites

### For All Features:
- Snowflake account with Cortex Search Service enabled (GA Jul 2, 2026)
- At least one source table with searchable columns (VARCHAR, STRING)
- A warehouse available for search index computation

### For CSS Setup Specifically:
- `CREATE CORTEX SEARCH SERVICE` privilege on target schema
- Source table must have supported column types
- Warehouse must have sufficient compute for indexing workload
- See `PREREQUISITES.md` for full DDL requirements

### For CSS Budgets Specifically:
- `CREATE RESOURCE BUDGET` privilege (account admin or role with budget management)
- Cortex Search Service already created and in READY state
- Optional: webhook endpoint for custom enforcement actions
- See `PREREQUISITES.md` for resource budget configuration

### For CSS Monitor Specifically:
- `MONITOR` grant on account (to access ACCOUNT_USAGE views)
- At least one active Cortex Search Service deployed
- Optional: data warehouse for storing historical monitoring data
- See `PREREQUISITES.md` for monitoring setup and query patterns

## Region / Account Availability

Cortex Search Services are available in all Snowflake regions (not region-gated). No special account edition required beyond standard Cortex access.

### GA Dates:
- **Jul 2, 2026**: Cortex Search Service GA (CREATE CORTEX SEARCH SERVICE)
- **Jul 3, 2026**: Resource budgets for CSS GA (CREATE RESOURCE BUDGET ... FOR CORTEX_SEARCH_SERVICES)
- **Jun 16, 2026**: CORTEX_AI_GUARDRAILS_USAGE_HISTORY view GA (monitoring sub-skill)

## Feature Flags

- `CORTEX_SEARCH_SERVICES_ENABLED` — must be true for create/setup operations
- `CORTEX_SEARCH_RESOURCE_BUDGETS_ENABLED` — must be true for budget enforcement
- `CORTEX_AI_GUARDRAILS_TRACKING_ENABLED` — must be true for guardrails monitoring

Check feature availability via: `SELECT SYSTEM$CORTEX_SEARCH_SERVICE_STATUS();` in your account.

Start with: `$cortex-search-lifecycle:css-setup` (create), `$cortex-search-lifecycle:css-budgets` (budgets), or `$cortex-search-lifecycle:css-monitor` (monitor)
