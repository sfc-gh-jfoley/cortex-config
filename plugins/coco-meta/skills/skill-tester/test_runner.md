---
name: skill-tester-runner
description: Spawns 3 parallel subagents to run a skill end-to-end with fixture-injected inputs, then compares results for consistency and runs assertions
---

# Test Runner

## Purpose

Orchestrate 3 parallel skill test runs, collect results, compare for consistency, and produce a scored pass/fail report.

---

## Step 1: Load the fixture

Read the specified fixture file from this skill's `fixtures/` directory:
```bash
cat fixtures/<fixture_file>.yaml
```

Extract:
- `skill` — target skill name
- `inputs` — phase inputs (free-form, skill-specific)
- `output_name_field` — which inputs key holds the artifact name (optional; used to suffix run names)
- `stopping_point_responses` — auto-responses at each stopping point
- `assertions` + `skill_assertions` — what to evaluate
- `connection` — Snowflake connection
- `result_schema` — expected JSON fields from each run (optional; falls back to generic defaults)
- `consistency_fields` — fields to compare across runs (optional; falls back to primary_output length)
- `cleanup.output_suffix` — suffix to append to output artifact names to avoid collisions

Confirm fixture loaded, then proceed.

---

## Step 2: Prepare 3 run configs

If `output_name_field` is set in the fixture, read `inputs[output_name_field]` as the base name and append `_TEST_1`, `_TEST_2`, `_TEST_3`:

```
output_name_field = "sv_name"  →  base = inputs.sv_name
Run 1 name: <base>_TEST_1
Run 2 name: <base>_TEST_2
Run 3 name: <base>_TEST_3
```

If `output_name_field` is not set (read-only skills like artifact-drift-monitor):
```
Run 1 name: RUN_1
Run 2 name: RUN_2
Run 3 name: RUN_3
```

---

## Step 3: Launch 3 parallel test subagents

⚠️ **CRITICAL**: Launch all 3 in a single message as parallel Task tool calls. Do NOT launch sequentially.

Each subagent receives a prompt built from this generic template. Fill in `<FIXTURE.*>` values from the loaded fixture:

```
You are running a skill test. Your job is to execute the skill end-to-end
using the fixture inputs below, without waiting for user input at stopping points.

TARGET SKILL: <FIXTURE.skill>

START BY: Invoke the skill tool with command "<FIXTURE.skill>" to load the skill's SKILL.md
Then follow the skill's documented phases and workflow in order.

SNOWFLAKE CONNECTION: <FIXTURE.connection>

FIXTURE INPUTS (treat these as the user's initial input to the skill):
<dump FIXTURE.inputs as indented key: value pairs>

RUN NAME (use this as the output artifact name for this run, if the skill creates one):
<RUN_NAME>  ← e.g. TPCH_ORDER_ANALYTICS_TEST_1

STOPPING POINT RULES:
- This is a non-interactive test run.
- At every ⚠️ MANDATORY STOPPING POINT (or any step explicitly labelled as a stopping
  point requiring user confirmation), do NOT wait for user input.
- Instead, find the matching key in the STOPPING POINT RESPONSES map below and inject
  that response verbatim.
- If a stopping point is not in the map, respond "yes" (default accept).

STOPPING POINT RESPONSES:
<dump FIXTURE.stopping_point_responses as indented key: value pairs>

RESULT: When you have completed all phases, output a JSON block with these fields.
Use the skill-specific fields below if provided, otherwise use generic defaults.

RESULT SCHEMA:
<if FIXTURE.result_schema is set, dump it here>
<otherwise use generic defaults:>
{
  "run": "<RUN_NAME>",
  "skill_completed": true/false,
  "phases_executed": ["<phase name>", ...],
  "phase_errors": ["<phase_name: error message>", ...],
  "primary_output": "<the main artifact text, DDL, SQL, or report produced>",
  "output_artifact_name": "<name of any Snowflake object created, or null>",
  "warnings": ["<any warnings>"]
}
```

---

## Step 4: Wait for all 3 subagents to complete

Monitor all 3 in parallel using `agent_output(wait=true)`. Do not proceed until all 3 have returned their JSON result blocks.

If a subagent fails or times out, record it as:
```json
{"run": "RUN_N", "skill_completed": false, "phase_errors": ["subagent timeout or crash"], "primary_output": ""}
```

---

## Step 5: Run assertions

Load [assertions.md](assertions.md) for the assertion evaluation logic.

Evaluate **generic assertions** first (apply to every skill):

| Assertion | Run 1 | Run 2 | Run 3 | Pass? |
|-----------|-------|-------|-------|-------|
| `skill_completed` | ✓ | ✓ | ✓ | ✓ |
| `no_phase_errors` | ✓ | ✓ | ✓ | ✓ |
| `output_not_empty` | ✓ | ✓ | ✓ | ✓ |

Then evaluate **skill-specific assertions** from `fixture.skill_assertions` (or `fixture.assertions` for backwards compatibility).

An assertion **PASSES** if all 3 runs satisfy it.
An assertion **WARNS** if 1-2 of 3 runs satisfy it.
An assertion **FAILS** if 0 runs satisfy it.

---

## Step 6: Consistency scoring

If `fixture.consistency_fields` is set, compare those specific fields across runs with their weights and tolerances.

If not set, use a generic fallback: compare `primary_output` length across runs.

| Dimension | Weight | How to score |
|-----------|--------|-------------|
| (from fixture.consistency_fields, or generic below) | | |
| primary_output length | 100% | max - min ≤ 10% of max → 100%; ≤ 25% → 80%; else → 50% |

**Interpretation**:
- 90-100%: Excellent — skill is deterministic
- 75-89%: Good — minor variation
- 60-74%: Acceptable
- < 60%: Poor — skill has non-determinism issue

---

## Step 7: Present final report

Use the report template below (no external file needed):

```
╔══════════════════════════════════════════════════════════════════╗
║  SKILL TEST REPORT                                               ║
║  Skill: <fixture.skill>                                          ║
║  Fixture: <fixture_file>                                         ║
║  Runs: 3   Time: <duration>                                      ║
╠══════════════════════════════════════════════════════════════════╣
║  ASSERTIONS                          Run1  Run2  Run3  Status    ║
║  skill_completed                       ✓     ✓     ✓    PASS     ║
║  no_phase_errors                       ✓     ✓     ✓    PASS     ║
║  <skill-specific assertions...>                                  ║
╠══════════════════════════════════════════════════════════════════╣
║  CONSISTENCY SCORE:  XX%  (<rating>)                             ║
╠══════════════════════════════════════════════════════════════════╣
║  OVERALL VERDICT:  ✅ PASS / ❌ FAIL  (N/N assertions)            ║
║                                                                  ║
║  Output artifacts (if any):                                      ║
║    <RUN_1 output artifact name or "none">                        ║
║    <RUN_2 output artifact name or "none">                        ║
║    <RUN_3 output artifact name or "none">                        ║
╠══════════════════════════════════════════════════════════════════╣
║  RECOMMENDATIONS:                                                ║
║  • <any issues or suggestions>                                   ║
╚══════════════════════════════════════════════════════════════════╝
```

⚠️ **STOPPING POINT** — Present report and wait for user's next action:
- Re-run failing assertions
- Update the skill to fix issues
- Save this report to a file
- Build a new fixture for edge cases
