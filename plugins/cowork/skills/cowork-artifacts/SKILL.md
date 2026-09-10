---
name: cowork-artifacts
description: "Create and manage persistent artifact references from Cortex Agent responses. Use when: creating shareable result assets, managing artifact lifecycle, permission delegation, team collaboration. Triggers: create artifact, share result, persistent reference, share findings, team collaboration."
---

# CoWork Artifacts Skill

End-to-end workflow for creating and managing persistent artifact references from Cortex Agent responses. Artifacts are versioned, shareable, and permission-aware.

---

## Overview

**Problem**: Agent generates a great result (chart, table, summary), but it's only visible in chat history. How do you turn it into a discoverable asset your team can find and use?

**Solution**: Create an **artifact** — a persistent reference to the result with:
- Versioning (track changes over time)
- Permission control (who can access, update, share)
- Lifecycle management (archive, restore, deprecate)
- Auditability (who created, when, what changed)

---

## Permission Model (Critical)

**Artifacts grant access to the artifact reference, NOT to underlying data.**

### Example: Who Can See What?

```
Table: ANALYTICS_DB.PUBLIC.REVENUE (SELECT permissions: User A ✓, User B ✗)

Artifact: "Q3 Revenue Summary" (created by User A, references REVENUE)
  ├─ User A (creator, has SELECT on REVENUE):
  │   └─ Sees full artifact with all columns
  │
  └─ User B (granted "READ" access to artifact, NO SELECT on REVENUE):
       └─ Sees artifact exists, metadata, but REVENUE data is filtered
```

**Key principle**: If User B doesn't have SELECT on REVENUE, they can't see REVENUE data in the artifact — even if they have artifact READ access.

This is a **security feature**, not a limitation. Artifacts respect your existing data ACLs.

### Permission Levels

When you grant artifact access, you choose the level:

| Level | Allows | Use Case |
|-------|--------|----------|
| **READ** | View artifact, examine data (subject to data ACL) | Sharing results, team visibility |
| **READ+UPDATE** | Read + modify artifact metadata/description, versioning | Collaborative refinement |
| **READ+SHARE** | Read + grant access to others | Cascade sharing (admin delegation) |

---

## Prerequisites

- Snowflake account with CoWork artifacts enabled (GA Jun 17, 2026)
- At least one Cortex Agent created (see `$cortex-agent-toolkit`)
- `CREATE ARTIFACT` grant on target schema
- See `PREREQUISITES.md` for full setup

---

## Phase 0: Pre-Flight Checks

Before creating artifacts, verify:

```sql
-- 1. CoWork artifacts enabled
SELECT SYSTEM$COWORK_STATUS();
-- Expected: ARTIFACTS_ENABLED = true

-- 2. Agent exists
SHOW AGENTS IN SCHEMA <your_schema>;
-- Expected: at least one agent listed

-- 3. CREATE ARTIFACT grant
SHOW GRANTS TO ROLE CURRENT_ROLE() ON SCHEMA <your_schema>;
-- Expected: CREATE ARTIFACT grant present
```

If CREATE ARTIFACT grant is missing:
```sql
USE ROLE ACCOUNTADMIN;
GRANT CREATE ARTIFACT ON SCHEMA <your_schema> TO ROLE <your_role>;
```

---

## Phase 1: Source Selection & Authentication

### 1.1 Identify the Agent

```
Prompt: "Which agent do you want to pull results from?"
→ User provides: ANALYTICS_DB.PUBLIC.MY_AGENT

Query to verify:
SELECT * FROM INFORMATION_SCHEMA.AGENTS 
WHERE AGENT_NAME = 'MY_AGENT' AND SCHEMA_NAME = 'PUBLIC';
```

### 1.2 Identify the Result

Run the agent and capture output:

```sql
CALL ANALYTICS_DB.PUBLIC.MY_AGENT(
  QUESTION => 'What was Q3 revenue by region?'
) INTO :result;
```

Extract the result artifact (chart, table, summary) that you want to make persistent.

### 1.3 Verify Data Access

```sql
-- Confirm you have SELECT on the data the agent references
SELECT * FROM ANALYTICS_DB.PUBLIC.REVENUE LIMIT 1;
-- Expected: query succeeds
```

---

## Phase 2: Create Artifact Reference

### 2.1 Define Artifact Metadata

Gather from user:
- **Artifact name** (e.g., "Q3 Revenue by Region")
- **Description** (e.g., "Agent-generated regional breakdown for executive dashboard")
- **Type** (chart, table, summary, alert)
- **Retention policy** (keep indefinitely, archive after 90 days, etc.)
- **Sensitive level** (public, internal-only, restricted)

### 2.2 Create the Artifact

```sql
CREATE ARTIFACT <schema>.artifact_q3_revenue AS
SELECT 
  REGION,
  SUM(REVENUE) AS TOTAL_REVENUE,
  COUNT(DISTINCT CUSTOMER_ID) AS CUSTOMER_COUNT
FROM ANALYTICS_DB.PUBLIC.REVENUE
WHERE YEAR(DATE) = 2026 AND MONTH(DATE) IN (7, 8, 9)
GROUP BY REGION
ORDER BY TOTAL_REVENUE DESC;

COMMENT ON ARTIFACT <schema>.artifact_q3_revenue IS
'Q3 2026 revenue by region — agent-generated for executive dashboard. 
Created: 2026-07-10. Owner: Sales Analytics team. 
Sensitivity: Internal-only. Archive after 2026-12-31.';
```

### 2.3 Verify Artifact Creation

```sql
SHOW ARTIFACTS IN SCHEMA <your_schema>;
-- Expected: artifact_q3_revenue listed
```

---

## Phase 3: Permission Delegation & Sharing

### 3.1 Grant Access by Role

Choose the permission level (READ, READ+UPDATE, READ+SHARE):

```sql
-- Grant READ access (view only)
GRANT READ ON ARTIFACT <schema>.artifact_q3_revenue TO ROLE SALES_TEAM;

-- Grant READ+UPDATE access (view + modify metadata)
GRANT READ, UPDATE ON ARTIFACT <schema>.artifact_q3_revenue TO ROLE ANALYTICS_ADMIN;

-- Grant READ+SHARE access (view + delegate to others)
GRANT READ, SHARE ON ARTIFACT <schema>.artifact_q3_revenue TO ROLE EXECUTIVE_ADMIN;
```

### 3.2 Verify Permissions

```sql
SHOW GRANTS ON ARTIFACT <schema>.artifact_q3_revenue;
```

Expected output:
```
| GRANTEE | GRANT_ROLE | GRANTED_ON | OBJECT_NAME | OBJECT_TYPE | PRIVILEGE |
|---------|-----------|-----------|-------------|------------|-----------|
| SALES_TEAM | | ARTIFACT | artifact_q3_revenue | ARTIFACT | READ |
| ANALYTICS_ADMIN | | ARTIFACT | artifact_q3_revenue | ARTIFACT | READ |
| ANALYTICS_ADMIN | | ARTIFACT | artifact_q3_revenue | ARTIFACT | UPDATE |
```

### 3.3 Communicate Artifact Availability

Share the artifact name with team members:

```
Use this artifact in your dashboards and reports:
  ANALYTICS_DB.PUBLIC.artifact_q3_revenue

To query it:
  SELECT * FROM ANALYTICS_DB.PUBLIC.artifact_q3_revenue;

Note: Data access depends on your role's SELECT grants on the underlying table.
For questions, contact the Sales Analytics team.
```

---

## Phase 4: Monitor Artifact Lifecycle

### 4.1 Track Artifact Usage

Monitor how often the artifact is queried:

```sql
SELECT 
  ARTIFACT_NAME,
  COUNT(*) AS QUERY_COUNT,
  MAX(QUERY_TIMESTAMP) AS LAST_QUERIED
FROM INFORMATION_SCHEMA.ARTIFACT_USAGE_HISTORY
WHERE ARTIFACT_NAME = 'artifact_q3_revenue'
  AND QUERY_TIMESTAMP >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY ARTIFACT_NAME;
```

### 4.2 Versioning

Update artifact when underlying data changes:

```sql
-- Version 2: Updated with latest Q3 data
ALTER ARTIFACT <schema>.artifact_q3_revenue SET AS
SELECT 
  REGION,
  SUM(REVENUE) AS TOTAL_REVENUE,
  COUNT(DISTINCT CUSTOMER_ID) AS CUSTOMER_COUNT,
  MAX(LAST_UPDATED_DATE) AS DATA_CURRENCY
FROM ANALYTICS_DB.PUBLIC.REVENUE
WHERE YEAR(DATE) = 2026 AND MONTH(DATE) IN (7, 8, 9)
GROUP BY REGION
ORDER BY TOTAL_REVENUE DESC;

COMMENT ON ARTIFACT <schema>.artifact_q3_revenue IS
'Q3 2026 revenue by region — agent-generated for executive dashboard.
Version 2 (2026-07-15): Updated with complete Q3 data.
Original: 2026-07-10. Owner: Sales Analytics team. Sensitivity: Internal-only.';
```

### 4.3 Archive or Deprecate

Mark artifact for archival at a future date:

```sql
COMMENT ON ARTIFACT <schema>.artifact_q3_revenue IS
'Q3 2026 revenue by region — [DEPRECATED as of 2026-10-01]. Use artifact_q4_revenue instead.
Archive scheduled: 2026-12-31. Contact sales-analytics@company.com for questions.';
```

Then archive when date arrives:

```sql
ALTER ARTIFACT <schema>.artifact_q3_revenue SET COMMENT = '[ARCHIVED 2026-12-31]';
-- Or drop entirely:
DROP ARTIFACT <schema>.artifact_q3_revenue;
```

---

## Troubleshooting

### Issue: "CREATE ARTIFACT privilege insufficient"
**Solution**: Grant the privilege:
```sql
USE ROLE ACCOUNTADMIN;
GRANT CREATE ARTIFACT ON SCHEMA <schema> TO ROLE <your_role>;
```

### Issue: "Teammate granted artifact access but sees no data"
**Solution**: This is expected if they lack SELECT on underlying table. Grant data access:
```sql
GRANT SELECT ON TABLE <underlying_table> TO ROLE <teammate_role>;
```
Then they will see the full artifact.

### Issue: "Artifact query is slow"
**Solution**: Check if underlying table needs optimization (clustering, search optimization):
```sql
SELECT COUNT(*) FROM ANALYTICS_DB.PUBLIC.REVENUE;

-- If query is slow, consider:
-- 1. Rebuild or cluster the table
-- 2. Add search optimization
-- 3. Create a materialized view or dynamic table for the artifact query
```

### Issue: "I need to update artifact data but don't want to change the query"
**Solution**: If data comes from a pipeline, refresh the underlying table, then re-run the artifact query:
```sql
-- After upstream pipeline refreshes REVENUE table:
CALL REFRESH_ARTIFACT('<schema>.artifact_q3_revenue');
-- Or manually update:
ALTER ARTIFACT <schema>.artifact_q3_revenue SET AS <new_query>;
```

---

## Best Practices

1. **Name artifacts clearly**: `artifact_q3_revenue`, `artifact_customer_cohort`, not `artifact_1`
2. **Document sensitivity**: Add `[RESTRICTED]`, `[PUBLIC]`, `[INTERNAL]` to comments
3. **Version artifacts**: Update comments with version history and data currency date
4. **Grant minimal access**: Start with READ, escalate to READ+UPDATE only if needed
5. **Monitor usage**: Check query history periodically; archive unused artifacts
6. **Communicate changes**: Notify teams when artifacts are updated or deprecated

---

## Next Steps

- **Share & collaborate**: Invite team members, grant access, monitor usage
- **Integrate with dashboards**: Reference artifacts in Snowflake Native App dashboards
- **Combine with deep research**: Use artifacts to persist findings from `$cowork:cowork-deep-research`
- **Build agent + artifact pipeline**: Automate artifact creation from scheduled agent runs
