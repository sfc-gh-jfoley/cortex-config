---
name: sv-optimization
description: >
  Iterative optimization of Snowflake Semantic Views using Cortex Analyst evaluations.
  Covers project setup, VQR management, mutation-based improvement, eval execution,
  failure analysis, and accept/reject decisions.
triggers:
  - optimize semantic view
  - improve SV accuracy
  - SV optimization
  - iterate on SV
  - fix SV failures
  - tune my semantic view
  - sv iteration
  - run sv eval and improve
---

# SV Optimization Skill

## When to Use

Use this skill when you have a semantic view with VQRs and want to systematically improve its accuracy through iterative mutations guided by evaluation results.

## Prerequisites

- A deployed semantic view with at least 5 VQRs
- All sv-evaluation prerequisites met (EXECUTE TASK, CREATE TASK/DATASET, MONITOR, etc.)
- CREATE OR REPLACE SEMANTIC VIEW privilege
- Baseline eval score (run sv-evaluation first if you don't have one)

## Intent Detection

| Intent | Trigger Patterns | Action |
|--------|-----------------|--------|
| **SETUP** | "set up optimization", "initialize", "scaffold" | Load `setup/SKILL.md` |
| **OPTIMIZE** | "run iteration", "optimize", "improve", "next iteration", "fix failures" | Load `optimize/SKILL.md` |
| **REVIEW** | "review results", "accept or reject", "compare scores" | Load `review/SKILL.md` |
| **EVAL-DATA** | "manage VQRs", "add VQRs", "rebalance", "VQR split" | Load `eval-data/SKILL.md` |

---

## Workflow Overview

```
SETUP (one-time)
  → Create _SV_TOOLKIT_META tables
  → Record baseline eval score
  → Configure VQR split (guide vs eval)
    ↓
OPTIMIZE (iterative loop)
  → Analyze eval failures
  → Select mutation operator
  → Apply mutation to SV DDL
  → Deploy: CREATE OR REPLACE SEMANTIC VIEW
  → Run eval on modified SV
  → Compare vs baseline
    ↓
REVIEW (per iteration)
  → Accept: new SV becomes baseline, log to OPTIMIZATION_LOG
  → Reject: revert to previous DDL, log rejection
    ↓
  [Repeat OPTIMIZE until accuracy target reached or 3 consecutive rejections]
    ↓
  [3 rejections → suggest sv-gepa-optimizer for broader search]
```

---

## VQR Split Strategy

VQRs serve dual purpose in optimization:
- **Guide VQRs**: remain in the SV during eval to guide Analyst (like few-shot examples)
- **Eval VQRs**: removed during eval (holdout) to test generalization

Split recommendation:
- 5-10 VQRs total: 60% eval / 40% guide
- 11-20 VQRs total: 70% eval / 30% guide
- 20+ VQRs: 75% eval / 25% guide

The eval system automatically holds out eval VQRs (Snowflake handles this), but we track which are "guide-quality" vs "eval-quality" for the optimization loop.

---

## Mutation Strategy

Each iteration applies ONE mutation from `references/mutation-operators.md`:

| Eval Failure Pattern | Recommended Operator |
|---|---|
| Wrong column selected | `improve_description`, `add_synonym` |
| Wrong aggregation | `add_metric`, `refine_metric_expr` |
| Wrong join/table | `change_relationship` |
| Wrong time filter | `add_time_dimension` |
| Analyst confused by too many options | `remove_column` |
| Analyst refuses question | `add_vqr` (teach by example) |
| Wrong filter applied | `add_filter` |

**One mutation per iteration** — measure its impact in isolation before stacking changes.

---

## State Persistence

```sql
CREATE TABLE IF NOT EXISTS <DB>._SV_TOOLKIT_META.OPTIMIZATION_LOG (
    ITERATION_ID VARCHAR,
    TIMESTAMP TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
    SV_FQN VARCHAR,
    MUTATION_OPERATOR VARCHAR,
    MUTATION_DESCRIPTION VARCHAR,
    EVAL_SCORE_BEFORE FLOAT,
    EVAL_SCORE_AFTER FLOAT,
    REGRESSIONS INT,
    DECISION VARCHAR,  -- ACCEPTED / REJECTED
    DDL_SNAPSHOT VARCHAR,
    NOTES VARCHAR
);
```

---

## Termination Conditions

| Condition | Action |
|---|---|
| Accuracy target reached (user-defined, default 85%) | Celebrate, stop |
| 3 consecutive rejections | Suggest sv-gepa-optimizer |
| All VQRs passing | Stop — nothing left to improve |
| User says "stop" | Stop, report final state |

---

## Quick Reference

- **DO**: Apply one mutation at a time, target specific failures, use evidence from eval
- **DON'T**: Stack multiple mutations, change things randomly, ignore regressions
- **ALWAYS**: Run eval after each change, check for regressions, log everything
- **STOP WHEN**: 3 rejections in a row, accuracy target met, or user satisfied
