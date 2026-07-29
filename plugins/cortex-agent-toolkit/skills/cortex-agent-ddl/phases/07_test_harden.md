---
name: cortex-agent-ddl-phase7-test-harden
description: Smoke test the live agent with DATA_AGENT_RUN, score responses, iterate on failures, write handoff.json for eval skill pipeline handoff
---

# Phase 7: Test & Harden

## Purpose
Smoke test the live agent with 2-3 sample questions, score the responses, iterate if needed, and write a `handoff.json` that feeds directly into `agent-flag-tester` and `cortex-agent-optimization`. This is the bridge between creation and the full evaluation pipeline.

This phase has **one mandatory stopping point** — present smoke test results and offer eval skill handoffs.

---

## Step 7.1: Smoke test with DATA_AGENT_RUN

Pick 2-3 questions from `SAMPLE_QUESTIONS` (from Phase 3). Cover different question types: one aggregate, one filter, one trend.

For each question, use the FLATTEN pattern — the text response index varies by account so hardcoding `content[N]` is unreliable:

```sql
-- Preferred: portable across all accounts (content index varies)
SELECT f.value:text::STRING AS answer
FROM TABLE(FLATTEN(
  TRY_PARSE_JSON(
    SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
      '<AGENT_FQN>',
      $${"messages":[{"role":"user","content":[{"type":"text","text":"<question>"}]}]}$$
    )
  ):content
)) f
WHERE f.value:type::STRING = 'text'
ORDER BY f.index DESC
LIMIT 1;
```

> **Note**: If you already know the text index for your account (e.g. `content[6]` or `content[7]`), you can use `:content[N]:text::STRING` as a quicker shorthand — but the FLATTEN pattern above is preferred for portability.

---

## Step 7.2: Score each response

For each question, evaluate:

| Criterion | PASS | WARN | FAIL |
|-----------|------|------|------|
| Response returned | Non-null text | — | NULL / timeout |
| Correct tool called | Matches expected tool from description | — | Wrong tool or no tool |
| Answer is quantified | Contains a number, date, or named entity | Vague/narrative | "I cannot answer" |
| No hallucination signals | Cites data; no invented company names | Hedged language | States facts with no data support |
| Response uses right domain | Matches AGENT_PURPOSE | Partial match | Completely off-domain |

Score: PASS = 2pts, WARN = 1pt, FAIL = 0pt. Max per question = 10pts.

---

## Step 7.3: Handle failures

**If a question gets FAIL on "Response returned"**:
- Check `budget.seconds` — may be timing out → increase and re-run Phase 5+6
- Check warehouse is running: `SELECT CURRENT_WAREHOUSE()`

**If a question gets FAIL on "Correct tool called"**:
- The tool description needs a stronger "When to use" signal
- Return to Phase 2 Step 2.6, regenerate the description with more specific routing language
- Re-run Phase 5 self-check → Phase 6 execute → Phase 7 test

**If a question gets FAIL on "I cannot answer"**:
- The semantic view may not cover this question → check SV_METADATA
- Or the orchestration instructions are too restrictive → return to Phase 3

**Iteration limit**: after 2 rounds without improvement, surface to user with specific diagnosis. Do not loop indefinitely.

---

## Step 7.4: Export agent spec

Save the final validated spec to a local file:

```bash
cat > <AGENT_NAME>_spec.json << 'EOF'
<AGENT_SPEC_LIVE>
EOF
```

Note the file path as `SPEC_EXPORT_PATH`.

---

## Step 7.5: Write handoff.json

> ⚠️ **MANDATORY — execute immediately.** Write this file now using the Write file tool. Do not defer, skip, or treat this as optional. This step must complete before Step 7.6.

> **Schema reference:** `reference/handoff-schema.json` — canonical field definitions and types for this file. Downstream consumers (`agent-flag-tester`, `cortex-agent-optimization`) read from this contract.

Write the following JSON to `./<AGENT_NAME>_handoff.json` (using the Write tool, not bash heredoc):

```json
{
  "agent_fqn": "<AGENT_FQN>",
  "agent_name": "<AGENT_NAME>",
  "database": "<AGENT_DB>",
  "schema": "<AGENT_SCHEMA>",
  "connection": "<AGENT_CONNECTION>",
  "warehouse": "<AGENT_WAREHOUSE>",
  "model": "<AGENT_MODEL>",
  "tools": [
    {
      "name": "<tool_name>",
      "type": "<tool_type>",
      "source_fqn": "<sv_or_css_fqn>"
    }
  ],
  "sample_questions": <SAMPLE_QUESTIONS>,
  "smoke_test_results": [
    {
      "question": "<question>",
      "score": <N>,
      "status": "PASS|WARN|FAIL",
      "notes": "<any failure notes>"
    }
  ],
  "created_at": "<ISO timestamp>",
  "spec_export_path": "<SPEC_EXPORT_PATH>"
}
```

After writing, verify the file exists:
```bash
ls -la ./<AGENT_NAME>_handoff.json
```

Set `HANDOFF_PATH` to the absolute path of the file.

This file is the input contract for:
- `agent-flag-tester` (Phase 1 auto-loads it if present in current directory)
- `cortex-agent-optimization` (reads `agent_fqn` + `sample_questions` for DEV split seeding)

---

## ⚠️ MANDATORY STOP — Smoke test results + eval handoff offer

Present results:

```
Smoke test results for <AGENT_FQN>:

  Q1: "<question>"
      Score: <N>/10  Status: PASS ✓
      Answer preview: "<first 100 chars of answer>"

  Q2: "<question>"
      Score: <N>/10  Status: WARN ⚠️
      Issue: Response vague — no numeric answer returned

  Q3: "<question>"
      Score: <N>/10  Status: PASS ✓

Overall: <total>/30  (<pct>%)

Spec exported to: ./<AGENT_NAME>_spec.json
Handoff written to: ./<AGENT_NAME>_handoff.json
```

---

## Step 7.6: Eval skill handoff offer

Present the next-steps menu:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
What would you like to do next?

  [1] agent-flag-tester
      Compare model variants (current_sonnet vs openai_heavy vs fast_agent — resolve from the model table)
      and conditional flag variants (VQR, unrestricted chart) side-by-side.
      Best when: you want to find the right model/config tradeoff
      before committing to a final configuration.
      → Invoke: paste agent-flag-tester skill prompt
        handoff.json will be auto-detected in current directory.

  [2] cortex-agent-optimization
      Iterative instruction improvement loop with DEV/TEST split,
      accept/reject gates, and multi-run statistical scoring.
      Best when: smoke tests pass but you want to push accuracy higher
      or tune tool routing for edge-case questions.
      → Invoke: paste cortex-agent-optimization skill prompt

  [3] Bundled evaluate-cortex-agent + dataset-curation
      Formal scored evaluation with a ground-truth dataset.
      EXECUTE_AI_EVALUATION with answer_correctness +
      logical_consistency metrics. Results in Snowsight.
      Best when: you need a rigorous, reproducible benchmark
      (e.g., before a production launch or customer demo).
      → Invoke: bundled cortex-agent skill → EVALUATE intent

  [4] Done — agent is live
      No further evaluation. Agent is accessible in
      Snowflake Intelligence as "<display_name>".

  [5] Fix a smoke test failure
      Return to Phase 3 (instructions) or Phase 2 (tool descriptions)
      based on the failure type identified above.

   [6] CI/CD deployment pipeline + versioning
       Set up automated deployment from a Git-tracked spec file.
       GitHub Actions / GitLab CI / Azure Pipelines with OIDC auth,
       environment promotion (DEV → TEST → PROD), rollback, and
       drift detection.
       Includes agent versioning: commit live → alias 'production' →
       rollback by reassigning the alias. See agent-versioning.md.
       Best when: you want to deploy this agent across environments
       from a CI/CD pipeline instead of manual SQL execution.
       → Proceeds to Phase 8; see reference/agent-versioning.md for
         version SQL commands
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Recommended path based on smoke test score:
- Score ≥ 80%: Options [1], [2], [4], or [6] are all reasonable
- Score 60-79%: Recommend [5] first, then [2]
- Score < 60%: Recommend [5] — don't run evals on a broken agent

Wait for user selection. If [4], proceed to Step 7.7. If [6], load `phases/08_cicd_deploy.md`. Otherwise, surface the appropriate skill prompt or return to the indicated phase.

---

## Step 7.7: Session wrap-up

```
Agent <AGENT_NAME> is live.

Summary:
  FQN:          <AGENT_FQN>
  Model:        <AGENT_MODEL>
  Tools:        <N> — <tool names>
  Profile:      "<display_name>"
  Smoke score:  <pct>%
  Grants:       <roles or "none yet">
  Spec export:  <SPEC_EXPORT_PATH>
  Handoff file: ./<AGENT_NAME>_handoff.json

Find it in Snowflake Intelligence under "<display_name>".
```



---

## Output variables (terminal)

| Variable | Contents |
|----------|----------|
| `SPEC_EXPORT_PATH` | Local path to saved spec JSON |
| `HANDOFF_PATH` | Local path to handoff.json |
| `SMOKE_TEST_RESULTS` | List of question/score/status dicts |
