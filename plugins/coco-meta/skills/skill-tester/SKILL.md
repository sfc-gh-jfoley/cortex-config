---
name: skill-tester
description: Test CoCo skills end-to-end by running them with pre-defined fixture inputs and evaluating outputs against assertions. Modeled after agent-flag-tester — spawns 3 parallel runs, compares consistency, reports pass/fail per assertion.
triggers:
  - test skill
  - run skill test
  - skill test
  - verify skill works
  - skill tester
---

# Skill Tester

## When to use

Use after building or modifying a CoCo skill to verify it:
- Follows its phases correctly with pre-defined inputs
- Produces valid, consistent outputs across multiple runs
- Handles edge cases and error conditions

Modeled on the `agent-flag-tester` pattern: 3 parallel runs → compare consistency → assertion scoring → pass/fail report.

---

## How skills are tested

Skills have **interactive stopping points** where they normally wait for user input.
The tester bypasses these by injecting pre-defined responses from a **fixture file**.

Each test run spawns a subagent that:
1. Reads the target skill's phase files
2. Executes each phase using fixture-provided inputs at stopping points
3. At the end, runs assertions and returns a structured result

Three parallel runs catch:
- **Consistency failures**: same inputs, different DDL/outputs (indicates non-determinism)
- **Validity failures**: DDL that doesn't execute or fails DESCRIBE
- **Quality failures**: descriptions blank, wrong column counts, etc.

---

## Entry points

### Run tests against an existing fixture

**→ Load [test_runner.md](test_runner.md)**

Tell the runner which skill and fixture to use:
```
Test skill: doc-reviewer
Fixture: fixtures/doc_reviewer_readme_full.yaml
Runs: 3
```

### Build a new fixture for a skill

**→ Load [fixture_format.md](fixture_format.md)**

### Understand assertions

**→ Load [assertions.md](assertions.md)**

---

## Available fixtures

6 bundled fixture files test the skills within this plugin. Run any with: `"Run skill tester on fixtures/<filename>.yaml"`. To build a new fixture, load [fixture_format.md](fixture_format.md).

| Fixture file | Skill | Scenario |
|-------------|-------|---------|
| [fixtures/doc_reviewer_readme_full.yaml](fixtures/doc_reviewer_readme_full.yaml) | doc-reviewer | FULL mode README review — 6 dims/100pt, cross-ref + link tables |
| [fixtures/doc_reviewer_readme_audit.yaml](fixtures/doc_reviewer_readme_audit.yaml) | doc-reviewer | FULL mode README audit — 6-dimension, 100-point rubric |
| [fixtures/plan_reviewer_full_mode.yaml](fixtures/plan_reviewer_full_mode.yaml) | plan-reviewer | FULL mode plan review — 8 dims/100pt, Priority 1 compliance |
| [fixtures/prompt_determinism_tester_single_prompt.yaml](fixtures/prompt_determinism_tester_single_prompt.yaml) | prompt-determinism-tester | Single prompt SUGGEST mode determinism test |
| [fixtures/skill_tester_meta_test.yaml](fixtures/skill_tester_meta_test.yaml) | skill-tester | Meta-test: run skill-tester against itself |
| [fixtures/skill_timing_single_skill.yaml](fixtures/skill_timing_single_skill.yaml) | skill-timing | Time single skill execution with start/checkpoint/end |

---

## Quick start

"Run skill tester against doc-reviewer using the README full fixture, 3 runs."

→ Loads test_runner.md → spawns 3 parallel subagents → returns consolidated report
