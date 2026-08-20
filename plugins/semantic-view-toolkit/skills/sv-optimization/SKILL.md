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

**Size awareness during optimization.** Mutations that add synonyms, descriptions, metrics, or VQRs grow the SV. Re-estimate the SV's token size after mutations that add content; if it approaches ~100,000 tokens, prefer mutations that *improve* existing descriptions over ones that *add* new content, and consider splitting the SV (see `sv-discovery` / `sv-composer`). Above ~100K, Cortex Agents prunes the SV (latency + reduced accuracy), which can mask optimization gains in production even when eval scores improve.

## Pre-Optimization Checks

Run these **before the first optimization iteration**. They catch structural defects that corrupt eval scores and waste iteration budget.

### Check 1: VQR-Metric Filter Alignment (Critical)

For each metric with a conditional aggregation filter (e.g., `CASE WHEN REFUNDED_IND = 0`), scan all VQRs that aggregate the same source column. Flag any VQR that omits the required filter.

**Detection:** Extract `CASE WHEN <col> = <val>` patterns from metric exprs → check each VQR's SQL for the same guard.

**Remediation:** VQR contamination is a **read-only finding** — do NOT apply mutations to contaminated VQRs. Instead, exclude them from optimization (see Step 3b in sv-evaluation/SKILL.md) or flag as REFERENCE_CONTAMINATED and continue optimizing with clean VQRs. A contaminated VQR baseline will penalize correct model behavior throughout the entire optimization loop.

### Check 2: Cross-Table Metric Consistency (High)

Same metric name with different aggregation logic on two fact tables creates LLM ambiguity.

**Detection:** Group metric definitions by name across all tables. Compare EXPR values. Flag any pair where filter logic differs (e.g., `TOTAL_NET_REVENUE_USD` with filter on one table, without on another).

**Remediation:** Apply `sync_metric_definitions_across_tables` — either align the expressions or rename one metric to make semantic difference explicit.

### Check 3: VQR Table Routing Validation (Medium)

A VQR that uses the wrong fact table may produce correct-looking SQL against a table with looser metric semantics.

**Detection:** For VQRs querying extended attributes (discounts, campaign data, upgrade flags), confirm they use `FCT_*_EXT` rather than the base fact table. For revenue-only questions, confirm they use the base fact table with stricter metric definitions.

**Remediation:** Manually review flagged VQRs and update table references if misrouted.

---

## Intent Detection

| Intent | Trigger Patterns | Action |
|--------|-----------------|--------|
| **SETUP** | "set up optimization", "initialize", "scaffold" | Load `references/setup.md` |
| **OPTIMIZE** | "run iteration", "optimize", "improve", "next iteration", "fix failures" | Load `references/optimize.md` |
| **REVIEW** | "review results", "accept or reject", "compare scores" | Load `references/review.md` |
| **EVAL-DATA** | "manage VQRs", "add VQRs", "rebalance", "VQR split" | Load `references/eval-data.md` |

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
| VQR SQL missing filter that metric definition requires | **Read-only analysis** (exclude/flag; do not modify) |
| VQR always fails and SQL contains a subquery | **Read-only finding** (flag; remove VQR or rewrite without subquery — Analyst cannot generate subquery-based SQL; do not mutate the SV) |
| Same metric name with different filter logic on two tables | `sync_metric_definitions_across_tables` |
| Metric uses SUM(CASE WHEN ...) on the same column repeatedly | `extract_metric_filter_to_fact` |
| Pre-check: VQR health classification before eval | `detect_contaminated_vqr_baseline` |

**One mutation per iteration** — measure its impact in isolation before stacking changes.

---

## State Persistence

> **DDL/DML safety gate**: Per account mutation policy, before creating `_SV_TOOLKIT_META`
> objects ask the user: "Want me to create a rollback clone first so we can undo this?
> (`CREATE DATABASE <db>_RESTORE CLONE <db>`)"
> If yes, create the clone before proceeding.

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
