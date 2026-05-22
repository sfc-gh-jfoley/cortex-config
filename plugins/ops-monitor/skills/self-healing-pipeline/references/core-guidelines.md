---
name: self-healing-pipeline-core-guidelines
description: Core context and guidelines for self-healing pipeline operations. Always load this reference at the start of any session.
---

# Core Guidelines

Foundational context for all self-healing pipeline operations. The main skill handles routing; this reference provides the knowledge needed to execute any workflow correctly.

## Mandatory Behavior Pattern

These rules apply to ALL operations. Violating them indicates context drift — reload skills immediately.

1. **Never guess.** If unsure of a Snowflake API, function signature, or required value — stop.
2. **Skills first.** Check the routing table in `SKILL.md` to find the correct reference for the operation.
3. **Docs second.** If skills do not cover it, use `snowflake_product_docs` to discover the correct API.
4. **Ask third.** If still unsure, ask the user: "I need to do X — is this the correct approach?"
5. **No fabrication.** Do not invent SQL, procedures, or API calls. Use documented templates only.
6. **No secrets in output.** Never echo passwords, tokens, or sensitive values back to the user.
7. **Verify results.** After operations, check the result matches expectations before proceeding.
8. **Conservative by default.** When in doubt, hold for human review rather than auto-executing.

**Context drift indicators** (if you notice these, reload `SKILL.md`):
- Writing raw SQL for operations that should use stored procedure templates
- Trying multiple SQL variations to see what works
- Proceeding without knowing what a command will do
- Skipping guardrail checks

---

## Architecture

```
                    ┌─────────────────┐
                    │  Snowflake ALERTs │
                    │  (self-monitor,   │
                    │   lag drift, cost) │
                    └────────┬─────────┘
                             │ fires independently
                             ▼
┌──────────────────────────────────────────────────────────┐
│                SP_DETECT_FAILURES (every 5 min)          │
│  scans TASK_HISTORY + DYNAMIC_TABLE_REFRESH_HISTORY      │
│  classifies as TASK or DYNAMIC_TABLE                     │
│  runs SP_CHECK_CIRCUIT_BREAKER first                     │
└──────────┬───────────────────────────┬───────────────────┘
           │ TASK                      │ DYNAMIC_TABLE
           ▼                           ▼
   SP_DIAGNOSE_FAILURE         SP_DIAGNOSE_DT_FAILURE
   (runbook → LLM)            (graph walk → runbook → LLM)
           │                           │
           └───────────┬───────────────┘
                       ▼
              SP_CHECK_GUARDRAILS
              ┌────────┼────────┐
              │        │        │
           PASS     REVIEW    BLOCK
              │        │        │
              ▼        ▼        ▼
        SP_EXECUTE  SP_CREATE   ESCALATE
        _FIX        _REVIEW     + ALERT
              │        │
              ▼        ▼
        SP_CHECK_   PENDING_REVIEWS
        DATA_       ┌──────────┐
        QUALITY     │Streamlit │
              │     │Dashboard │
              ▼     └─┬──┬──┬──┘
        SP_VERIFY_     │  │  │
        TASK_DAG/    Approve│Reject│Manual Fix
        DT_FIX        │  │  │
              │        ▼  ▼  ▼
              ▼     SP_APPROVE/ SP_REJECT/ SP_MARK_RESOLVED
           RESOLVED    │                      │
              │        └──────────┬───────────┘
              ▼                   ▼
         ALERT(success)    SP_LEARN_FROM_MANUAL_FIXES
                           (auto-populate runbook)
```

## Component Inventory

| Layer | Components |
|-------|-----------|
| Detection | SP_DETECT_FAILURES, SP_CHECK_CIRCUIT_BREAKER |
| Diagnosis | SP_DIAGNOSE_FAILURE (tasks), SP_DIAGNOSE_DT_FAILURE (DTs) |
| Guardrails | SP_CHECK_GUARDRAILS (conservative: deny ALTER/DROP until pattern known) |
| Execution | SP_EXECUTE_FIX, SP_CHECK_DATA_QUALITY |
| Verification | SP_VERIFY_TASK_DAG, SP_VERIFY_DT_FIX (full downstream DAG walk) |
| HITL | PENDING_REVIEWS table, SP_CREATE_REVIEW, SP_APPROVE_FIX, SP_REJECT_FIX, SP_MARK_RESOLVED |
| Learning | SP_LEARN_FROM_MANUAL_FIXES, SP_AUTO_ESCALATE_EXPIRED |
| Alerting | SP_SEND_ALERT (email/webhook), ALERT objects (self-monitor, lag drift, cost, escalations) |
| UI | Streamlit Dashboard (SiS): Dashboard, Pending Reviews, Audit Log |
| Storage | PIPELINE_FAILURES, ERROR_RUNBOOK, HEALING_AUDIT_LOG, PENDING_REVIEWS |

---

## Default Guardrail Philosophy

**Conservative by default**: only safe, reversible operations are auto-executed. Everything else requires human review.

| Operation | Default | Rationale |
|-----------|---------|-----------|
| SELECT (diagnostic) | AUTO | Read-only, no risk |
| ALTER TASK ... SET WAREHOUSE | AUTO | Config change, reversible |
| ALTER TASK RESUME | AUTO | State change, reversible |
| ALTER DYNAMIC TABLE ... SET TARGET_LAG | REVIEW | Performance change, needs human judgment |
| ALTER DYNAMIC TABLE REFRESH | AUTO | Trigger refresh, no schema change |
| ALTER TABLE ADD COLUMN | REVIEW | Schema change |
| ALTER TASK MODIFY AS | REVIEW | Changes task logic |
| CREATE OR REPLACE DYNAMIC TABLE | REVIEW | Replaces existing DT definition |
| Any DROP, TRUNCATE, DELETE | BLOCK | Destructive, never auto-execute |
| Any GRANT, REVOKE | BLOCK | Security change, never auto-execute |

The user configures these during setup. As patterns are proven safe, they can promote operations from REVIEW → AUTO by adding runbook entries with confidence >= 0.8.

### Guardrail Tiers

- **TIER 1 — BLOCK**: Destructive/security ops. Always blocked, no override. (DROP, TRUNCATE, DELETE, GRANT, REVOKE, CREATE/ALTER USER/ROLE)
- **TIER 2 — REVIEW**: ALTER operations without a runbook match. Requires human approval via HITL.
- **TIER 3 — PASS**: Safe operations (SELECT, RESUME, REFRESH, EXECUTE TASK) with sufficient confidence.
- **TIER 4 — REVIEW**: Everything else defaults to human review.

**Promoting REVIEW → AUTO**: Add a runbook entry for the error pattern with `CONFIDENCE >= 0.8`. The guardrail checks the runbook before deciding.

---

## Model Selection Logic

**Runbook-first, LLM-fallback.** Deterministic matches before burning LLM credits.

| Scenario | Model | Rationale |
|----------|-------|-----------|
| Known error in runbook | No LLM needed | Deterministic match → direct fix |
| Simple object-not-found, typo | `llama3.1-8b` | Fast, cheap, sufficient for simple renames |
| Schema mismatch, type errors | `llama3.1-70b` | Needs schema reasoning |
| Complex multi-object failures | `llama3.1-405b` or `mistral-large2` | Deep reasoning required |
| DT UPSTREAM_FAILED (cascade) | `llama3.1-70b` | Needs graph traversal + root cause reasoning |

---

## Circuit Breaker

The agent self-suspends when it detects it is not being effective. This prevents fix loops and runaway LLM costs.

**Triggers:**
- Escalations in past hour exceed threshold (default: 10)
- Objects with >= 3 fix attempts in past 2 hours exceed count (default: 3)

**Actions on trip:**
1. Suspend the SELF_HEALING_AGENT task
2. Send alert with escalation counts
3. Log CIRCUIT_BREAKER event to HEALING_AUDIT_LOG
4. Require manual `ALTER TASK ... RESUME` to restart

See `references/monitoring-templates.md` for SP_CHECK_CIRCUIT_BREAKER implementation.

---

## Snowflake APIs Used

| API | Purpose |
|-----|---------|
| `INFORMATION_SCHEMA.TASK_HISTORY()` | Task failure detection |
| `INFORMATION_SCHEMA.TASK_DEPENDENTS(RECURSIVE => TRUE)` | Task DAG traversal |
| `INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(ERROR_ONLY => TRUE)` | DT failure detection |
| `INFORMATION_SCHEMA.DYNAMIC_TABLE_GRAPH_HISTORY()` | DT DAG traversal (INPUTS array) |
| `INFORMATION_SCHEMA.DYNAMIC_TABLES()` | DT lag drift monitoring |
| `GET_DDL('TASK', ...)` / `GET_DDL('DYNAMIC_TABLE', ...)` | Definition retrieval |
| `EXECUTE TASK ... RETRY LAST` | Retry failed task graph from failure point |
| `ALTER DYNAMIC TABLE ... REFRESH` | Trigger manual DT refresh |
| `SYSTEM$TASK_DEPENDENTS_ENABLE()` | Resume task graphs |
| `SNOWFLAKE.CORTEX.COMPLETE()` | LLM inference |
| `SYSTEM$SEND_EMAIL()` | Email alerting |
| `SYSTEM$SEND_SNOWFLAKE_NOTIFICATION()` | Webhook alerting |
| `CREATE ALERT` | Snowflake ALERT objects |
| `SNOWFLAKE.ALERT.LAST_SUCCESSFUL_SCHEDULED_TIME()` | ALERT condition windowing |

---

## Prerequisites

- Snowflake account with CORTEX_USER database role (for LLM access)
- A database/schema with existing tasks or dynamic tables to monitor
- Permissions: CREATE PROCEDURE, CREATE TABLE, CREATE TASK, CREATE ALERT on target schema
- MONITOR privilege on dynamic tables (for DT refresh history)
- EXECUTE ALERT and EXECUTE MANAGED ALERT privileges on account
- For email: notification integration permissions (ACCOUNTADMIN to create)
- For Streamlit: CREATE STREAMLIT privilege
