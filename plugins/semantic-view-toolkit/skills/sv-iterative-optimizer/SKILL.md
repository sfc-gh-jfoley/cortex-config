---
name: sv-iterative-optimizer
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

## Execution Mode

Detect or ask whether to run **INTERACTIVE** or **AUTONOMOUS**:

- **INTERACTIVE** (default): Every `STOP GATE (INTERACTIVE mode)` in `setup.md`/`optimize.md`/`review.md` blocks for user input, as written.
- **AUTONOMOUS**: STOP GATEs do not block.
  - `setup.md` gate → proceed straight into the optimize loop after printing the setup summary.
  - `optimize.md` gate → apply the proposed mutation automatically (it already passed the skill's own mutation-operator logic) and run the eval.
  - `review.md` gate → follow the computed `Recommendation` automatically: `Continue iterating` → next iteration; `Escalate to sv-gepa-optimizer` → escalate; `Done` (target reached) → stop successfully. Stop and report (don't loop forever) after **3 consecutive rejections** with no score improvement — this is the same stall threshold used elsewhere in this toolkit (see `agent-optimizer`).
  - Every iteration is already written to `OPTIMIZATION_LOG` per `setup.md` — that log is the audit trail; no separate confirmation is needed before each write.

Default to INTERACTIVE if the user's preference is unclear. A standing "run to completion" /
"don't stop until tuned" directive for this task counts as an explicit request for
AUTONOMOUS without asking again.

## Prerequisites

- A deployed semantic view with at least 5 VQRs
- All sv-evaluation prerequisites met (EXECUTE TASK, CREATE TASK/DATASET, MONITOR, etc.)
- Privilege to create semantic views in the SV's schema (candidates are created there); promotion needs more and is gated (`SV-PROMOTE`)
- Baseline eval score (run sv-evaluation first if you don't have one)

**Size awareness during optimization.** Mutations that add synonyms, descriptions, metrics, or VQRs grow the SV. Re-estimate the SV's token size (~1 token per ~2.5 chars of DDL) after mutations that add content; if it approaches ~100,000 tokens, prefer mutations that *improve* existing descriptions over ones that *add* new content, and consider splitting the SV (see `sv-discovery` / `sv-rearchitect`). Above ~100K, Cortex Agents prunes the SV (latency + reduced accuracy), which can mask optimization gains in production even when eval scores improve.

## Pre-Optimization Checks

Run these **before the first optimization iteration**. They catch structural defects that corrupt eval scores and waste iteration budget.

### Check 1: VQR-Metric Filter Alignment (Critical)

For each metric with a conditional aggregation filter (a `CASE WHEN <col> = <val>` guard), scan all VQRs that aggregate the same source column. Flag any VQR that omits the guard.

**Remediation:** VQR contamination is a **read-only finding** - do NOT mutate contaminated VQRs. Exclude them from the evaluated question list (see sv-evaluation) or flag as REFERENCE_CONTAMINATED and continue with clean VQRs. A contaminated reference penalizes correct model behavior for the whole loop.

### Check 2: Cross-Table Metric Consistency (High)

Same metric name with different aggregation logic on two fact tables creates LLM ambiguity.

**Detection:** Group metric definitions by name across all tables. Compare EXPR values. Flag any pair where filter logic differs (a filter on one table and none on another).

**Remediation:** Apply `sync_metric_definitions_across_tables` — either align the expressions or rename one metric to make semantic difference explicit.

### Check 3: VQR Table Routing Validation (Medium)

A VQR that uses the wrong fact table may produce correct-looking SQL against a table with looser metric semantics.

**Detection:** For each VQR, confirm the fact table it queries is the one whose metric definitions match the question (for example the table that carries the attribute the question filters on, versus a base table with stricter metrics).

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
  → Create candidate copy (kind cand) from GET_DDL via scripts/candidate.py
  → Apply mutation to the candidate only
  → Run eval on the candidate (hold-out questions, >=2 repeats, pinned metric version)
  → Compare vs baseline under the same question list and metric version
    ↓
REVIEW (per iteration)
  → Accept: candidate becomes the working copy; log to OPTIMIZATION_LOG. Production changes only via gate SV-PROMOTE (references/candidate-promotion.md)
  → Reject: discard the candidate, log rejection
    ↓
  [Repeat OPTIMIZE until accuracy target reached or 3 consecutive rejections]
    ↓
  [3 rejections → suggest sv-gepa-optimizer for broader search]
```

---

## VQR Split Strategy

VQRs serve two roles, and the split must be real:
- **Guide VQRs**: stay in the SV as examples for Analyst.
- **Eval VQRs**: the hold-out set. Evaluation lists exactly these questions in `source_metadata.verified_queries`; guide questions are never scored.

Recommended hold-out share: 5-10 VQRs: 60%; 11-20: 70%; 20+: 75%. Record the eval question list once at setup and reuse it unchanged for every run. Hold-out questions must not also appear as VQRs in the candidate; if the SV currently contains them, evaluate on a candidate that omits them (VQR edits on the candidate only). Verify the exact omission/selection mechanics in `skills/sv-evaluation/SKILL.md`.

**Evaluation rules (Cortex Analyst contract):** use `analyst_params` with `source_metadata.type: verified_queries` and pin the metric (`sql_correctness`, version `v3`). Scores from different metric versions are not comparable; refuse to compare them. SQL generation is non-deterministic: run the same question list at least 2 times per SV state.

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
| VQR SQL missing filter that metric definition requires | **Read-only analysis** (exclude/flag; the optimizer never changes VQRs; the operator may approve a fix via `SV-VQR-MUTATE`) |
| VQR always fails and SQL contains a subquery | **Read-only finding** (flag it; the claim that Analyst cannot generate subquery SQL is unverified, so do not mutate the SV on that basis) |
| Same metric name with different filter logic on two tables | `sync_metric_definitions_across_tables` |
| Metric uses SUM(CASE WHEN ...) on the same column repeatedly | `extract_metric_filter_to_fact` |
| Pre-check: VQR health classification before eval | `detect_contaminated_vqr_baseline` |

**One mutation per iteration** - measure its impact in isolation before stacking changes.

---

## State Persistence

> **Note (INTERACTIVE mode only):** When creating `_SV_TOOLKIT_META` objects for the first
> time in INTERACTIVE mode (gate `META-ROLLBACK-CLONE`), offer: "Want me to create a rollback clone first?
> (`CREATE DATABASE <db>_RESTORE CLONE <db>`)"
> In AUTONOMOUS mode, `CREATE SCHEMA/TABLE IF NOT EXISTS` is additive and idempotent
> — no prompt needed.

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
- **ALWAYS**: Mutate a candidate, never production; run eval (>=2 repeats) after each change, check for regressions, log everything
- **STOP WHEN**: 3 rejections in a row, accuracy target met, or user satisfied
