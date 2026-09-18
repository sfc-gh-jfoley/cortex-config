---
name: ai-access-grants
description: >
  Generate Snowflake GRANT/REVOKE SQL for Cortex AI product access control. Use when:
  a user describes what AI products a role should or should not have access to, and
  wants the exact SQL to implement it. Triggers: grant cortex access, restrict AI access,
  cortex roles, who can use CoCo, who can use Analyst, AI privileges, cortex RBAC.
---

# AI Access Grants

Translates plain-language access requirements into exact Snowflake GRANT/REVOKE SQL
for Cortex AI products, covering all database roles and supporting privileges.

## Reference: Cortex AI Database Roles

| Database Role | Covers | Blocks |
|---|---|---|
| `SNOWFLAKE.CORTEX_USER` | Everything: AI functions, Analyst, Search, Agents, CoCo, CoWork, Fine-tuning | Nothing — full Cortex access |
| `SNOWFLAKE.CORTEX_AGENT_USER` | Cortex Agents + all CoCo surfaces (CLI, Desktop, Snowsight) + Snowflake Intelligence | AI Functions, Analyst, Search, Fine-tuning, Copilot |
| `SNOWFLAKE.CORTEX_ANALYST_USER` | Cortex Analyst API only | AI Functions, Agents, Search, Fine-tuning, CoCo, CoWork |
| `SNOWFLAKE.AI_FUNCTIONS_USER` | Scalar AI functions: AI_COMPLETE, AI_CLASSIFY, AI_EXTRACT, AI_SENTIMENT, AI_TRANSLATE, AI_FILTER, AI_REDACT, AI_PARSE_DOCUMENT, AI_TRANSCRIBE, AI_AGG, AI_SUMMARIZE_AGG, AI_EMBED, AI_SIMILARITY, AI_COUNT_TOKENS | Analyst, Agents, Search, Fine-tuning, CoCo, CoWork |
| `SNOWFLAKE.CORTEX_EMBED_USER` | AI_EMBED, EMBED_TEXT_768/1024. Also sufficient to *create* a Cortex Search service. Querying a search service still requires `CORTEX_USER` or USAGE on that service. | All other AI Functions, Analyst, Agents, Fine-tuning, CoCo, CoWork |
| `SNOWFLAKE.COPILOT_USER` | Snowflake Copilot only — separate from `CORTEX_USER`. A role can have Copilot without Cortex or vice versa. | Everything except Copilot |

All are granted via: `GRANT DATABASE ROLE SNOWFLAKE.<ROLE> TO ROLE <target_role>;`

**Use the narrowest role that fits the use case.** `CORTEX_USER` supersedes all narrower roles — if a role already has it, revoke it before narrow roles take effect.

## Reference: Additional Control Layers

Beyond database roles, two more layers apply:

**Model RBAC** — controls which LLM models a role can invoke. Separate from feature access. Even with `CORTEX_USER`, a role can be restricted to specific models:
```sql
-- Grant a specific model to a role
USE ROLE ACCOUNTADMIN;
GRANT APPLICATION ROLE SNOWFLAKE."CORTEX-MODEL-ROLE-CLAUDE-SONNET-4-6" TO ROLE <role>;

-- Grant all current and future models
GRANT APPLICATION ROLE SNOWFLAKE."CORTEX-MODEL-ROLE-ALL" TO ROLE <role>;
```
List available model roles: `SHOW APPLICATION ROLES LIKE 'CORTEX-MODEL%' IN APPLICATION SNOWFLAKE;`

Note: `CORTEX_MODELS_ALLOWLIST` account parameter is deprecated as of August 2026. Use model RBAC application roles exclusively.

**Per-service USAGE grants** — Cortex Search and Cortex Agents require USAGE on the specific service/agent objects, even with `CORTEX_USER`:
```sql
-- Grant access to one specific search service
GRANT USAGE ON CORTEX SEARCH SERVICE <db>.<schema>.<service> TO ROLE <role>;
GRANT USAGE ON DATABASE <db> TO ROLE <role>;
GRANT USAGE ON SCHEMA <db>.<schema> TO ROLE <role>;

-- Grant access to a specific agent
GRANT USAGE ON AGENT <db>.<schema>.<agent> TO ROLE <role>;
```

**`ENABLE_CORTEX_ANALYST` account parameter** — account-wide disable switch for Cortex Analyst. When `FALSE`, disables Analyst for all roles including ACCOUNTADMIN (though ACCOUNTADMIN can always re-enable it). Cortex Analyst is opt-in and disabled by default at the role level — no parameter change is needed to enable it, just grant `CORTEX_USER` or `CORTEX_ANALYST_USER`. The parameter's main use is as a governance kill switch during review periods:
```sql
ALTER ACCOUNT SET ENABLE_CORTEX_ANALYST = FALSE; -- disable account-wide
-- ACCOUNTADMIN can reverse this at any time with = TRUE
```

**Two keys for AI Functions** — calling AI functions requires BOTH a database role (`CORTEX_USER` or `AI_FUNCTIONS_USER`) AND the `USE AI FUNCTIONS ON ACCOUNT` account-level privilege. Revoking either one blocks access. Exception: `AI_AGG` and `AI_SUMMARIZE_AGG` work with only the account privilege, no database role required.

## Reference: Minimum Role Required per Operation

Not every operation needs ACCOUNTADMIN. Use the least-privileged role that works:

| Operation | Minimum role required |
|---|---|
| `GRANT/REVOKE DATABASE ROLE SNOWFLAKE.*` to a role | ACCOUNTADMIN in practice (Snowflake owns those roles; no other role has OWNERSHIP on them) |
| `GRANT/REVOKE USE AI FUNCTIONS ON ACCOUNT` | ACCOUNTADMIN (account-level privilege) |
| `GRANT/REVOKE USE AI FUNCTION <name> ON ACCOUNT` | ACCOUNTADMIN (account-level privilege) |
| `GRANT/REVOKE CREATE SEMANTIC VIEW ON SCHEMA` | Role with MANAGE GRANTS, or ownership of the schema |
| `ALTER USER ... SET CORTEX_CODE_*_DAILY_EST_CREDIT_LIMIT_PER_USER` | ACCOUNTADMIN |
| `ALTER ACCOUNT SET CORTEX_CODE_*_DAILY_EST_CREDIT_LIMIT_PER_USER` | ACCOUNTADMIN |
| `GRANT ROLE <role> TO USER <user>` | Role with OWNERSHIP on the role being granted, or SECURITYADMIN/USERADMIN if they own it |

**Rule:** Use the role that owns the object being granted — for SNOWFLAKE db roles that's ACCOUNTADMIN in practice, for schema privileges it's the schema owner. SECURITYADMIN/USERADMIN owns most user-created roles by default but only if those roles were created under it.

## Reference: Supporting Privileges

| Capability | Privilege |
|---|---|
| Create/alter semantic views | `CREATE SEMANTIC VIEW ON SCHEMA <db.schema>` |
| Call specific AI functions only | `GRANT USE AI FUNCTION <name> ON ACCOUNT` (after revoking `USE AI FUNCTIONS`) |
| Block a specific CoCo surface without touching other AI | `ALTER USER <u> SET CORTEX_CODE_{CLI\|DESKTOP\|SNOWSIGHT}_DAILY_EST_CREDIT_LIMIT_PER_USER = 0` |
| Block all CoCo surfaces account-wide | `ALTER ACCOUNT SET CORTEX_CODE_{CLI\|DESKTOP\|SNOWSIGHT}_DAILY_EST_CREDIT_LIMIT_PER_USER = 0` |
| All AI functions (blanket) | `GRANT USE AI FUNCTIONS ON ACCOUNT TO ROLE <role>` |

## Workflow

### Step 1: Understand the Request

Ask (if not already clear):
1. **Which role(s)** are being configured?
2. **What AI products** should they have access to? (CoCo, Analyst, AI functions, Agents, Copilot)
3. **What should be blocked?** Any explicit exclusions?
4. **Are there existing grants to clean up?** (Did they previously have `CORTEX_USER`?)
5. **Schema-level controls needed?** (e.g., prevent creating semantic views in specific schemas)

If the request is clear enough, infer answers and confirm in the output rather than asking.

### Step 2: Map Requirements to Roles

Apply this logic:

- **CoCo only** → `CORTEX_AGENT_USER` (not `CORTEX_USER`)
- **Analyst only** → `CORTEX_ANALYST_USER` (not `CORTEX_USER`). No account parameter change needed to enable Analyst — it is opt-in and blocked at role level by default.
- **AI functions only** → `AI_FUNCTIONS_USER` + `USE AI FUNCTIONS ON ACCOUNT`
- **Embeddings only** → `CORTEX_EMBED_USER` + `USE AI FUNCTIONS ON ACCOUNT`
- **Agents/Cortex API only** → `CORTEX_AGENT_USER`
- **Everything** → `CORTEX_USER` (simplest; covers all)
- **Combination** → grant each narrow role; do NOT use `CORTEX_USER` unless full access is intended
- **Restrict CoCo, keep other AI** → set `CORTEX_CODE_{CLI|DESKTOP|SNOWSIGHT}_DAILY_EST_CREDIT_LIMIT_PER_USER = 0` per user; revoking `CORTEX_USER` would also remove AI function access
- **Disable Analyst account-wide** → `ALTER ACCOUNT SET ENABLE_CORTEX_ANALYST = FALSE` (ACCOUNTADMIN can re-enable at any time)
- **Fine-tuning** → `CREATE MODEL ON SCHEMA` for the creating role + `CORTEX_USER` for both the creating role and any role that runs inference on the fine-tuned model

Key rule: if a role already has `CORTEX_USER`, you must revoke it before narrow roles have effect — `CORTEX_USER` supersedes them all.

### Step 3: Generate SQL

Split the output into sections by the minimum role required. Do not use ACCOUNTADMIN for operations that don't need it.

Structure:
1. **ACCOUNTADMIN block** — only for: SNOWFLAKE database role grants/revokes, account-level USE AI FUNCTIONS privileges
2. **USERADMIN block** — only if assigning roles to users or setting per-user parameters
3. **Schema owner block** — schema-level CREATE SEMANTIC VIEW grants/revokes (use the role that owns the schema, or a role with MANAGE GRANTS)

REVOKEs always come before GRANTs within each block. Include a brief comment per section.

Format:
```sql
-- Requires ACCOUNTADMIN: SNOWFLAKE db roles and account-level AI privileges
USE ROLE ACCOUNTADMIN;

-- Remove broad access (required before narrow roles take effect)
REVOKE DATABASE ROLE SNOWFLAKE.CORTEX_USER FROM ROLE <role>;

-- Grant scoped access
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_AGENT_USER TO ROLE <role>;

-- Requires schema owner or a role with MANAGE GRANTS
USE ROLE <schema_owner_role>;

-- Prevent creating semantic views in production schema
REVOKE CREATE SEMANTIC VIEW ON SCHEMA prod_db.public FROM ROLE <role>;

-- Requires USERADMIN (only if assigning role to a user)
USE ROLE USERADMIN;
GRANT ROLE <role> TO USER <user>;
```

Omit any block that isn't needed for the specific request.

### Step 4: Surface Gotchas

Always check and call out if any apply:

- **Inheritance trap**: if a parent role has `CORTEX_USER`, child role revoke has no effect. Note this and suggest checking with `SHOW GRANTS TO ROLE <parent_role>`.
- **IMPORTED PRIVILEGES**: broad `GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE` can bypass role revokes. Note if this may be a concern.
- **CoCo surface differentiation is always per-user, never per-role.** `CORTEX_AGENT_USER` grants access to all CoCo surfaces (CLI, Desktop, Snowsight) at once — there is no role that enables only one surface. To block a specific surface, use `CORTEX_CODE_{CLI|DESKTOP|SNOWSIGHT}_DAILY_EST_CREDIT_LIMIT_PER_USER = 0` on each individual user. New users added to the role later must be set manually.
- **PUBLIC role default**: `CORTEX_USER` is granted to PUBLIC by default. If locking down an account, note that PUBLIC must be addressed first.

## Output Format

```
## Access Configuration: <role_name>

**Grants:** [comma-separated AI products being enabled]
**Blocked:** [comma-separated AI products being restricted]

```sql
-- Requires ACCOUNTADMIN
USE ROLE ACCOUNTADMIN;
...

-- Requires <schema_owner_role> or MANAGE GRANTS (if schema-level changes needed)
USE ROLE <schema_owner_role>;
...
```

**Gotchas to verify:**
- [inheritance or PUBLIC role concerns]
```
