---
name: cortex-agent-optimization
description: >
  Iterative optimization of Snowflake Cortex Agents using dev/test eval splits.
  Covers project setup, instruction editing, build/deploy, eval execution,
  failure analysis, and accept/reject decisions.
  Use when: optimizing agent instructions, running agent evals, improving agent
  accuracy, setting up eval splits, analyzing agent failures.
  Triggers: optimize agent, agent eval, improve agent, agent iteration,
  run eval, optimization loop, agent instructions, eval split,
  run optimization, next iteration, analyze agent failures, accept reject iteration,
  flag sweep, revalidate flags, flag recheck, full optimization, end-to-end optimize,
  optimize from scratch, full lifecycle, model sweep, complete agent optimization.
  Note: for standalone 3-variant flag comparison use agent-flag-tester. This skill's
  FLAG SWEEP sub-skill handles flag revalidation within an active optimization project.
---

## When to Use

This skill applies when a user has (or wants to create) a Snowflake Cortex Agent with markdown-based instructions and wants to iteratively improve it using evaluations with a dev/test split. It covers the full optimization lifecycle: project scaffolding, eval dataset management, instruction editing guided by failure analysis, build/deploy, evaluation execution with statistical rigor (configurable runs per split), and data-driven accept/reject decisions.

## Prerequisites

- A deployed Snowflake Cortex Agent (or intent to create one)
- `snow` CLI installed and a named connection configured
- Python 3.11+ (for the build script)

## Related Skills

**Bundled alternatives:** Snowflake provides a bundled `cortex-agent` skill with sub-skills for agent lifecycle management, including `optimize-cortex-agent`. This custom skill differs by providing statistical rigor through dev/test splits and multi-run evaluations. See README.md "Related Bundled Skills" section for detailed comparison.

**Complementary workflows:** This skill can leverage bundled sub-skills for dataset creation (`dataset-curation`), debugging (`debug-single-query-for-cortex-agent`), and ad-hoc testing (`adhoc-testing-for-cortex-agent`). References are provided in the relevant workflow steps.

## Setup

Load `references/project-structure.md` for context on the expected file layout and conventions.

## Intent Detection

Detect the user's intent and route to the appropriate sub-skill:

| Intent | Trigger Patterns | Action |
|--------|-----------------|--------|
| **SETUP** | "set up optimization", "scaffold", "initialize optimization", "set up eval" | Load `setup/SKILL.md` and follow its workflow |
| **OPTIMIZE** | "run iteration", "optimize", "improve agent", "next iteration", "run eval", "analyze failures", "resume iteration" | Load `optimize/SKILL.md` and follow its workflow |
| **REVIEW** | "review results", "accept or reject", "compare iterations", "check test scores", "finalize iteration" | Load `review/SKILL.md` and follow its workflow |
| **EVAL DATA** | "create eval split", "validate split", "check eval balance", "split quality", "re-balance eval", "eval dataset" | Load `eval-data/SKILL.md` and follow its workflow |
| **FLAG SWEEP** | "flag sweep", "revalidate flags", "re-run flag comparison", "compare EnableAgenticAnalyst", "compare feature flags" | Load `flag-sweep/SKILL.md` and follow its workflow. **Note:** for standalone 3-variant comparison from scratch (no active optimization project), route to `agent-flag-tester` instead. |
| **FLAG REVALIDATION** | "revalidate flags", "re-test flags", "flag recheck", "confirm flag choice", "flags still hold", auto-triggered after 3 accepted iterations | Load `flag-sweep/SKILL.md` with `mode=REVALIDATE` (see below) |
| **FEEDBACK** | "pull feedback", "feedback to eval", "grow eval from feedback", "curate feedback", "promote feedback", "user feedback" | Load `feedback-pipeline/SKILL.md` and follow its workflow |
| **DIAGNOSE** | "diagnose agent failures", "why is my agent failing", "is it the SV or the agent", "root cause", "debug failures", "what's wrong with my agent" | Run inline diagnostic below |
| **RESUME_AFTER_SV_CHANGE** | "I fixed the semantic view", "SV was updated", "semantic view changed", "resume after SV fix", "SV is fixed now" | Run inline re-entry workflow below |
| **LIFECYCLE** | "full optimization", "end-to-end optimize", "optimize from scratch", "full lifecycle", "model sweep + optimize", "optimize everything", "complete agent optimization" | Load `references/full-lifecycle.md` and follow its phased workflow. This covers the full improvement lifecycle: Creation → Baseline → Model Sweep → Flags → Iterative Opt → GEPA → Validate & Ship. |

### DIAGNOSE Workflow

When DIAGNOSE intent is detected, run this 3-step diagnostic before recommending any fixes.

**Step 1: Can the SV answer these questions at all?**
For each failing question, run:
```bash
cortex analyst query "<question>" --view=<SEMANTIC_VIEW_FQN>
```
- Empty result or error → **SV gap**. Stop here. Route to `sv-ddl`.
- Returns data → proceed to Step 2.

**Step 2: Does the SV answer match what we expect?**
Compare the SV's output to `ground_truth_output` for each question.
- SV returns wrong/partial data → **SV quality issue**. Route to `sv-optimization`.
- SV returns correct data but agent answer is wrong → **Agent instruction problem**. Proceed to OPTIMIZE.

**Step 3: Is the failure consistent or intermittent?**
Run the failing question through the agent 3 times (via `DATA_AGENT_RUN`).
- Fails 2+/3 times → Real failure. Proceed to OPTIMIZE.
- Fails 1/3 times → Non-determinism. Route to `vqr-generator`.

Present a clear verdict:
```
Diagnosis complete:

  Question 1: "..." → SV gap (missing metric) → Fix: sv-ddl
  Question 2: "..." → Agent instruction problem → Fix: optimize
  Question 3: "..." → Non-deterministic SQL → Fix: vqr-generator

Recommended order: Fix SV gaps first, then optimize instructions,
then add VQRs for remaining non-determinism.
```

### RESUME_AFTER_SV_CHANGE Workflow

When a user returns after fixing a semantic view, do NOT simply resume optimization.
Ground truth may now be stale — the SV returns different data than when it was written.

**Step 1: Re-run SV pre-flight**
For all DEV questions in the formerly-failing TEST_CATEGORY, run:
```bash
cortex analyst query "<question>" --view=<SEMANTIC_VIEW_FQN>
```
Confirm the previously-failing questions now return data. Present a before/after:
```
SV Pre-flight (post-fix):
  ✓ 4/4 previously-failing questions now return data
  ✓ 14/14 previously-passing questions still return data
```

**Step 2: Flag stale ground truth**
For each question that was previously failing, compare the new SV output to the stored
`ground_truth_output` in the eval table:

```sql
SELECT INPUT_QUERY, GROUND_TRUTH:ground_truth_output::STRING AS current_gt
FROM <EVAL_TABLE>
WHERE TEST_CATEGORY = '<affected_category>';
```

Run `cortex analyst query` for each row and surface discrepancies:
```
Potential stale ground truth detected:
  Q: "What is churn rate by region?"
  Current GT: "West region has highest churn at 12%"
  SV now returns: "West 14%, East 11%, Central 9%"
  → Ground truth needs updating (data changed or SV calculation fixed)
```

**Step 3: Update stale rows**
For each stale row, propose the updated ground truth and ask for confirmation before
writing the UPDATE SQL. Apply approved updates.

**Step 4: Run fresh baseline eval**
After ground truth is confirmed current:
> "SV is fixed and ground truth is validated. Running a fresh DEV baseline before
> resuming optimization — previous iteration scores are no longer comparable."

Fire a new DEV eval run named `post_sv_fix_baseline`. This becomes the new comparison
baseline for future iterations. Route to OPTIMIZE with this baseline loaded.

**Auto-trigger:** If `flag_sweep_baseline.json` exists in the workspace AND the optimization log shows `revalidation_interval` accepted iterations since the last flag validation, automatically suggest FLAG REVALIDATION before the next OPTIMIZE iteration. The user can defer ("skip for now") or proceed.

If intent is ambiguous, ask the user which mode they want.

## Execution Mode

Detect or ask whether to run in **supervised** or **autonomous** mode:

- **Supervised** (default): All `⚠️ STOP` gates are active. The user approves each decision before proceeding.
- **Autonomous**: STOP gates are skipped. Cortex Code runs the full optimization loop until a termination condition is met. Stricter acceptance criteria apply (statistical significance required). Automated termination: 3 consecutive rejected iterations = stop and report remaining failures as known limitations.

Default to supervised if the user's preference is unclear.

## Ctx Rules

Set these rules on first use of this skill:

```
cortex ctx rule add "Only analyze DEV failures to make instruction changes; never examine TEST results before deploying"
cortex ctx rule add "Never drop eval datasets; only drop stale version locks"
cortex ctx rule add "Always read optimization log before starting an iteration"
cortex ctx rule add "In autonomous mode, stop after 3 consecutive rejected iterations and report remaining failures as known limitations"
```

## Quick Reference

- **DO**: Add tool retry logic, fix buggy examples, use "WRONG" examples, make small targeted changes
- **DON'T**: Add verbose checklists, modify tool descriptions for routing, change tool order, keep strengthening the same failing rule
- **ALWAYS**: Revert on TEST regression, log every iteration, separate DEV analysis from TEST evaluation
- **STOP WHEN**: 3 consecutive rejections on the same failures — local optimum reached

Load `references/optimization-patterns.md` for the full set of distilled patterns.
