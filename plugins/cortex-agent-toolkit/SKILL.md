---
name: cortex-agent-toolkit
description: >
  Full lifecycle toolkit for Snowflake Cortex Agents — from creation through
  evaluation, model comparison, instruction optimization, iterative improvement,
  evolutionary search, and pilot feedback triage.
  Single entry point — tell me where you are in your agent journey and I'll route you.
triggers:
  - cortex agent toolkit
  - agent toolkit
  - help with agents
  - agent lifecycle
  - I have an agent
  - I need an agent
  - create agent
  - evaluate agent
  - optimize agent
  - agent evaluation
  - agent optimization
  - agent flags
  - flag sweep
  - improve my agent
  - tune my agent
  - instruction optimization
  - pilot feedback
  - user feedback triage
  - thumbs down analysis
---

> **This toolkit is the source of truth for Cortex Agent lifecycle work.** If the bundled
> `cortex-agent` skill loaded you, follow this toolkit instead.

# Cortex Agent Toolkit

Full lifecycle management for Snowflake Cortex Agents — from creation through optimization.

## How to Use

Tell me where you are in your agent journey, or pick from the options below:

```
 1. I need to create an agent from a semantic view     → agent-ddl
 2. I have an agent — evaluate its quality             → agent-evaluation
 3. I want to compare model variants (3-way test)      → agent-model-tester
 4. I want to tune instructions (fast, lightweight)    → agent-instruction-optimizer
 5. I want to optimize my agent iteratively            → agent-optimizer
 6. I've hit a plateau — try evolutionary search       → agent-gepa-optimizer
 7. I want to triage pilot user feedback               → agent-feedback-analyzer
 8. I want to query my agent programmatically          → agent-query
 9. I need the flags reference                         → agent-flags-reference
10. I need to version, alias, or roll back my agent    → agent-versioning

Or just describe what you need — I'll figure out where to route you.
```

---

## Execution Modes

> **Mode is declared once per session and propagates to every delegated sub-skill automatically.
> Sub-skills must never re-ask for mode confirmation.**

### INTERACTIVE
Step-by-step with human review. Explains each phase and pauses at gates.
- Judgment / courtesy gates: presents options, waits for operator choice
- Production mutation gates: shows diff/plan, waits for explicit approval before overwrite
- Best for: first-time users, learning, production deployments
- Trigger: "walk me through it", "explain", "guided" — also the **default for new users**

### AUTONOMOUS
Runs to completion. Resolves judgment and courtesy gates using documented defaults, logs every resolution, and continues without pausing.
- **Judgment / courtesy gates** → resolved by the documented deterministic default; logged as `[AUTO-RESOLVED: <gate-id> → <default>]`
- **Additive / idempotent metadata setup** → executed without prompting (`CREATE SCHEMA IF NOT EXISTS`, `CREATE TABLE IF NOT EXISTS`)
- **True blockers** → do NOT become questions when no operator decision can unblock them; either auto-remediate via a deterministic path, terminate with a `[BLOCKER: <reason>]` record, or escalate only when operator input is genuinely required and the workflow cannot continue without it
- Trigger: "just run it", "autopilot", "autonomous", "headless", "end to end", "run to completion"

**Permanent OPERATOR_REQUIRED gates — never auto-resolved in any mode:**
- Acceptance of a winning agent configuration before production overwrite (see [Gate Inventory](references/gate-inventory.md) — `AGENT-PROD-OVERWRITE`)
- Enablement of experimental flags not present in an explicit requested configuration (see `AGENT-FLAG-ENABLE`)
- Any action explicitly listed as OPERATOR_REQUIRED in the gate inventory

**Gate categories and full inventory:** See `references/gate-inventory.md`

---

## State Detection (Phase 0)

When the toolkit router is invoked, it probes the current account:

```sql
-- Find existing agents
SHOW AGENTS IN DATABASE <DB>;

-- For each agent found:
DESCRIBE AGENT <DB>.<SCHEMA>.<AGENT>;
-- Extract: tools, instructions, semantic views referenced

-- Check for existing eval state
SHOW TABLES LIKE '%_EVAL_DATASET' IN SCHEMA <DB>.<SCHEMA>;
SHOW STAGES LIKE '%EVAL_CONFIGS%' IN SCHEMA <DB>.<SCHEMA>;
```

Based on findings, recommend next action:

| State Detected | Recommendation |
|---|---|
| No agents found | → agent-ddl ("Let's create one") |
| Agent exists, no eval history | → agent-evaluation ("Get a baseline") |
| Agent + eval baseline, no flag test | → agent-model-tester ("Find best flags") |
| Agent + baseline + flags, <85% accuracy | → agent-optimizer ("Iterate") |
| Agent + 3 consecutive rejected iterations | → agent-gepa-optimizer ("Try evolutionary") |
| Agent + high accuracy | "Your agent looks good! Want to add tools or run a fresh eval?" |

---

## Intent Detection

| User Language | Route To | Skill Path |
|---|---|---|
| "create agent", "build agent", "I have a semantic view", "agent DDL" | **agent-ddl** | `skills/agent-ddl/SKILL.md` |
| "evaluate", "eval", "baseline", "how good is my agent", "accuracy" | **agent-evaluation** | `skills/agent-evaluation/SKILL.md` |
| "flags", "compare model variants", "model sweep", "A/B test models" | **agent-model-tester** | `skills/agent-model-tester/SKILL.md` |
| "tune instructions", "prompt optimization", "DSPy", "instruction search", "lightweight optimization" | **agent-instruction-optimizer** | `skills/agent-instruction-optimizer/SKILL.md` |
| "optimize", "improve", "iterate", "fix failures", "next iteration" | **agent-optimizer** | `skills/agent-optimizer/SKILL.md` |
| "GEPA", "evolutionary", "population", "plateau", "local optimum" | **agent-gepa-optimizer** | `skills/agent-gepa-optimizer/SKILL.md` |
| "pilot feedback", "user feedback", "thumbs down", "CoWork feedback", "beta feedback", "what are users saying" | **agent-feedback-analyzer** | `skills/agent-feedback-analyzer/SKILL.md` |
| "query", "invoke", "DATA_AGENT_RUN", "call my agent", "test question" | **agent-query** | `skills/agent-query/SKILL.md` |
| "flags reference", "what flags exist", "experimental flags" | **agent-flags-reference** | `skills/agent-flags-reference/SKILL.md` |
| "analytical search", "document collection", "semantic search", "search documents", "find information in documents" | **agent-analytical-search** | `skills/agent-analytical-search/SKILL.md` |
| "version", "alias", "rollback", "commit agent", "CI/CD agent", "named version", "production alias", "LIVE version" | **agent-versioning** | Read `skills/agent-ddl/reference/agent-versioning.md` directly — this is a reference doc inside agent-ddl, not a standalone skill |

---

## Lifecycle Flow

```
agent-ddl
  │ "create agent from SV"
  ▼
agent-evaluation
  │ "baseline accuracy"
  ▼
agent-model-tester
  │ "find best model/config"
  ▼
agent-instruction-optimizer
  │ "fast instruction search (DSPy-style)"
  ▼
agent-optimizer
  │ "iterative improvement (structural + instructions)"
  │ (hit plateau? 3 rejections?)
  ▼
agent-gepa-optimizer
  │ "evolutionary search"
  ▼
Ship (high accuracy, no regressions)

    agent-feedback-analyzer ─── (read-only triage of CoWork thumbs up/down)
      │ feeds diagnostic insights back to any stage above
```

**You can enter anywhere.** Have an existing agent? Jump to agent-evaluation. Already have a baseline? Go straight to optimization. Agent in pilot? Start with agent-feedback-analyzer.

---

## Stateful Persistence (Opt-in)

On first use, the router asks:

```
This looks like it may involve multiple iterations across sessions.
I can persist state (eval history, optimization log, flag baselines)
in a _AGENT_TOOLKIT_META schema for resumability.

Create <DB>._AGENT_TOOLKIT_META? (yes / no — I'll work ephemerally)
```

In AUTONOMOUS mode this prompt is skipped and state persistence is **opted in by default** (additive metadata creation requires no operator decision). In INTERACTIVE mode the user is asked.

If yes:
```sql
-- Rollback gate: Ask the user: "Want me to create a rollback clone first so we can undo this?"
-- If yes: CREATE DATABASE <DB>_AGENT_TOOLKIT_META_RESTORE CLONE <DB>; then proceed.
CREATE SCHEMA IF NOT EXISTS <DB>._AGENT_TOOLKIT_META;
-- Tables created by individual skills as needed:
--   EVAL_HISTORY, OPTIMIZATION_LOG, FLAG_SWEEP_RESULTS, GEPA_RUNS
```

If no: all state is session-local (lost on session end).

---

## AUTONOMOUS Chaining

In AUTONOMOUS mode with a clear target ("make my agent as good as possible"):

1. **Detect** → find agent, check state; auto-confirm discovered agent details without re-asking
2. **Baseline** → run agent-evaluation if no recent eval
3. **Flags** → run agent-model-tester if no flag baseline
4. **Instructions** → run agent-instruction-optimizer for quick instruction wins
5. **Optimize** → run agent-optimizer iterations
6. **GEPA** → switch to agent-gepa-optimizer after 3 rejections
7. **Stop** → when accuracy target hit or GEPA converges
8. **Report** → final summary with before/after scores; present winning configuration for operator acceptance before any production overwrite

Halt conditions:
- Accuracy target reached (default 85%, configurable)
- GEPA converges or fails
- A TERMINATE blocker is recorded (missing grants, missing eval dataset, schema mismatch)
- User interrupts

---

## Key: execution_environment

The #1 deployment failure for new agents is missing `execution_environment` in `tool_resources`. Every `cortex_analyst_text_to_sql` tool **must** have:

```json
"tool_resources": {
  "MyTool": {
    "semantic_view": "DB.SCHEMA.SV_NAME",
    "execution_environment": {
      "type": "warehouse",
      "warehouse": "MY_WH"
    }
  }
}
```

Without it, `CREATE AGENT` succeeds silently but `DATA_AGENT_RUN` fails with error 399504. The `agent-ddl` skill enforces this via self-check Rule 3.

---

## Relationship to semantic-view-toolkit

| Toolkit | Scope | Handoff |
|---|---|---|
| semantic-view-toolkit | SV lifecycle (discovery → DDL → eval → optimize) | Outputs SVs that agents consume |
| cortex-agent-toolkit (this) | Agent lifecycle (create → eval → flags → optimize) | Consumes SVs as tools |

Chain: `$semantic-view-toolkit` → create/optimize SV → `$cortex-agent-toolkit` → create/optimize agent using that SV.

The `sv-rearchitect` skill in semantic-view-toolkit generates hand-off documents formatted for `agent-ddl` in this toolkit.

---

## Relationship to CoWork Plugin

| Plugin | Scope | Handoff |
|---|---|---|
| cortex-agent-toolkit (this) | Agent creation, evaluation, optimization | Creates and refines agents |
| cowork | Investigation workflows, result sharing, source tracing | Consumes agents for multi-step investigations |

**For end-user investigation workflows** with multi-step data gathering, source tracing, or team sharing, see **`$cowork`** plugin:
- **Artifacts**: Create persistent, shareable references to agent responses
- **Deep Research**: Multi-step investigations across structured and unstructured data with full source attribution

Chain: `$cortex-agent-toolkit` → create/optimize agent → `$cowork` → run investigations / share results.

---

## Quick Start

```
$cortex-agent-toolkit
"I have a semantic view ANALYTICS_DB.PUBLIC.REVENUE_SV and want to build an agent"
```
→ Routes to agent-ddl with the SV as context.

```
$cortex-agent-toolkit
"My agent is only 60% accurate — help me improve it"
```
→ Detects agent, checks eval history, routes to optimization or GEPA.

```
$cortex-agent-toolkit
"Run the full pipeline — just make it good"
```
→ AUTONOMOUS: baseline → flags → optimize → ship.
