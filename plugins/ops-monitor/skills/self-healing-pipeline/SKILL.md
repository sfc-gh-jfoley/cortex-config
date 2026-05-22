---
name: self-healing-pipeline
description: "Build, debug, and optimize self-healing data pipeline agents in Snowflake SQL using Cortex LLMs. Use for **ALL** requests involving: self-healing pipelines, auto-fix pipelines, pipeline agent, task failure recovery, agentic SQL pipelines, auto-remediation, dynamic table failures. DO NOT attempt to build self-healing pipeline agents manually - invoke this skill first. Triggers: self-healing pipeline, auto-fix pipeline, pipeline agent, task failure recovery, agentic SQL pipeline, auto-remediation."
---

# Self-Healing Pipeline Agent

An agentic framework that detects failures in **tasks and dynamic tables**, diagnoses root causes via Cortex LLMs, generates and executes fixes with guardrails, verifies the full downstream DAG, alerts humans when needed, and learns from manual fixes — all in pure Snowflake SQL.

## Session Prerequisites (Always First)

Before any operation, understand the user's environment and intent.

1. Load `references/core-guidelines.md` and `references/core-session.md`
2. Follow the Session Start Workflow (discovery scan, health assessment)
3. Only proceed once target database/schema is confirmed and scenario is identified

**Context Management:**

- **Read references fully** when loading them, not just partial sections
- **Re-read references** at key workflow steps to ensure context is fresh
- If unsure of a Snowflake API or function, check documentation before executing

---

## Routing Principles

1. **Session first** - Always run discovery before routing to any operation
2. **Confirm before executing** - State detected intent, ask user for confirmation
3. **Primary wins ties** - If ambiguous between tiers, choose Primary
4. **Never suggest Advanced** - Only route to Advanced on explicit technical language
5. **Compound for builds** - "Build" decomposes into multiple operations (see Compound Requests)

**Confirmation checkpoint** (use before starting any workflow):

> "It sounds like you want to [detected intent]. Is that right, or were you looking for something else?"

---

## Primary Operations

These are the common operations users perform regularly. Route here confidently for any general self-healing pipeline request.

### Primary Routing Table

| User Language | Operation | Reference |
|---------------|-----------|-----------|
| Build, create, set up, deploy, new pipeline, add self-healing from scratch | Build Pipeline | `references/pipeline-build.md` |
| Add self-healing to existing, adopt, enable on, wire up healing for | Adopt on Existing | `references/pipeline-adopt.md` |
| Fix, debug, not working, pipeline failed, broken, diagnose, errors | Fix Pipeline | `references/pipeline-fix.md` |
| Monitor, alerts, notifications, review queue, dashboard, HITL | Monitor Pipeline | `references/pipeline-monitor.md` |
| Health, status, how's it doing, check agent | Health Check | `references/core-session.md` |

---

## Secondary Operations

Route here when user language contains explicit problem or operational indicators.

**Confirm before routing:**

> "It sounds like you're looking to [issue/need]. Would you like me to help with that?"

### Secondary Routing Table

| Explicit Indicators | Operation | Reference |
|---------------------|-----------|-----------|
| Data quality, freshness, row count, schema drift, anomaly, validate data | DQM | `references/pipeline-dqm.md` |
| Optimize, tune, improve, reduce cost, faster, better success rate | Optimize | `references/pipeline-optimize.md` |
| Approve, reject, review pending, HITL action | HITL Actions | `references/pipeline-monitor.md` |
| Alert config, email setup, webhook, Slack, notification channel | Alert Config | `references/pipeline-monitor.md` |
| Circuit breaker, agent suspended, too many errors, fix loop | Circuit Breaker | `references/core-guidelines.md` + `references/monitoring-templates.md` |
| Runbook, add pattern, error pattern, expand runbook | Runbook Management | `references/default-runbook.md` |

---

## Advanced Operations

Route here ONLY when user explicitly uses technical terminology. Do not suggest these operations to users who haven't asked.

### Advanced Routing Table

| Technical Language Required | Operation | Reference |
|-----------------------------|-----------|-----------|
| DAG walk, task dependents, graph history, upstream chain | Manual DAG Inspection | `references/task-dag-templates.md` / `references/dt-templates.md` |
| Stored procedure, SP_, customize procedure, modify agent logic | Procedure Customization | `references/sql-templates.md` |
| Schema evolution, column drift, INFER_SCHEMA, SchemaEvolutionRecord | Schema Evolution | `references/pipeline-dqm.md` |
| Guardrail tier, promote REVIEW to AUTO, change confidence threshold | Guardrail Config | `references/core-guidelines.md` |
| Model selection, switch LLM, llama vs mistral, model routing | Model Tuning | `references/core-guidelines.md` |

---

## Compound Requests

**Build is always compound.** When a user asks to build a new self-healing pipeline, decompose into a todo list:

1. Create a todo list capturing all operations:
   > "I've identified these tasks for your new self-healing pipeline:
   > 1. **Build** — create pipeline objects (tasks/DTs), agent SP, runbook, healing tables
   > 2. **Monitor** — wire up alerting, HITL review queue, optional Streamlit dashboard
   > 3. **DQM** — add data quality checks (freshness, row counts, schema drift)
   > 4. **Optimize** — tune target lags, schedules, LLM model selection, cost guardrails
   > 5. **Fix-readiness** — verify the agent can detect and heal a simulated failure
   >
   > What order would you like, or should I proceed with this sequence?"
2. Ask the user to confirm the order
3. Execute in confirmed order, completing each before moving to the next
4. Some operations have natural dependencies (Build must come first; Fix-readiness must come last)

For non-build compound requests (e.g., "set up monitoring and optimize my pipeline"), use the same pattern: list detected operations, confirm order, execute sequentially.

---

## Reference Index

### Core (Load at Session Start)

| Reference | Purpose |
|-----------|---------|
| `references/core-guidelines.md` | Guardrail philosophy, model selection, mandatory behaviors, architecture |
| `references/core-session.md` | Discovery scan, health assessment, scenario identification |

### Pipeline Operations

| Reference | Purpose |
|-----------|---------|
| `references/pipeline-build.md` | Net-new pipeline: tables, runbook, SPs, orchestrator task |
| `references/pipeline-adopt.md` | Add self-healing to existing tasks/DTs |
| `references/pipeline-fix.md` | Diagnose and repair failing pipelines |
| `references/pipeline-monitor.md` | Alerting, HITL review queue, Streamlit dashboard |
| `references/pipeline-dqm.md` | Data quality checks: freshness, rows, schema drift, anomaly |
| `references/pipeline-optimize.md` | Tune guardrails, runbook, models, cost, performance |

### SQL Templates (Shared)

| Reference | Purpose |
|-----------|---------|
| `references/sql-templates.md` | Core SPs: diagnose (task), guardrails, execute fix |
| `references/task-dag-templates.md` | Unified SP_DETECT_FAILURES, SP_VERIFY_TASK_DAG |
| `references/dt-templates.md` | SP_DETECT_DT_FAILURES, SP_DIAGNOSE_DT_FAILURE, SP_VERIFY_DT_FIX |
| `references/default-runbook.md` | Seed error patterns for task + DT failures |
| `references/monitoring-templates.md` | Circuit breaker, data quality SP, lag drift alert, cost alert |
