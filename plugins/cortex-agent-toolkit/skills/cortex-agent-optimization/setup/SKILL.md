---
name: cortex-agent-optimization-setup
description: "Scaffold an optimization project for a Cortex Agent."
parent_skill: cortex-agent-optimization
---

## Step 1: Discover Agent and Workspace

**Check for existing project:** If `<WORKSPACE_ROOT>/<AGENT_DIR>/agent/` directory already exists, warn the user that a project has been scaffolded. Ask whether to re-scaffold (overwrite) or skip to a specific step.

Collect parameters from the user:
- Agent fully-qualified name (`<DATABASE>.<SCHEMA>.<AGENT_NAME>`)
- Snowflake connection name (`<CONNECTION>`)
- CLI tool for SQL execution (`<CLI_TOOL>`, default: `snow`)
- Execution mode (`<EXECUTION_MODE>`: `supervised` or `autonomous`, default: `supervised`)
- **Workspace directory (`<WORKSPACE_ROOT>`, required)** — prompt: "Where should I create the optimization project?" No default to CWD.
- **Runs per split (`<RUNS_PER_SPLIT>`)** — number of eval runs per split per iteration. After detecting the eval table (or creating it), count the DEV and TEST question counts and recommend based on dataset size:
  - < 20 questions → recommend 6
  - 20–50 questions → recommend 4
  - 50–100 questions → recommend 3 (default)
  - \> 100 questions → 3 is sufficient
  Present the question counts and recommendation; user may override.

**Validate workspace:** Ensure `<WORKSPACE_ROOT>` is NOT inside the skill directory.

**Detect workspace mode:**
- If `<WORKSPACE_ROOT>/scripts/build_agent_spec.py` exists → multi-agent workspace detected
  - Ask for agent subdirectory name (`<AGENT_DIR>`, default: lowercase `<AGENT_NAME>`)
  - Set `<WORKSPACE_TYPE>` = `"multi"`
- Otherwise → single-agent project
  - Set `<AGENT_DIR>` = `.`
  - Set `<WORKSPACE_TYPE>` = `"single"`

Retrieve the agent spec using the CLI (not SQL — `DESCRIBE AGENT` output is often too large for the SQL execution tool):
```bash
cortex agents describe <AGENT_FQN>
```
If `cortex agents describe` is unavailable, fall back to:
```bash
snow sql -c <CONNECTION> -q "DESCRIBE AGENT <AGENT_FQN>" --format json
```
Extract current instructions and tool configuration from the spec output.

**Detect existing datasets:** Run `SHOW DATASETS IN SCHEMA <DATABASE>.<SCHEMA>`. If datasets matching `<AGENT_NAME>` exist (e.g., `<AGENT_NAME>_dev_ds_v2`), reuse their names. Otherwise default to:
- `<DEV_DATASET_NAME>`: `<AGENT_NAME>_dev_ds_v1`
- `<TEST_DATASET_NAME>`: `<AGENT_NAME>_test_ds_v1`

**⚠️ STOP**: Present extracted agent details (instructions summary, tools list, model config) and workspace setup to the user for confirmation.

## Step 2: Create Source-of-Truth Directory

Create `<WORKSPACE_ROOT>/<AGENT_DIR>/agent/` directory with markdown files extracted from the current spec:
- `orchestration_instructions.md` — from `spec.instructions.orchestration`
- `response_instructions.md` — from `spec.instructions.response`
- `tool_descriptions.md` — from `spec.tools[].tool_spec.description` (one `## Tool: <name>` section per tool)
- `spec_base.json` — everything except instructions and tool descriptions (models, budget, tool types, tool_resources)

Snapshot the baseline: copy all `agent/*.md` and `agent/spec_base.json` to `<WORKSPACE_ROOT>/<AGENT_DIR>/snapshots/baseline/`.

## Step 3: Create Build Script

**If multi-agent workspace and `<WORKSPACE_ROOT>/scripts/build_agent_spec.py` exists, skip creation** (reuse shared script).

Otherwise, create `<WORKSPACE_ROOT>/scripts/build_agent_spec.py` that:
- For single-agent: Reads `<WORKSPACE_ROOT>/agent/*.md` files and `<WORKSPACE_ROOT>/agent/spec_base.json`
- For multi-agent: Reads agent-specific paths from `metadata.yaml`
- Strips HTML comments and top-level headings from markdown
- Parses `tool_descriptions.md` into per-tool description strings (split on `## Tool: <name>`)
- Assembles the full spec JSON
- Generates `ALTER AGENT <AGENT_FQN> MODIFY LIVE VERSION SET SPECIFICATION = $$...$$;`
- Writes to `<WORKSPACE_ROOT>/<AGENT_DIR>/deploy.sql`
- Supports `--dry-run` (stdout) and `--json` (spec only) flags

The agent FQN should be configurable (constant at top of script or via `--agent` argument for multi-agent).

**Validation:** Refer to `references/agent-template/` for example template files. The skill repo also contains a `test-fixture-example/` directory (at the repo root) with a complete working validation setup including a build script.

## Step 4: Create Eval Data

Guide the user to create an evaluation table. Ask if they already have one or need to create it.

**Detect existing split values (REQUIRED FIRST STEP if table has data):**

If the eval table already exists and has data, run:
```sql
SELECT DISTINCT SPLIT 
FROM <EVAL_TABLE> 
WHERE SPLIT IS NOT NULL 
ORDER BY SPLIT;
```

Interpret results:

- **Exactly 2 distinct values returned:**
  Ask user: "Found split values '<VALUE1>' and '<VALUE2>'. Which is DEV and which is TEST?"
  Set `<DEV_SPLIT_VALUE>` and `<TEST_SPLIT_VALUE>` based on response.

- **0 or 1 values returned:** Complete split not detected (exactly 2 distinct values required).
  Ask user to choose split value convention:
  - Option A (default): `'TRAIN'` (DEV) / `'VALIDATION'` (TEST)
  - Option B: `'DEV'` (DEV) / `'TEST'` (TEST)
  - Option C: Custom values (user specifies)
  Set `<DEV_SPLIT_VALUE>` and `<TEST_SPLIT_VALUE>` accordingly.
  Proceed to split assignment (load `eval-data/SKILL.md` Create Split workflow).

- **3+ values returned:** ERROR
  Show: "Found invalid SPLIT values: [list values]. Eval table must have exactly 2 split values. Please fix and re-run."
  STOP - user must clean data.

**If creating new:** Generate SQL for the eval table (see `references/eval-setup.md` for schema). Guide the user to populate it with evaluation questions. Each row needs:
- `TEST_ID` — unique identifier
- `TEST_CATEGORY` — category for stratified analysis
- `INPUT_QUERY` — the question to ask the agent
- `GROUND_TRUTH` — `OBJECT_CONSTRUCT('ground_truth_invocations', PARSE_JSON('[...]'), 'ground_truth_output', '...')`
- `SPLIT` — `<DEV_SPLIT_VALUE>` (DEV) or `<TEST_SPLIT_VALUE>` (TEST)

**For advanced dataset creation options:**
- Production data extraction and annotation → See bundled `dataset-curation` skill (Option B)
- Agent Events Explorer (Streamlit UI) → See bundled `dataset-curation` skill, launches interactive browser for event annotation
- Format conversion from existing tables → See bundled `dataset-curation` skill (Option C)

Note: Bundled skill creates OBJECT-type GROUND_TRUTH columns; this skill uses OBJECT columns for ground truth. Ensure format compatibility.

For split assignment (~45% DEV, ~55% TEST, stratified by category), load `eval-data/SKILL.md` and run its Create Split workflow.

Create views for each split:
```sql
CREATE OR REPLACE VIEW <DATABASE>.<SCHEMA>.AGENT_EVAL_DEV AS
SELECT * FROM <EVAL_TABLE> WHERE SPLIT = '<DEV_SPLIT_VALUE>';

CREATE OR REPLACE VIEW <DATABASE>.<SCHEMA>.AGENT_EVAL_TEST AS
SELECT * FROM <EVAL_TABLE> WHERE SPLIT = '<TEST_SPLIT_VALUE>';
```

### Ground Truth Completeness Gate

**MANDATORY before proceeding to Step 5.** Run `eval-data/SKILL.md` Workflow E (Validate Ground Truth Completeness) against `<EVAL_TABLE>`. This checks that every question has a non-empty `ground_truth_output` in its GROUND_TRUTH JSON.

- If **PASS**: proceed to Step 5.
- If **HARD STOP**: list the questions with missing GT. The user must fill them before eval configs are created. Do NOT skip this — missing GT produces score 0 per question and silently corrupts all aggregate metrics.

**⚠️ STOP**: Review eval questions, split distribution, and GT completeness with the user.

## Step 5: Create Eval Configs

Generate `<RUNS_PER_SPLIT>` YAML eval config files per split. Each file is identical to the template in `references/eval-setup.md` except for `dataset_name`. Show the full template for `_r1` and note "repeat for `_r2` through `_r<RUNS_PER_SPLIT>`":

- **`eval_config_dev_r1.yaml`**: `dataset_name: <DEV_DATASET_NAME>_r1`, points at `<DATABASE>.<SCHEMA>.AGENT_EVAL_DEV`.
- Repeat for `eval_config_dev_r2.yaml` through `eval_config_dev_r<RUNS_PER_SPLIT>.yaml`, incrementing only the `dataset_name` suffix.
- **`eval_config_test_r1.yaml`** through **`eval_config_test_r<RUNS_PER_SPLIT>.yaml`**: same pattern, pointing at `<DATABASE>.<SCHEMA>.AGENT_EVAL_TEST` with dataset names `<TEST_DATASET_NAME>_r1` through `_r<RUNS_PER_SPLIT>`.

Write all `2 × <RUNS_PER_SPLIT>` configs to `<WORKSPACE_ROOT>/<AGENT_DIR>/` locally. Ask the user for the stage path (`<STAGE_PATH>`), then upload all:
```sql
-- Repeat for each config file through r<RUNS_PER_SPLIT>, for both DEV and TEST
PUT 'file://<WORKSPACE_ROOT>/<AGENT_DIR>/eval_config_dev_r1.yaml' <STAGE_PATH>/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
PUT 'file://<WORKSPACE_ROOT>/<AGENT_DIR>/eval_config_test_r1.yaml' <STAGE_PATH>/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
```

## Step 6: Create Metadata and Log

Create `<WORKSPACE_ROOT>/<AGENT_DIR>/metadata.yaml`:
```yaml
database: <DATABASE>
schema: <SCHEMA>
name: <AGENT_NAME>
workspace_root: <WORKSPACE_ROOT>
workspace_type: <WORKSPACE_TYPE>
agent_dir: <AGENT_DIR>
connection: <CONNECTION>
cli_tool: <CLI_TOOL>
stage_path: <STAGE_PATH>
dev_dataset_name: <DEV_DATASET_NAME>
test_dataset_name: <TEST_DATASET_NAME>
eval_table: <EVAL_TABLE>
dev_split_value: <DEV_SPLIT_VALUE>
test_split_value: <TEST_SPLIT_VALUE>
execution_mode: <EXECUTION_MODE>
runs_per_split: <RUNS_PER_SPLIT>
```

Initialize `<WORKSPACE_ROOT>/<AGENT_DIR>/optimization_log.md`:
```markdown
# Optimization Log

**Agent:** <AGENT_FQN>
**Consecutive rejections:** 0

## Baseline

| Metric | DEV Mean (N=X) | DEV StdDev | TEST Mean (N=Y) | TEST StdDev | Combined Mean |
|--------|----------------|------------|-----------------|-------------|---------------|
```

## Step 7: Run Baseline Eval

Build and deploy current instructions to confirm the pipeline works:
```bash
python <WORKSPACE_ROOT>/scripts/build_agent_spec.py
<CLI_TOOL> sql --connection <CONNECTION> --filename <WORKSPACE_ROOT>/<AGENT_DIR>/deploy.sql
```

Run DEV eval `<RUNS_PER_SPLIT>` times in parallel. Fire all runs simultaneously, each using its own slot config:
```sql
-- Fire all simultaneously (do not wait between calls)
CALL EXECUTE_AI_EVALUATION(
  'START',
  OBJECT_CONSTRUCT('run_name', 'baseline_dev_r1'),
  '<STAGE_PATH>/eval_config_dev_r1.yaml'
);
-- Repeat immediately for r2 through r<RUNS_PER_SPLIT>, using eval_config_dev_r2.yaml etc.
```

Poll all runs in parallel using the parallel polling pattern from `references/eval-polling.md` until every slot reports completion.

If "Dataset version already exists" error occurs on a slot, wait 2-3 minutes and retry that slot. If persists 5+ min with no eval running on that slot, clear its stale lock per `references/eval-setup.md`. Other slots are unaffected.

Run TEST eval `<RUNS_PER_SPLIT>` times in parallel (`baseline_test_r1` through `baseline_test_r<RUNS_PER_SPLIT>`) using `eval_config_test_r1.yaml` through `eval_config_test_r<RUNS_PER_SPLIT>.yaml`. Poll all in parallel until all slots report completion.

Compute mean and stddev per metric across all `<RUNS_PER_SPLIT>` runs for each split: build a UNION ALL query with one SELECT block per run (`baseline_dev_r1` through `baseline_dev_r<RUNS_PER_SPLIT>`), GROUP BY METRIC_NAME, AVG + STDDEV of EVAL_AGG_SCORE. Run for both DEV and TEST. Record baseline scores in `optimization_log.md`.

**⚠️ STOP**: Present baseline scores (mean ± stddev for each split), confirm pipeline works end-to-end. The optimization project is now ready. Continue to `optimize/SKILL.md` for the first iteration.
