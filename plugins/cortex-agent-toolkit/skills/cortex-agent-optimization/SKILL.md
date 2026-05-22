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
| **LIFECYCLE** | "full optimization", "end-to-end optimize", "optimize from scratch", "full lifecycle", "model sweep + optimize", "optimize everything", "complete agent optimization" | Load `references/full-lifecycle.md` and follow its phased workflow. This covers the full improvement lifecycle: Creation → Baseline → Model Sweep → Flags → Iterative Opt → GEPA → Validate & Ship. |

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
- **STOP WHEN**: 2-3 consecutive rejections on the same failures — local optimum reached

Load `references/optimization-patterns.md` for the full set of distilled patterns.
