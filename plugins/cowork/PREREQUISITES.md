# CoWork Plugin Prerequisites

## Account-Level Setup

### Feature Enablement (Contact Snowflake Support if Needed)

Check if CoWork is enabled in your account:

```sql
SELECT SYSTEM$COWORK_STATUS();
```

Expected output includes:
- `ARTIFACTS_ENABLED: true` (GA Jun 17, 2026)
- `DEEP_RESEARCH_ENABLED: true` (GA Jul 7, 2026)

If either is `false`, contact your Snowflake account team to enable the feature.

---

## For Artifacts Sub-Skill

### Role Permissions Required

The role creating or managing artifacts needs these grants:

```sql
USE ROLE ACCOUNTADMIN;

GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE <your_role>;
GRANT EXECUTE AGENT ON ACCOUNT TO ROLE <your_role>;
GRANT CREATE ARTIFACT ON SCHEMA <target_schema> TO ROLE <your_role>;
GRANT MODIFY ARTIFACT ON SCHEMA <target_schema> TO ROLE <your_role>;
GRANT MONITOR ARTIFACT ON SCHEMA <target_schema> TO ROLE <your_role>;
```

### Permission Model: Data Access vs. Artifact Access

**Critical**: Artifacts grant access to the **artifact reference**, not to the underlying data.

**Scenario**:
```
Table: ANALYTICS_DB.PUBLIC.REVENUE
  ├─ User A: SELECT grant
  ├─ User B: NO SELECT grant
  
Artifact: created by User A, references REVENUE data
  ├─ User A: READ access to artifact ✓
  ├─ User B: granted READ on artifact... but cannot SELECT REVENUE
```

**Result**: User B can see the artifact exists and view its metadata, but cannot query the underlying data (unless they also have SELECT on REVENUE).

### Impact on Sharing

When you share an artifact:
1. Recipient gets access to the **artifact reference**
2. Recipient's data permissions determine what they can see in the artifact
3. If artifact contains sensitive columns the recipient can't see, those columns are masked or filtered based on their role's grants

**Example**:
- Artifact: Sales data with columns [Customer, Region, Amount, CostOfGoods]
- User A (has SELECT on all): sees full data
- User B (has SELECT on Customer, Region, Amount only): cannot see CostOfGoods
- User B granted artifact access: sees artifact, but CostOfGoods is filtered due to their data ACL

---

## For Deep Research Sub-Skill

### Role Permissions Required

```sql
USE ROLE ACCOUNTADMIN;

GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE <your_role>;
GRANT EXECUTE AGENT ON ACCOUNT TO ROLE <your_role>;
GRANT SELECT ON ALL TABLES IN SCHEMA <research_schema> TO ROLE <your_role>;
GRANT SELECT ON ALL VIEWS IN SCHEMA <research_schema> TO ROLE <your_role>;
GRANT SELECT ON DYNAMIC TABLES IN SCHEMA <research_schema> TO ROLE <your_role>;
GRANT EXECUTE ON STAGE <cortex_search_stage> TO ROLE <your_role>;
GRANT EXECUTE CORTEX SEARCH TO ROLE <your_role>;
GRANT CREATE TASK ON SCHEMA <research_schema> TO ROLE <your_role>;
```

### Cortex Search Setup

If using Cortex Search in your Deep Research workflows:

1. **Index must exist**: Create a Cortex Search service on your data
   ```sql
   CREATE CORTEX SEARCH SERVICE my_search
   ON COLUMNS (col1, col2, col3)
   FROM TABLE my_db.public.my_table
   WAREHOUSE = my_warehouse
   COMMENT = 'Search service for deep research';
   ```

2. **Grant access**:
   ```sql
   GRANT EXECUTE ON CORTEX SEARCH SERVICE my_search TO ROLE <your_role>;
   ```

3. **Test access**:
   ```sql
   SELECT * FROM TABLE(my_search(QUERY => 'test query', NUM_RESULTS => 5));
   ```

### Multi-Step Investigation Prerequisites

Each step in a Deep Research workflow may require different permissions:

- **SQL query steps**: SELECT on source tables/views
- **Cortex Search steps**: EXECUTE on Cortex Search service
- **Analysis steps**: No additional grants (analysis runs in warehouse)
- **Cross-database investigation**: SELECT on tables in all referenced databases

---

## CoWork + Cortex Agents Integration

### Prerequisites from cortex-agent-toolkit

If using CoWork artifacts or deep research **with** Cortex Agent results:

1. **Agent must exist**: Create an agent via `$cortex-agent-toolkit`
2. **Agent execution grants**: Your role must have `EXECUTE AGENT` on the target agent
3. **Tool execution grants**: If agent uses tools, ensure your role has grants on tool sources

```sql
-- Verify agent accessibility
SHOW AGENTS IN DATABASE <db>;

-- If needed, grant access
GRANT EXECUTE AGENT ON AGENT <db>.<schema>.<agent_name> TO ROLE <your_role>;
```

---

## Snowflake Account Requirements

### Minimum Edition
- **Standard** or higher (Cortex features require at least Standard)
- Artifacts and Deep Research available in Standard, Business Critical, and Federated editions

### Region Availability
- CoWork is **not region-gated** — available in all Snowflake regions (AWS, Azure, GCP)

### Warehouse Configuration
- Standard or larger warehouse for artifact creation
- For Deep Research multi-step workflows, a warehouse with 2+ credits/hour recommended (parallelizes execution steps)

---

## Pre-Flight Checklist

Before starting CoWork artifacts or deep research, verify:

```sql
-- 1. CoWork enabled
SELECT SYSTEM$COWORK_STATUS();
-- Expected: ARTIFACTS_ENABLED=true AND DEEP_RESEARCH_ENABLED=true

-- 2. CORTEX_USER role
SELECT COUNT(*) FROM SNOWFLAKE.INFORMATION_SCHEMA.APPLICABLE_ROLES 
WHERE ROLE_NAME = 'CORTEX_USER';
-- Expected: 1

-- 3. Warehouse access
USE WAREHOUSE <your_warehouse>;
SELECT CURRENT_WAREHOUSE();
-- Expected: <your_warehouse>

-- 4. For Artifacts: CREATE ARTIFACT grant
SELECT * FROM INFORMATION_SCHEMA.OBJECT_PRIVILEGES 
WHERE OBJECT_NAME = '<target_schema>' AND PRIVILEGE_TYPE = 'CREATE ARTIFACT';
-- Expected: 1 or more rows

-- 5. For Deep Research: Cortex Search available
SELECT * FROM INFORMATION_SCHEMA.OBJECTS 
WHERE OBJECT_TYPE = 'CORTEX SEARCH SERVICE';
-- Expected: >= 1 (if using search in workflows)
```

If any check fails, apply the appropriate grant from the sections above.

---

## Troubleshooting

### Issue: "CoWork feature not enabled"
**Solution**: Contact Snowflake support to enable CoWork in your account. Both artifacts and deep research are GA as of Jul 7, 2026.

### Issue: "Insufficient privileges to create artifact"
**Solution**: Verify `CREATE ARTIFACT` grant:
```sql
GRANT CREATE ARTIFACT ON SCHEMA <schema> TO ROLE <your_role>;
```

### Issue: "Cortex Search service not found"
**Solution**: Create a Cortex Search service first:
```sql
CREATE CORTEX SEARCH SERVICE my_search
ON COLUMNS (content)
FROM TABLE my_db.public.documents
WAREHOUSE = my_warehouse;
```

### Issue: "Cannot execute agent in deep research workflow"
**Solution**: Verify agent grants:
```sql
GRANT EXECUTE AGENT ON AGENT <db>.<schema>.<agent> TO ROLE <your_role>;
```

### Issue: "Teammate can't see artifact data"
**Solution**: Remember the permission model — artifact access ≠ data access. Grant data access:
```sql
GRANT SELECT ON TABLE <my_table> TO ROLE <teammate_role>;
```

Then your teammate will see the full artifact.
