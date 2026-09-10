---
name: css-budgets
description: >
  Set monthly credit spending limits on Cortex Search Services using Snowflake's
  tag-based budget mechanism (SNOWFLAKE.CORE.BUDGET). Configure threshold-triggered
  stored procedures to alert, revoke access, or suspend services. GA Jul 3, 2026.
triggers:
  - search service budgets
  - css budgets
  - search budgets
  - cortex search budgets
  - resource budgets
  - search spending limits
  - credit limits
  - budget enforcement
  - search cost control
---

# CSS Budgets: Spending Limits for Cortex Search Services

Monthly credit budgets for Cortex Search Services using Snowflake's native
`SNOWFLAKE.CORE.BUDGET` object with tag-based cost attribution. GA Jul 3, 2026.

---

## How It Works

Snowflake's budget mechanism uses **tags** as the attribution bridge between an object and a budget:

```
1. Create a cost-attribution tag
2. Apply the tag to the Cortex Search service
3. Create a SNOWFLAKE.CORE.BUDGET instance
4. Set monthly spending limit on the budget
5. Associate the tag with the budget (Snowflake tracks tagged service spend)
6. Add stored procedures as threshold actions (alert at 80%, revoke at 100%)
```

Budget enforcement runs periodically: standard budgets may take up to 8 hours after a threshold
is breached to execute actions. Low-latency budgets reduce this to ~2 hours.

---

## Phase 0: Prerequisites

```sql
-- Requires ACCOUNTADMIN or BUDGET_ADMIN role for budget creation
USE ROLE ACCOUNTADMIN;

-- The budget object lives in a schema you control
-- Recommended: dedicated schema for budget management
CREATE DATABASE IF NOT EXISTS budgets_db;
CREATE SCHEMA IF NOT EXISTS budgets_db.budgets_schema;
CREATE SCHEMA IF NOT EXISTS budgets_db.tags;
```

Grant required privileges to the role that will manage budgets:
```sql
GRANT CREATE SNOWFLAKE.CORE.BUDGET ON SCHEMA budgets_db.budgets_schema TO ROLE <budget_role>;
GRANT USAGE ON DATABASE budgets_db TO ROLE <budget_role>;
GRANT USAGE ON SCHEMA budgets_db.budgets_schema TO ROLE <budget_role>;
```

---

## Phase 1: Create and Apply a Cost Tag

```sql
-- Create a tag to identify the cost center
CREATE TAG IF NOT EXISTS budgets_db.tags.cost_center
  ALLOWED_VALUES 'search_production', 'search_dev', 'search_analytics'
  COMMENT = 'Cost center tag for Cortex Search budget attribution';

-- Apply the tag to the Cortex Search service
-- (Replace with your actual service FQN)
ALTER CORTEX SEARCH SERVICE IF EXISTS <db>.<schema>.<search_service_name>
  SET TAG budgets_db.tags.cost_center = 'search_production';
```

Verify the tag was applied:
```sql
SELECT SYSTEM$GET_TAG(
  'budgets_db.tags.cost_center',
  '<db>.<schema>.<search_service_name>',
  'CORTEX_SEARCH_SERVICE'
);
```

Note: Tag changes can take up to 8 hours to be reflected in budget tracking.

---

## Phase 2: Create the Budget and Set Spending Limit

```sql
-- Switch to the schema where the budget will live
USE SCHEMA budgets_db.budgets_schema;

-- Create the budget instance
CREATE SNOWFLAKE.CORE.BUDGET search_production_budget();

-- Set a monthly credit limit (e.g., 100 credits = roughly $200 at $2/credit)
CALL search_production_budget!SET_SPENDING_LIMIT(100);
```

Optionally enable low-latency enforcement (2-hour enforcement vs. standard 8-hour):
```sql
-- Low-latency option: set via Snowsight UI Admin > Cost Management > Budgets
-- or via the budget API (check current docs for ENABLE_LOW_LATENCY_BUDGET parameter)
```

---

## Phase 3: Associate the Tag with the Budget

```sql
-- Tell the budget to track spending for services tagged with our cost_center tag
CALL budgets_db.budgets_schema.search_production_budget!SET_RESOURCE_TAGS(
  [
    [(SELECT SYSTEM$REFERENCE(
        'TAG',
        'budgets_db.tags.cost_center',
        'SESSION',
        'applybudget'
      )),
      'search_production']   -- the tag value on our service
  ],
  'UNION'
);
```

Verify budget is tracking:
```sql
CALL budgets_db.budgets_schema.search_production_budget!GET_SERVICE_TYPE_USAGE_V2(
  '<YYYY-MM>',   -- start month, e.g., '2026-07'
  '<YYYY-MM>'    -- end month,   e.g., '2026-07'
);
```

---

## Phase 4: Add Threshold Actions

### Alert at 80% (email notification)

```sql
CALL budgets_db.budgets_schema.search_production_budget!SET_EMAIL_NOTIFICATIONS(
  'my_notification_integration',  -- existing NOTIFICATION INTEGRATION name
  'admin@example.com, oncall@example.com'
);

CALL budgets_db.budgets_schema.search_production_budget!SET_NOTIFICATION_THRESHOLD(80);
```

### Revoke access + suspend service at 100%

First create the stored procedure that will be called at the threshold:

> **SECURITY NOTE:** `service_name` and `role_name` in these stored procedures must come from admin-controlled configuration (e.g., a config table or hardcoded values), NOT from user input or query parameters. String concatenation in `EXECUTE IMMEDIATE` creates SQL injection risk if inputs are user-supplied.

```sql
CREATE OR REPLACE PROCEDURE budgets_db.budgets_schema.sp_revoke_and_suspend_search(
  service_name  STRING,
  role_name     STRING
)
RETURNS STRING
LANGUAGE SQL
AS
BEGIN
  -- Revoke usage from the specified role
  EXECUTE IMMEDIATE
    'REVOKE USAGE ON CORTEX SEARCH SERVICE ' || :service_name ||
    ' FROM ROLE ' || :role_name;
  -- Suspend the service (stops indexing + serving charges)
  EXECUTE IMMEDIATE
    'ALTER CORTEX SEARCH SERVICE ' || :service_name || ' SUSPEND';
  RETURN 'Budget threshold reached: access revoked and service suspended for ' || :service_name;
END;

-- Grant the SNOWFLAKE application access to call this procedure
GRANT USAGE ON DATABASE budgets_db TO APPLICATION SNOWFLAKE;
GRANT USAGE ON SCHEMA budgets_db.budgets_schema TO APPLICATION SNOWFLAKE;
GRANT USAGE ON PROCEDURE budgets_db.budgets_schema.sp_revoke_and_suspend_search(STRING, STRING)
  TO APPLICATION SNOWFLAKE;

-- Register the action at 100%
CALL budgets_db.budgets_schema.search_production_budget!ADD_CUSTOM_ACTION(
  SYSTEM$REFERENCE(
    'PROCEDURE',
    'budgets_db.budgets_schema.sp_revoke_and_suspend_search(string, string)'
  ),
  ARRAY_CONSTRUCT('<db>.<schema>.<search_service_name>', '<role_to_revoke>'),
  'ACTUAL',
  100
);
```

---

## Phase 5: Configure Service Reinstatement at Cycle Reset

At the start of each new budget month, automatically reinstate access:

```sql
CREATE OR REPLACE PROCEDURE budgets_db.budgets_schema.sp_reinstate_search(
  service_name  STRING,
  role_name     STRING
)
RETURNS STRING
LANGUAGE SQL
AS
BEGIN
  EXECUTE IMMEDIATE
    'ALTER CORTEX SEARCH SERVICE ' || :service_name || ' RESUME';
  EXECUTE IMMEDIATE
    'GRANT USAGE ON CORTEX SEARCH SERVICE ' || :service_name ||
    ' TO ROLE ' || :role_name;
  RETURN 'Service resumed and access reinstated for ' || :service_name;
END;

GRANT USAGE ON PROCEDURE budgets_db.budgets_schema.sp_reinstate_search(STRING, STRING)
  TO APPLICATION SNOWFLAKE;

CALL budgets_db.budgets_schema.search_production_budget!SET_CYCLE_START_ACTION(
  SYSTEM$REFERENCE(
    'PROCEDURE',
    'budgets_db.budgets_schema.sp_reinstate_search(string, string)'
  ),
  ARRAY_CONSTRUCT('<db>.<schema>.<search_service_name>', '<role_to_reinstate>')
);
```

---

## Monitoring

```sql
-- Current month spending
CALL budgets_db.budgets_schema.search_production_budget!GET_SERVICE_TYPE_USAGE_V2(
  '2026-07', '2026-07'
);

-- All configured threshold actions
CALL budgets_db.budgets_schema.search_production_budget!GET_CUSTOM_ACTIONS();

-- ACCOUNT_USAGE views for historical data
SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_SEARCH_DAILY_USAGE_HISTORY
WHERE SERVICE_NAME = '<search_service_name>'
  AND USAGE_DATE >= DATEADD('day', -30, CURRENT_DATE());

SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_SEARCH_BATCH_QUERY_USAGE_HISTORY
WHERE SERVICE_NAME = '<search_service_name>';
```

---

## Important Limitations

| Limitation | Detail |
|---|---|
| Enforcement latency | Standard: up to 8h; low-latency: ~2h after threshold breach |
| Tag propagation | Tag changes take up to 8h to appear in budget tracking |
| Monthly period only | Budget periods cannot be changed from monthly |
| Scope is per-service | Each service must be tagged individually |
| CoWork attribution | Requests starting in CoWork and invoking a CSS tool are attributed to CoWork, not the CSS — budget may not capture this usage |

---

## Related Skills

| Skill | Use for |
|---|---|
| `css-setup` | Create the Cortex Search service before adding a budget |
| `css-monitor` | Detailed ACCOUNT_USAGE analysis and guardrails monitoring |
| `cortex-agent-toolkit` | Agents that use Cortex Search as a tool (can also have budgets) |
