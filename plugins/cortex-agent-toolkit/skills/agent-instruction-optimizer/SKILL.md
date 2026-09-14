---
name: agent-instruction-optimizer
description: >
  DSPy MIPROv2 optimizer for Cortex Agent instructions. Implements Stanford's
  Multiprompt Instruction PRoposal Optimizer v2 (Khattab et al. 2023) for
  Snowflake Cortex Agents — jointly compiles instruction text and bootstrapped
  demonstrations using Tree-structured Parzen Estimator (TPE). A real surrogate
  model that builds KDE distributions over good/bad parameter regions and uses
  Expected Improvement acquisition to select the next (instruction, demo) program
  to evaluate. Faster and cheaper than full agent-optimizer.
  Slots between agent-model-tester and agent-optimizer in the lifecycle.
  Use when: DSPy, MIPROv2, MIPRo, compile instructions, bootstrap demonstrations,
  TPE, instruction optimization, tune instructions, prompt optimization, few-shot,
  instruction search, quick optimization.
triggers:
  - DSPy
  - MIPROv2
  - MIPRo
  - compile instructions
  - bootstrap demonstrations
  - instruction optimization
  - tune instructions
  - prompt optimization
  - TPE
  - instruction search
  - instruction variants
  - few-shot optimization
  - quick optimization
---

# DSPy Instruction Optimizer (MIPROv2)

Snowflake's implementation of Stanford's **MIPROv2** optimizer for Cortex Agents.
Treats the agent as a DSPy *program* and compiles it by jointly searching over
*instruction proposals* and *bootstrapped demonstrations* using **Tree-structured
Parzen Estimator (TPE)** — the same algorithm used in optuna and DSPy's default
Bayesian backend.

See `references/dspy-methodology.md` for the research background and how this
maps to the original DSPy framework.

**No structural mutations.** This skill compiles the prompt dimension only —
instruction text and few-shot demonstrations. If compilation plateaus, hand off to
`agent-optimizer` for structural work (VQRs, UDFs, dynamic tables).

## When to Use

- After `agent-model-tester` (model choice decided), before `agent-optimizer`
- Quick wins on a new agent before investing in the full optimization loop
- When instructions are the bottleneck (correct SV, correct model, but synthesis is off)
- Budget: ~20 eval calls total (n_trials × mini-batch)

## Prerequisites

- A deployed Cortex Agent with instruction files (orchestration_instructions.md,
  response_instructions.md, or equivalent)
- An eval dataset with DEV split (from `agent-evaluation` or `agent-optimizer` setup)
- Python 3.11+ with `optuna`, `PyYAML`
- `snow` CLI configured with connection

Read `metadata.yaml` for parameters if an optimization project exists. Otherwise,
ask for: `<DATABASE>`, `<SCHEMA>`, `<AGENT_NAME>`, `<EVAL_TABLE>`, `<CONNECTION>`.

---

## Configuration

| Parameter | Default | Range | Notes |
|---|---|---|---|
| n_trials | 20 | 5-30 | Total TPE trials (instruction × few-shot combos evaluated) |
| n_startup_trials | 5 | 3-8 | Random exploration before TPE surrogate kicks in |
| few_shot_k | 2 | 1-3 | Few-shot demos injected per candidate |
| instruction_pool_size | 12 | 8-16 | Instruction variants generated upfront |
| mini_batch_pct | 0.40 | 0.25-0.60 | Fraction of DEV questions per trial |

---

## Execution Mode

Follows the toolkit-wide mode contract (`../../references/gate-inventory.md`) inherited from
the router — do not re-prompt for mode if it was already set there.

- **INTERACTIVE** (default if mode can't be determined): The Step 3.2 coverage checkpoint and
  the Phase 6 `INSTROPT-WINNER-ACCEPT` gate are active. The user reviews and approves before
  proceeding.
- **AUTONOMOUS**:
  1. Step 3.2 (`INSTROPT-COVERAGE-CHECK`-adjacent judgment call): if every operator family has
     >= 1 variant, log `[AUTO-RESOLVED: INSTROPT-COVERAGE-CHECK → proceeded, all families covered]`
     and proceed. Missing coverage after one regeneration retry is a data-integrity condition —
     `[BLOCKER: INSTROPT-COVERAGE-CHECK: <family> could not be filled]` and hard-stop (both modes).
  2. Phase 6 apply/defer (`INSTROPT-WINNER-ACCEPT`): **this is a permanent OPERATOR_REQUIRED
     gate per the gate inventory — it does NOT auto-resolve in AUTONOMOUS mode.** Present the
     diff and wait for an explicit A/B/C/D choice exactly as in INTERACTIVE. The only thing
     AUTONOMOUS changes here is that `INSTROPT-SNAPSHOT` (see Phase 6) always fires automatically
     before any production write, in both modes.
  Data-integrity conditions (anti-pattern rejections in Step 3.1, missing operator coverage
  after a regeneration retry, Snowflake/API errors) still hard-stop in both modes.

---

## Phase 1: Baseline

### Step 1.1: Read Current Instructions

Read the agent's instruction files. Identify the instruction surface:
- `orchestration_instructions.md` — how the agent plans and uses tools
- `response_instructions.md` — how the agent formats and delivers answers
- Any inline instructions in the agent spec

If the agent was created via `agent-ddl`, these files are in
`<WORKSPACE_ROOT>/<AGENT_DIR>/agent/`. If not, extract from `DESCRIBE AGENT`.

### Step 1.2: Open Snowflake Run Record

Load DDL from `../../references/pattern-mining.md`. Create tables if not exist
and open the run record:

```sql
CREATE TABLE IF NOT EXISTS <DATABASE>.<SCHEMA>.<AGENT_NAME>_OPT_RUNS ( ... );
CREATE TABLE IF NOT EXISTS <DATABASE>.<SCHEMA>.<AGENT_NAME>_OPT_CANDIDATES ( ... );
CREATE TABLE IF NOT EXISTS <DATABASE>.<SCHEMA>.<AGENT_NAME>_QUESTION_MANIFEST ( ... );
-- Use full DDL from pattern-mining.md

INSERT INTO <DATABASE>.<SCHEMA>.<AGENT_NAME>_OPT_RUNS
    (run_id, optimizer_type, agent_fqn, baseline_score, status, started_at)
VALUES ('<run_id_uuid>', 'INSTRUCTION_TPE', '<DATABASE>.<SCHEMA>.<AGENT_NAME>',
        NULL, 'IN_PROGRESS', CURRENT_TIMESTAMP());
```

Generate `run_id` as a UUID. Also create the shared cross-agent table if
`opt_history_fqn` is set in `metadata.yaml`:

```sql
CREATE TABLE IF NOT EXISTS <META_DB>.<META_SCHEMA>.OPT_QUESTION_HISTORY ( ... );
```

### Step 1.3: Run Baseline Eval

If a recent baseline exists in `optimization_log.md` (within 24h, no agent changes),
reuse it. Otherwise run a fresh DEV eval using `EXECUTE_AI_EVALUATION` on the full
DEV split:

```sql
CALL EXECUTE_AI_EVALUATION('START',
  OBJECT_CONSTRUCT('run_name', 'instr_opt_baseline'),
  '<STAGE_PATH>/config_baseline.yaml');
```

Poll using `references/eval-polling.md` until COMPLETED. Insert per-question results
into `<AGENT_NAME>_QUESTION_MANIFEST` and `OPT_QUESTION_HISTORY` (if configured)
with `source='baseline'`.

### Step 1.4: Analyze Failures

Pull per-question scores and group by failure pattern:

```sql
SELECT INPUT, EVAL_AGG_SCORE, TEST_CATEGORY, METRIC_NAME
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
  '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>',
  'CORTEX AGENT', 'instr_opt_baseline'))
WHERE METRIC_NAME IS NOT NULL
ORDER BY EVAL_AGG_SCORE ASC;
```

Group failures by pattern (wrong numbers, wrong tool selection, bad formatting,
hallucination, routing failures). Write summary to
`<WORKSPACE_ROOT>/<AGENT_DIR>/failure_context.json`. This feeds mutation prompts
in Phase 3.

---

## Phase 2: Bootstrap Demonstrations

### Step 2.1: Bootstrap Trace Pool

Build the *demonstration pool* from baseline eval results — the DSPy equivalent
of bootstrapping labeled examples. No additional agent calls needed:

```bash
python scripts/collect_traces.py \
  --database <DATABASE> --schema <SCHEMA> \
  --eval-run instr_opt_baseline --agent <AGENT_NAME> \
  --min-score 0.75 --max-traces 20 \
  --output <WORKSPACE_ROOT>/<AGENT_DIR>/trace_pool.json
```

Returns `trace_pool.json` with up to 20 correctly-answered questions
(`input`, `expected_output`, `agent_response`, `category`). These become
few-shot demo candidates injected into instruction variants during TPE trials.

### Step 2.2: Review Trace Coverage

Present trace pool summary to user. Show count per category. Flag any category
with fewer than 2 traces — weak few-shot coverage for that category means TPE
may not find good demos for it.

---

## Phase 3: Propose Instructions

### Step 3.1: Propose Instruction Variants

Generate `instruction_pool.json` — 12 *instruction proposals* using diverse
mutation operators. This is the DSPy "propose" step: generate a discrete set of
candidate programs before searching. Load `references/mutation-templates.md` for the operator catalog.

```bash
python scripts/generate_candidates.py \
  --agent-dir <WORKSPACE_ROOT>/<AGENT_DIR>/agent/ \
  --failure-context <WORKSPACE_ROOT>/<AGENT_DIR>/failure_context.json \
  --pool-size 12 \
  --output <WORKSPACE_ROOT>/<AGENT_DIR>/instruction_pool.json
```

The script emits one prompt per operator slot. For each slot, CoCo generates
the instruction variant using that prompt + the failure context. Write the
generated text back for that slot.

**Anti-pattern checks** (reject and regenerate if detected):
- Variant is identical to parent (no-op mutation)
- Variant adds verbose checklists or step-by-step instructions for the LLM
- Variant modifies tool descriptions or tool routing logic
- Variant exceeds 2x the parent instruction length

### Step 3.2: STOP Gate — Operator Coverage Review

Present operator distribution to user. Require at least 1 variant per operator
family before proceeding:

| Operator Family | Examples | Min Required |
|---|---|---|
| routing | add_routing_rule, add_domain_rule | 1 |
| examples | add_worked_example, fix_example | 1 |
| formatting | compress_verbose, restructure_sections | 1 |
| retry/recovery | add_retry_logic | 1 |

Show a one-line diff summary per variant.

**INTERACTIVE:** Wait for user approval before proceeding.
**AUTONOMOUS:** If every operator family has >= 1 variant, log
`[AUTO-RESOLVED: INSTROPT-COVERAGE-CHECK → proceeded, all families covered]` and
proceed. If a family is missing, regenerate one variant for that family only (repeat Step
3.1's targeted generation) and re-check; if still missing after one retry, this is a
data-integrity condition — hard-stop and report which operator family could not be filled.

---

## Phase 4: TPE Compilation

Repeat Steps 4.1–4.7 until `tpe_suggest.py` returns `done=true`.

### Step 4.1: Get Next Trial from TPE

Initialize or resume the optuna TPE study:

```bash
python scripts/tpe_suggest.py \
  --instruction-pool <WORKSPACE_ROOT>/<AGENT_DIR>/instruction_pool.json \
  --trace-pool <WORKSPACE_ROOT>/<AGENT_DIR>/trace_pool.json \
  --study-db <WORKSPACE_ROOT>/<AGENT_DIR>/tpe_study.db \
  --agent-name <AGENT_NAME> \
  --few-shot-k 2 \
  --n-startup-trials 5
```

Returns JSON: `{"trial_number": N, "instruction_idx": 3, "fewshot_0": 7, "fewshot_1": 2, "done": false}`

If `done=true`: skip to Phase 5.

### Step 4.2: Build Candidate Spec

```bash
python scripts/build_candidate.py \
  --base-spec <WORKSPACE_ROOT>/<AGENT_DIR>/agent_spec.json \
  --instruction-pool <WORKSPACE_ROOT>/<AGENT_DIR>/instruction_pool.json \
  --trace-pool <WORKSPACE_ROOT>/<AGENT_DIR>/trace_pool.json \
  --instruction-idx <instruction_idx> \
  --fewshot-indices <fewshot_0>,<fewshot_1> \
  --output <WORKSPACE_ROOT>/<AGENT_DIR>/candidate_spec_<N>.json
```

Few-shot demos are injected as a `## Worked Examples` section appended to
`orchestration_instructions.md` in the candidate spec.

### Step 4.3: Deploy Candidate Agent

```sql
CREATE OR REPLACE AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>_INSTR_TPE_<N>
FROM SPECIFICATION $$<contents of candidate_spec_<N>.json>$$;
```

### Step 4.4: Sample Mini-Batch

Create a stratified batch view — proportional sample per TEST_CATEGORY, rotating
questions across trials to avoid overfitting to a fixed subset:

```sql
CREATE OR REPLACE VIEW <DATABASE>.<SCHEMA>.INSTR_OPT_BATCH_<N> AS
WITH category_counts AS (
    SELECT TEST_CATEGORY,
           GREATEST(1, CEIL(COUNT(*) * 0.40)) AS cat_sample_size
    FROM <DATABASE>.<SCHEMA>.<EVAL_TABLE>
    WHERE SPLIT = '<DEV_SPLIT_VALUE>'
    GROUP BY TEST_CATEGORY
),
ranked AS (
    SELECT t.*,
           ROW_NUMBER() OVER (
               PARTITION BY t.TEST_CATEGORY ORDER BY RANDOM(<N>)
           ) AS rn
    FROM <DATABASE>.<SCHEMA>.<EVAL_TABLE> t
    WHERE t.SPLIT = '<DEV_SPLIT_VALUE>'
)
SELECT r.*
FROM ranked r
JOIN category_counts c ON r.TEST_CATEGORY = c.TEST_CATEGORY
WHERE r.rn <= c.cat_sample_size;
```

The seed `RANDOM(<N>)` uses the trial number — different questions per trial,
reproducible on resume.

### Step 4.5: Run Eval on Candidate

Upload a YAML eval config pointing at `INSTR_OPT_BATCH_<N>`, then:

```sql
CALL EXECUTE_AI_EVALUATION('START',
  OBJECT_CONSTRUCT('run_name', 'instr_tpe_trial<N>'),
  '<STAGE_PATH>/config_instr_tpe_<N>.yaml');
```

Poll using `references/eval-polling.md` until COMPLETED.

### Step 4.6: Collect Score and Log

```sql
SELECT AVG(EVAL_AGG_SCORE) AS mean_score
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
  '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>_INSTR_TPE_<N>',
  'CORTEX AGENT', 'instr_tpe_trial<N>'))
WHERE METRIC_NAME = 'answer_correctness';
```

Insert per-question rows into `<AGENT_NAME>_QUESTION_MANIFEST` and
`OPT_QUESTION_HISTORY` with `source='tpe_trial'`, `run_label='trial_<N>'`
(see `../../references/pattern-mining.md` for INSERT pattern).

Insert candidate record:

```sql
INSERT INTO <DATABASE>.<SCHEMA>.<AGENT_NAME>_OPT_CANDIDATES
    (candidate_id, run_id, generation, operator, mean_score,
     delta_vs_baseline, accepted)
VALUES ('tpe_trial_<N>', '<run_id>', <N>, '<operator_for_instruction_idx>',
        <mean_score>, <mean_score> - <baseline_score>, FALSE);
```

### Step 4.7: Record Score and Clean Up

```bash
python scripts/tpe_record.py \
  --study-db <WORKSPACE_ROOT>/<AGENT_DIR>/tpe_study.db \
  --trial-number <N> \
  --score <mean_score>
```

Then drop trial artifacts:

```sql
DROP AGENT IF EXISTS <DATABASE>.<SCHEMA>.<AGENT_NAME>_INSTR_TPE_<N>;
DROP VIEW IF EXISTS <DATABASE>.<SCHEMA>.INSTR_OPT_BATCH_<N>;
```

Return to Step 4.1.

---

## Phase 5: Evaluate Compiled Program

### Step 5.1: Retrieve Best Trial

```bash
python scripts/tpe_suggest.py \
  --study-db <WORKSPACE_ROOT>/<AGENT_DIR>/tpe_study.db \
  --best-only
```

Returns: best `instruction_idx`, `fewshot_indices`, `score`.

### Step 5.2: Deploy Winner as Validation Candidate

Build the winning candidate spec (Step 4.2 with best indices). Deploy as a
disposable candidate — **not** the primary agent — so the full DEV/TEST eval
below runs against a copy, not production:

```sql
CREATE OR REPLACE AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>_INSTR_WINNER
FROM SPECIFICATION $$<winning_spec>$$;
```

### Step 5.3: Full DEV Eval

Run the full DEV split (all `RUNS_PER_SPLIT` runs from `metadata.yaml`) against
`<AGENT_NAME>_INSTR_WINNER`. Insert results into `<AGENT_NAME>_QUESTION_MANIFEST`
and `OPT_QUESTION_HISTORY` with `source='tpe_final'`.

### Step 5.4: Present Results Summary

```
Instruction Optimization Complete

  Baseline (DEV):  72.0%
  Winner (DEV):    78.5% (+6.5pp)

  Trials run: 20 (startup: 5, TPE-guided: 15)
  Winning operator: add_retry_logic
  Few-shot demos used: REVENUE (2 examples)

  Per-category improvement:
    REVENUE:    +12pp (3 questions fixed)
    CHURN:      +4pp  (1 question fixed)
    OPERATIONS: no change

  Regressions: 0
```

### Step 5.5: Update Run Record

```sql
UPDATE <DATABASE>.<SCHEMA>.<AGENT_NAME>_OPT_RUNS
SET final_score = <winner_score>,
    delta = <winner_score> - baseline_score,
    winner_operator = '<winning_operator>',
    generations_run = <N>,
    status = 'CONVERGED',
    ended_at = CURRENT_TIMESTAMP()
WHERE run_id = '<run_id>';
```

---

## Phase 6: Apply or Defer

The winner is still only deployed as `<AGENT_NAME>_INSTR_WINNER` at this point —
production has not been touched. This gate (`INSTROPT-WINNER-ACCEPT`) decides whether
it gets promoted, and it is a **permanent OPERATOR_REQUIRED gate — it always pauses,
in both INTERACTIVE and AUTONOMOUS mode.** Present the winning instruction diff
(validated DEV/TEST scores from Phase 5). Ask:

> "Apply these instructions to the production agent?
>  (A) Apply to production agent
>  (B) Save as snapshot for later review (snapshots/instr_opt_<DATE>/)
>  (C) Hand off to agent-optimizer for structural work
>      (winning instructions become the new starting point)
>  (D) Discard — update run status to BUDGET_EXHAUSTED"

Log the operator's decision: `[OPERATOR-DECISION: INSTROPT-WINNER-ACCEPT → <A/B/C/D>]`.

**If (A):** First snapshot the current production spec (rollback state, gate
`INSTROPT-SNAPSHOT` — `AUTO_REMEDIATE`, always fires with no prompt in either mode) —
save the live agent's current `agent/*.md` files and spec JSON to
`snapshots/instr_opt_<DATE>_pre_apply/`. Only then copy winning instructions to
`<WORKSPACE_ROOT>/<AGENT_DIR>/agent/`, build, and deploy to the primary agent:

```sql
CREATE OR REPLACE AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>
FROM SPECIFICATION $$<winning_spec>$$;
```

Update `OPT_CANDIDATES` `accepted=TRUE` for the winning trial.

**If (C):** Pass winning `orchestration_instructions.md` and `response_instructions.md`
as the new parent, along with `failure_context.json`, to `agent-optimizer`. Production
is not touched.

**Always:** `DROP AGENT IF EXISTS <AGENT_NAME>_INSTR_WINNER;` and remove
`instruction_pool.json`, `trace_pool.json`, `tpe_study.db`, and all
`candidate_spec_<N>.json` files from the workspace.

---

## Lifecycle Position

```
agent-model-tester (model choice)
  ↓
agent-instruction-optimizer  ← DSPy MIPROv2 compilation (THIS)
  ↓                            jointly compiles instruction proposals
                               + bootstrapped demonstrations via TPE
agent-optimizer (structural mutations + instruction refinement)
  ↓
agent-gepa-optimizer (GEPA — evolutionary population search)
```

This skill *compiles* the prompt dimension of the agent program. If compilation
converges below target accuracy, the remaining gap is structural (missing VQRs,
UDFs, dynamic tables) — hand off to the full optimization loop.

See `references/dspy-methodology.md` for the research background.
