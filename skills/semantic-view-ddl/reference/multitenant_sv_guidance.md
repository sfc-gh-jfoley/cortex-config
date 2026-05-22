---
name: multitenant-sv-guidance
description: How row access policies on base tables propagate through semantic views to Cortex Agents
---

# Multi-Tenant Semantic View Guidance

## Key Insight: RAPs Propagate Automatically

Cortex Analyst generates SQL against a semantic view's **source tables**, not against the SV
object itself. This means:

1. **RAPs on base tables scope all agent-generated queries.** If `ORDERS` has a RAP filtering
   on `tenant_id`, every SQL query Cortex Analyst generates that touches `ORDERS` will be
   automatically filtered — the RAP evaluates at query execution time, not at SV definition time.

2. **No special SV syntax is needed.** The semantic view DDL does not reference the RAP. The
   RAP is attached to the underlying table, and Snowflake's query engine enforces it transparently.

3. **The calling user/role/session determines the filter.** The RAP's policy function reads
   `CURRENT_USER()`, `CURRENT_ROLE()`, or session attributes at query time — this is the
   identity of the user (or service account) calling `DATA_AGENT_RUN`.

## Architecture Diagram

```
User / API Gateway
    │
    ├── Sets identity (user, role, or session attribute)
    │
    ▼
DATA_AGENT_RUN(agent, payload)
    │
    ├── Cortex Agent reads semantic view definition
    ├── Cortex Analyst generates SQL using SV logical model
    │
    ▼
Generated SQL executes against base tables
    │
    ├── RAP on ORDERS evaluates: tenant_id = <resolved identity>
    ├── RAP on CUSTOMERS evaluates: tenant_id = <resolved identity>
    │
    ▼
Results returned (tenant-scoped)
```

## Which RAP Pattern to Use

| Pattern | Identity Source | RAP Predicate | When to Use |
|---------|----------------|---------------|-------------|
| A: User-per-tenant | `CURRENT_USER()` | `tenant_id = CURRENT_USER()` | Internal teams, named service accounts |
| B: Role-per-tenant | `CURRENT_ROLE()` | `tenant_id = CURRENT_ROLE()` | RBAC-heavy orgs, role hierarchy |
| C: Session attribute | `SYS_CONTEXT('SNOWFLAKE$SESSION_ATTRIBUTES', 'tenant_id')` | `tenant_id = SYS_CONTEXT('SNOWFLAKE$SESSION_ATTRIBUTES', 'tenant_id')` | API gateways, connection pools, SaaS apps |

For full implementation details of each pattern, see **cortex-agent-ddl Phase 4b**.

## SV Design Considerations for MTT

### Tenant columns MUST be DIMENSIONS

In Phase 3, tenant boundary columns (e.g., `TENANT_ID`, `ORG_ID`, `ACCOUNT_ID`) are locked as
DIMENSION. This is required so that:

- Cortex Analyst can generate `WHERE tenant_id = ...` clauses
- Users can ask "show me data for tenant X" (even though the RAP already filters)
- The SV's logical model accurately represents the data's access boundaries

### Do NOT make tenant columns FACTS or SKIP

- **FACT** would allow `SUM(tenant_id)` — meaningless and a security smell
- **SKIP** would hide the column — Cortex Analyst cannot generate tenant filters, and users
  cannot understand why they see a subset of data

### Tag tenant columns for discoverability

In Phase 7 Step 7.5, tag tenant dimensions with `tenant_boundary = 'true'`. This enables:

```sql
-- Find all tenant boundary columns across all SVs:
SELECT *
FROM TABLE(INFORMATION_SCHEMA.TAG_REFERENCES_ALL_COLUMNS(
    'my_db.my_schema', 'SEMANTIC VIEW'))
WHERE TAG_NAME = 'TENANT_BOUNDARY';
```

## Security Warnings

1. **Pattern C requires trusted middleware.** If arbitrary SQL callers can `SET tenant_id = ...`,
   any user can impersonate any tenant. Only use Pattern C when the session attribute is set by
   Snowflake's authentication flow or a controlled API gateway.

2. **Test with cross-tenant queries.** After setting up RAPs, verify isolation by calling
   `DATA_AGENT_RUN` as Tenant A and asking for Tenant B's data. The result should be empty.

3. **RAPs on ALL source tables.** If the SV joins `ORDERS` and `CUSTOMERS`, both tables need
   RAPs. A RAP on only `ORDERS` means customer data leaks through the unprotected `CUSTOMERS`
   table when Cortex Analyst generates a customer-only query.
