---
name: cowork
description: >
  Snowflake CoWork: multi-step investigation and result sharing for Cortex Agents.
  Create persistent artifact references from agent responses; run multi-step deep research
  across structured and unstructured data with full source tracing. Use when you need to
  scale agent responses into investigations, share findings with teams, or trace data lineage.
triggers:
  - cowork
  - artifacts
  - deep research
  - multi-step investigation
  - research workflow
  - agent investigation
  - share findings
  - source tracing
  - data investigation
  - investigation workflow
---

> **CoWork is the investigation layer built on top of Cortex Agents.** Create agents first with
> `$cortex-agent-toolkit`; then use CoWork to run investigations, share results, and trace sources.

# Snowflake CoWork Plugin

Scalable investigation and sharing workflows for Cortex Agent responses. Two sub-skills:
- **Artifacts**: Create persistent, shareable references to agent-generated charts and tables
- **Deep Research**: Multi-step investigations across structured queries + unstructured search with full source attribution

---

## When to Use CoWork vs. Agents

| Need | Use Cortex Agent | Use CoWork |
|------|------------------|-----------|
| Simple Q&A with a tool | ✓ | — |
| Multi-turn conversation | ✓ | — |
| Create reference data / tool | ✓ | — |
| Share agent response as persistent artifact | — | ✓ (Artifacts) |
| Run 3+ step investigation across multiple sources | — | ✓ (Deep Research) |
| Trace data lineage to final finding | — | ✓ (Deep Research) |
| Permission-aware result sharing | — | ✓ (Artifacts + Deep Research) |

---

## Quick Navigation

### 1. **I want to create a persistent chart/table from my agent's response**

→ **`cowork-artifacts`** sub-skill

Use when:
- Agent generated a result you want to reference later
- You need to share it with specific team members
- You want permission control (who can access the artifact)

[Open cowork-artifacts workflow](#artifacts-workflow)

### 2. **I want to run a multi-step investigation across data + search**

→ **`cowork-deep-research`** sub-skill

Use when:
- One query isn't enough — you need a multi-step investigation
- You want to combine structured SQL results with unstructured search
- You need to know which data source produced each finding
- You're building audit trails or compliance reports

[Open cowork-deep-research workflow](#deep-research-workflow)

---

## Sub-Skills

### cowork-artifacts

**Location**: `plugins/cowork/skills/cowork-artifacts/SKILL.md`

Create and manage persistent artifact references from agent responses. Artifacts are permission-aware: creators control who can access each artifact.

- Artifact types: charts, tables, alerts, summaries
- Permission model: role-based access control
- Lifecycle: create, update, archive, share
- Use cases: sharing dashboards, team reports, audit trails

### cowork-deep-research

**Location**: `plugins/cowork/skills/cowork-deep-research/SKILL.md`

Multi-step investigation workflows combining structured queries, unstructured search, and analysis. Every finding is traced to its source.

- Source tracing: every finding links to query, search result, or analysis step
- Combining structured + unstructured: SQL queries + Cortex Search results + analysis
- Use cases: competitive analysis, customer research, incident investigation, market sizing

---

## Artifacts Workflow {#artifacts-workflow}

```
Agent response
  ├─ Extract value (chart data, query results)
  ├─ Create artifact reference
  ├─ Apply permissions (read, read+update, read+share)
  └─ Share with team
       └─ Team member accesses artifact
            └─ Data access controlled by their own grants (data ACL unchanged)
```

**Key**: Artifacts don't grant data access — they reference existing data. Permissions on the artifact itself are separate from data permissions.

---

## Deep Research Workflow {#deep-research-workflow}

```
Research question
  ├─ Plan multi-step investigation
  │   ├─ Step 1: Structured query (SQL)
  │   ├─ Step 2: Unstructured search (Cortex Search)
  │   ├─ Step 3: Analysis (combine results)
  │   └─ ...Step N
  │
  ├─ Execute each step (with source tracking)
  │   └─ For each result: record source (query ID, search result rank, analysis step)
  │
  └─ Compile findings with source attribution
       └─ "Finding X came from Query 1 (SQL: SELECT...)"
            └─ "Finding Y came from Search Result #3 (Cortex Search on 'competitive pricing')"
```

---

## Prerequisites

### For Artifacts:
- Snowflake account with CoWork artifacts feature enabled (GA as of Jun 17, 2026)
- At least one Cortex Agent created (from `$cortex-agent-toolkit`)
- Role permissions to create artifacts in your schema
- See `PREREQUISITES.md` for permission model details

### For Deep Research:
- CoWork deep research feature enabled (GA as of Jul 7, 2026)
- Cortex Search service available in your account (or unstructured search via Cortex Analytics)
- SQL query access to relevant databases/schemas
- See `PREREQUISITES.md` for full setup checklist

---

## Positioning Relative to Other Skills

| Skill | Scope | Handoff |
|-------|-------|--------|
| `cortex-agent-toolkit` | Agent creation, evaluation, optimization | Creates agents; CoWork **consumes** agents |
| `cowork` (this plugin) | Investigation, sharing, source tracing | Runs multi-step workflows on top of agents |
| `semantic-view-toolkit` | Semantic view lifecycle | Feeds data into both agents and CoWork |

**Chain**: `$semantic-view-toolkit` → SV → `$cortex-agent-toolkit` → Agent → `$cowork` → Investigation / Sharing

---

## Entry Points

### Via skill-loader

```bash
$cowork
"I want to share my agent's result as a persistent artifact"
```
→ Routes to `cowork-artifacts`

```bash
$cowork
"I need to run a multi-step investigation across databases"
```
→ Routes to `cowork-deep-research`

### Direct sub-skill invocation

```bash
$cowork:cowork-artifacts
# Opens cowork-artifacts workflow directly
```

```bash
$cowork:cowork-deep-research
# Opens cowork-deep-research workflow directly
```

---

## Quick Start

**Artifacts**: Create a persistent, shareable reference to an agent result
```bash
$cowork:cowork-artifacts
→ Phase 1: Pick agent and result
→ Phase 2: Create artifact reference
→ Phase 3: Grant access to team members
```

**Deep Research**: Run a multi-step investigation
```bash
$cowork:cowork-deep-research
→ Phase 1: Define research question
→ Phase 2: Plan multi-step workflow
→ Phase 3: Execute (with source tracking)
→ Phase 4: Compile findings with attribution
```

---

## Troubleshooting

**Q: "Artifact API not available"**  
A: CoWork artifacts require GA (Jun 17, 2026). Check `SELECT SYSTEM$COWORK_ARTIFACTS_VERSION()` in your account.

**Q: "I created an artifact but my teammate can't see the data"**  
A: Artifacts don't grant data access. Your teammate needs `SELECT` on the underlying table/view. See `PREREQUISITES.md` → Permission Model for details.

**Q: "Deep research result — where did this finding come from?"**  
A: Every finding in Deep Research output includes source attribution. Check the "Source" column for the originating query ID, search rank, or analysis step.

---

## Support

For issues or feature requests, see `README.md` for examples and use cases.
