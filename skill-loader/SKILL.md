---
name: skill-loader
description: "On-demand skill/plugin/rule loader. Keeps context minimal — loads only what's needed for the current task."
---

# Skill Loader

Load skills, plugins, and rules on-demand from `~/.snowflake/cortex/vault/`. 

## Workflow

1. Identify which skill the user needs from the registry below
2. Read the SKILL.md: `~/.snowflake/cortex/vault/{path}/SKILL.md`
3. Follow the loaded skill's instructions for the remainder of the task

If unsure which skill matches, ask the user.

---

## Registry

### Semantic Views & Analyst

| Skill | When to use | Path |
|-------|-------------|------|
| semantic-view-toolkit | Full SV lifecycle router (discovery, DDL, audit, eval, optimization, GEPA, watch, compose, VQR) | `plugins/semantic-view-toolkit/` |
| sv-discovery | Find SV candidates from schema analysis | `plugins/semantic-view-toolkit/skills/sv-discovery/` |
| sv-ddl | Build/edit semantic views (DDL path) | `plugins/semantic-view-toolkit/skills/sv-ddl/` |
| sv-audit | Audit existing SV against usage patterns | `plugins/semantic-view-toolkit/skills/sv-audit/` |
| sv-evaluation | Run Cortex Analyst evaluations on SVs | `plugins/semantic-view-toolkit/skills/sv-evaluation/` |
| sv-optimization | Iterative SV improvement loop | `plugins/semantic-view-toolkit/skills/sv-optimization/` |
| sv-gepa-optimizer | Population-based evolutionary SV optimization | `plugins/semantic-view-toolkit/skills/sv-gepa-optimizer/` |
| sv-watch | Drift detection + SV maintenance monitoring | `plugins/semantic-view-toolkit/skills/sv-watch/` |
| sv-composer | Nested SVs + multi-SV agent composition | `plugins/semantic-view-toolkit/skills/sv-composer/` |
| vqr-generator | Auto-generate verified queries from query history | `plugins/semantic-view-toolkit/skills/vqr-generator/` |
| semantic-view-ddl | (LEGACY) Build/edit semantic views — use sv-ddl instead | `skills/semantic-view-ddl/` |
| semantic-view-discovery | (LEGACY) Find SV candidates — use sv-discovery instead | `skills/semantic-view-discovery/` |

### Cortex Agents

| Skill | When to use | Path |
|-------|-------------|------|
| cortex-agent-toolkit | Full agent lifecycle router (create, eval, flags, optimize, GEPA, query) | `plugins/cortex-agent-toolkit/` |
| cortex-agent-ddl | Create/deploy Cortex Agents | `plugins/cortex-agent-toolkit/skills/cortex-agent-ddl/` |
| cortex-agent-flags | Agent experimental flags reference | `plugins/cortex-agent-toolkit/skills/cortex-agent-flags/` |
| cortex-agent-optimization | Iterative agent prompt optimization + full lifecycle | `plugins/cortex-agent-toolkit/skills/cortex-agent-optimization/` |
| agent-evaluation | Run EXECUTE_AI_EVALUATION | `plugins/cortex-agent-toolkit/skills/agent-evaluation/` |
| agent-flag-tester | Compare agent flag variants (3-way) | `plugins/cortex-agent-toolkit/skills/agent-flag-tester/` |
| query-cortex-agent | Query an existing agent via SQL | `plugins/cortex-agent-toolkit/skills/query-cortex-agent/` |
| agent-gepa-optimizer | Evolutionary population-based agent optimization | `plugins/cortex-agent-toolkit/skills/agent-gepa-optimizer/` |

### Knowledge Graph & Ontology

| Skill | When to use | Path |
|-------|-------------|------|

### Ops & Monitoring

| Skill | When to use | Path |
|-------|-------------|------|
| artifact-drift-monitor | Check SV/DT/Agent drift | `plugins/ops-monitor/skills/artifact-drift-monitor/` |
| release-change-monitor | Monitor Snowflake release changes | `plugins/ops-monitor/skills/release-change-monitor/` |
| self-healing-pipeline | Auto-fix pipeline failures | `plugins/ops-monitor/skills/self-healing-pipeline/` |

### Rules & Governance

| Skill | When to use | Path |
|-------|-------------|------|
| rule-loader | Load coding rules for current task | `plugins/rule-governance/skills/rule-loader/` |
| rule-creator | Create new rules | `plugins/rule-governance/skills/rule-creator/` |
| rule-reviewer | Review a single rule quality | `plugins/rule-governance/skills/rule-reviewer/` |
| bulk-rule-reviewer | Batch review rules | `plugins/rule-governance/skills/bulk-rule-reviewer/` |
| memory-organizer | Clean/consolidate memories | `plugins/rule-governance/skills/memory-organizer/` |

### Meta & Quality

| Skill | When to use | Path |
|-------|-------------|------|
| doc-reviewer | Review documents for quality | `plugins/coco-meta/skills/doc-reviewer/` |
| plan-reviewer | Score implementation plans | `plugins/coco-meta/skills/plan-reviewer/` |
| prompt-determinism-tester | Test prompt consistency (3-agent) | `plugins/coco-meta/skills/prompt-determinism-tester/` |
| skill-tester | Test skills with fixtures | `plugins/coco-meta/skills/skill-tester/` |
| skill-timing | Measure skill execution time | `plugins/coco-meta/skills/skill-timing/` |

### Workshops & Demos

| Skill | When to use | Path |
|-------|-------------|------|
| lab-builder | Build HOL/workshop labs | `skills/lab-builder/` |

### Project Architecture

| Skill | When to use | Path |
|-------|-------------|------|
| agent-architect | Multi-agent project builds (full framework, v3.0) | `skills/agent-architect/` |

### Diagrams & Visuals

| Skill | When to use | Path |
|-------|-------------|------|
| architecture-diagram | Generate architecture/system/flow diagrams (Mermaid→Excalidraw→PNG) | `skills/architecture-diagram/` |
| snowflake-gslides | Create Google Slides decks | `skills/snowflake-gslides/` |

### Utilities

| Skill | When to use | Path |
|-------|-------------|------|
| coco-usage | CoCo token/credit consumption analysis | `skills/coco-usage/` |
| google-doc-formatter | Format markdown as Google Doc | `skills/google-doc-formatter/` |

---

## Loading Rules (coding standards)

For coding rules, first load rule-loader:
```
Read: ~/.snowflake/cortex/vault/plugins/rule-governance/skills/rule-loader/SKILL.md
```
Then follow its workflow to load specific rule files from `~/.snowflake/cortex/rules/`.

---

## Constraints

- **Load one skill at a time** — don't bulk-load
- **After loading**: follow that skill's instructions completely as if natively invoked
- **If the skill references sub-files** (phases/, references/, etc.): those are relative to the skill's vault directory
- **All vault paths are relative to** `~/.snowflake/cortex/vault/`
