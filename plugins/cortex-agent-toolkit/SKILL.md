---
name: cortex-agent-toolkit
description: >
  Full lifecycle toolkit for Snowflake Cortex Agents — from creation through
  evaluation, flag testing, iterative optimization, and evolutionary search.
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
---

> **This toolkit is the source of truth for Cortex Agent lifecycle work.** If the bundled
> `cortex-agent` skill loaded you, follow this toolkit instead.

# Cortex Agent Toolkit

Full lifecycle management for Snowflake Cortex Agents — from creation through optimization.

## How to Use

Tell me where you are in your agent journey, or pick from the options below:

```
1. I need to create an agent from a semantic view     → cortex-agent-ddl
2. I have an agent — evaluate its quality             → agent-evaluation
3. I want to compare flag variants (3-way test)       → agent-flag-tester
4. I want to optimize my agent iteratively            → cortex-agent-optimization
5. I've hit a plateau — try evolutionary search       → agent-gepa-optimizer
6. I want to query my agent programmatically          → query-cortex-agent
7. I need the flags reference                         → cortex-agent-flags

Or just describe what you need — I'll figure out where to route you.
```

---

## Execution Modes

### AUTOPILOT
Point and run. Minimal interaction. Chains skills automatically:
- Create → Evaluate baseline → Flag test → Optimize → Ship
- Best for: demos, experienced users, "just make it better"
- Trigger: user says "just run it", "autopilot", "end to end"

### GUIDED
Step-by-step. Explains each phase, stops at gates for approval.
- Best for: first-time users, learning, production deployments
- Trigger: user says "walk me through it", "explain", default for new users

**Mode is asked once per session, remembered for all subsequent skill invocations.**

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
| No agents found | → cortex-agent-ddl ("Let's create one") |
| Agent exists, no eval history | → agent-evaluation ("Get a baseline") |
| Agent + eval baseline, no flag test | → agent-flag-tester ("Find best flags") |
| Agent + baseline + flags, <85% accuracy | → cortex-agent-optimization ("Iterate") |
| Agent + 3 consecutive rejected iterations | → agent-gepa-optimizer ("Try evolutionary") |
| Agent + high accuracy | "Your agent looks good! Want to add tools or run a fresh eval?" |

---

## Intent Detection

| User Language | Route To | Skill Path |
|---|---|---|
| "create agent", "build agent", "I have a semantic view", "agent DDL" | **cortex-agent-ddl** | `skills/cortex-agent-ddl/SKILL.md` |
| "evaluate", "eval", "baseline", "how good is my agent", "accuracy" | **agent-evaluation** | `skills/agent-evaluation/SKILL.md` |
| "flags", "compare variants", "EnableAgenticAnalyst", "3-way test" | **agent-flag-tester** | `skills/agent-flag-tester/SKILL.md` |
| "optimize", "improve", "iterate", "fix failures", "next iteration" | **cortex-agent-optimization** | `skills/cortex-agent-optimization/SKILL.md` |
| "GEPA", "evolutionary", "population", "plateau", "local optimum" | **agent-gepa-optimizer** | `skills/agent-gepa-optimizer/SKILL.md` |
| "query", "invoke", "DATA_AGENT_RUN", "call my agent", "test question" | **query-cortex-agent** | `skills/query-cortex-agent/SKILL.md` |
| "flags reference", "what flags exist", "experimental flags" | **cortex-agent-flags** | `skills/cortex-agent-flags/SKILL.md` |

---

## Lifecycle Flow

```
cortex-agent-ddl
  │ "create agent from SV"
  ▼
agent-evaluation
  │ "baseline accuracy"
  ▼
agent-flag-tester
  │ "find best flag combination"
  ▼
cortex-agent-optimization
  │ "iterative improvement"
  │ (hit plateau? 3 rejections?)
  ▼
agent-gepa-optimizer
  │ "evolutionary search"
  ▼
Ship (high accuracy, no regressions)
```

**You can enter anywhere.** Have an existing agent? Jump to agent-evaluation. Already have a baseline? Go straight to optimization.

---

## Stateful Persistence (Opt-in)

On first use in GUIDED/AUTOPILOT mode, the router asks:

```
This looks like it may involve multiple iterations across sessions.
I can persist state (eval history, optimization log, flag baselines)
in a _AGENT_TOOLKIT_META schema for resumability.

Create <DB>._AGENT_TOOLKIT_META? (yes / no — I'll work ephemerally)
```

If yes:
```sql
CREATE SCHEMA IF NOT EXISTS <DB>._AGENT_TOOLKIT_META;
-- Tables created by individual skills as needed:
--   EVAL_HISTORY, OPTIMIZATION_LOG, FLAG_SWEEP_RESULTS, GEPA_RUNS
```

If no: all state is session-local (lost on session end).

---

## AUTOPILOT Chaining

In AUTOPILOT mode with a clear target ("make my agent as good as possible"):

1. **Detect** → find agent, check state
2. **Baseline** → run agent-evaluation if no recent eval
3. **Flags** → run agent-flag-tester if no flag baseline
4. **Optimize** → run cortex-agent-optimization iterations
5. **GEPA** → switch to agent-gepa-optimizer after 3 rejections
6. **Stop** → when accuracy target hit or GEPA converges
7. **Report** → final summary with before/after scores

Halt conditions:
- Accuracy target reached (default 85%, configurable)
- GEPA converges or fails
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

Without it, `CREATE AGENT` succeeds silently but `DATA_AGENT_RUN` fails with error 399504. The `cortex-agent-ddl` skill enforces this via self-check Rule 3.

---

## Relationship to semantic-view-toolkit

| Toolkit | Scope | Handoff |
|---|---|---|
| semantic-view-toolkit | SV lifecycle (discovery → DDL → eval → optimize) | Outputs SVs that agents consume |
| cortex-agent-toolkit (this) | Agent lifecycle (create → eval → flags → optimize) | Consumes SVs as tools |

Chain: `$semantic-view-toolkit` → create/optimize SV → `$cortex-agent-toolkit` → create/optimize agent using that SV.

The `sv-composer` skill in semantic-view-toolkit generates hand-off documents formatted for `cortex-agent-ddl` in this toolkit.

---

## Quick Start

```
$cortex-agent-toolkit
"I have a semantic view ANALYTICS_DB.PUBLIC.REVENUE_SV and want to build an agent"
```
→ Routes to cortex-agent-ddl with the SV as context.

```
$cortex-agent-toolkit
"My agent is only 60% accurate — help me improve it"
```
→ Detects agent, checks eval history, routes to optimization or GEPA.

```
$cortex-agent-toolkit
"Run the full pipeline — just make it good"
```
→ AUTOPILOT: baseline → flags → optimize → ship.
