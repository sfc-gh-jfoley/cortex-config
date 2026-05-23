---
name: spec-implement
version: "1.13.0"
description: "Orchestrate implementation from accepted specs — generate stubs, dispatch domain agents, validate artifacts"
---

# spec-implement

Orchestrates code generation from an accepted spec. Generates file stubs in `impl/`, dispatches domain-specific agents in dependency order, validates outputs, and tracks artifact status through `.specbuilder/impl-status.json`.

## Tool Permissions

Read, Write, Edit, Bash, ask_user_question

## Prerequisite

The spec **status** MUST be `accepted` (check frontmatter `status` field). If it is `draft` or `in-review`, STOP and ask the user to accept the spec first via `spec-verify` sign-off.

**Hard gate:** If `spec/modules/` does not exist or is empty, STOP. The project needs scaffolding and a spec module before implementation can begin. Route the user to `spec-scaffold` then `spec-generate`.

## Step 1: Generate stubs and dispatch plan

```bash
python3 -m specbuilder implement <module_num>
```

Produces:
- `impl/<artifact-path>` — file stubs at their final locations (under the output directory)
- `.specbuilder/impl-status.json` — artifact inventory with status tracking
- `.specbuilder/dispatch.json` — batched execution plan with dependency ordering

The `impl/` directory is the default output root. Paths in the spec's `## Output` section are relative within it. For example, if the spec says `sql/tables/users.sql`, the file lands at `impl/sql/tables/users.sql`.

## Step 2: Review stubs with user

Present generated stubs and the dispatch plan. Confirm artifact list and execution order before proceeding. The user may request path or ordering changes.

## Step 3: Execute batches (parallel within batch)

Read `.specbuilder/dispatch.json`. For each batch in `execution_order`:

1. Check `"parallel": true` on the batch (all same-batch artifacts are independent)
2. For each artifact in the batch, **construct the agent prompt**:
   a. Read the domain template from `specbuilder/src/agents/templates/<artifact.template>`
   b. Append `## Artifact Assignment` block:
      - path: `<artifact path from dispatch.json>`
      - type: `<artifact type>`
      - description: `<artifact description>`
      - depends_on: `<list of dependency paths>`
   c. Append `## Spec Context` block containing these sections from the spec:
      - Executive Summary
      - Inputs
      - Output (full section, so agent sees sibling artifacts)
      - Edge Cases
      - Relevant acceptance criteria (ACs that reference this artifact's path or type)
   d. Replace all `<ARTIFACT_PATH>` placeholders in the template with the actual artifact path
3. Spawn one Task agent per artifact concurrently:
   - Use `run_in_background=true` and `team_name` for parallel execution
   - Each agent's prompt is the constructed template from step 2
   - Each agent writes the completed artifact to `impl/<path>` (replacing stub)
4. Barrier: wait for ALL agents in the current batch to complete
5. Reconcile status files into manifest:
   ```bash
   python3 -c "from specbuilder.src.workspace import reconcile_status_files; from pathlib import Path; reconcile_status_files(Path('.specbuilder'))"
   ```
6. **Verify batch before proceeding:**
   ```bash
   python3 -m specbuilder implement <module_num> --validate-only
   ```
   - If validation fails: fix the artifact, re-validate until clean
   - Do NOT proceed to the next batch with failing artifacts — errors compound downstream
   - For dependent batches, this is critical: the next batch builds on this one's output
7. Check for failures — if any artifact has status `failed` after retry:
   - Run `skip_dependents()` for downstream artifacts
   - Continue with remaining independent artifacts in next batch
8. Proceed to next batch

**CRITICAL:** After each batch, run `--validate-only` and confirm zero failures before proceeding to the next batch. Errors compound downstream — fix first, then continue.

**Fallback (single artifact in batch):** If a batch has only one artifact, implement it directly without spawning a background agent — the overhead isn't worth it.

**Concurrency cap**: Defined by `MAX_CONCURRENT_AGENTS` in `specbuilder/src/config.py` (default: 0, unlimited — defers to CoCo's native agent limits). If a batch contains more artifacts than the cap, and the cap is set to a non-zero value:
1. Sub-divide the batch into groups of `MAX_CONCURRENT_AGENTS` (preserving domain-priority ordering from dispatch.json)
2. Execute each sub-group sequentially (barrier between sub-groups)
3. All sub-groups within the same batch share the same reconciliation step

Example (cap=4): A batch with 7 artifacts becomes [4] → barrier → [3] → reconcile.

**IMPORTANT — manifest write isolation**: Agents must NEVER call `update_artifact_status()` directly. This function performs a read-modify-write on `impl-status.json` which races during parallel execution. Agents must ONLY use `write_artifact_status()` which writes to isolated `.specbuilder/.status/<slug>.json` files. The orchestrator calls `reconcile_status_files()` at batch barriers to merge status into the manifest atomically.

**Timeout handling (detailed):**

An agent is considered "stuck" when ALL of the following are true:
1. All other agents in the same batch have completed (success or failure)
2. The agent has produced no new output for 90 seconds (check via `agent_output`)
3. The agent's `.status/` file still shows `in_progress` or doesn't exist

When an agent is stuck:
1. Terminate it (kill the background agent)
2. Write timeout status:
   ```bash
   python3 -c "from specbuilder.src.workspace import write_artifact_status; from pathlib import Path; write_artifact_status(Path('.specbuilder'), '<path>', 'failed', error='Agent timed out — no progress after 90s')"
   ```
3. Proceed to retry (see below)

**Retry policy:**

Failed artifacts (whether from error or timeout) get ONE retry before being permanently marked as failed:

1. On first failure: re-spawn the agent with the same prompt
2. On second failure: mark as permanently failed, run `skip_dependents()`
3. Log both attempts in the reconciliation summary

Retry agents are spawned individually (not in parallel with other retries) to isolate failure causes. Retries happen BEFORE moving to the next batch — they are part of the current batch's execution.

## Step 4: Validate

```bash
python3 -m specbuilder implement <module_num> --validate-only
```

Fix any failures and re-validate until clean.

## Step 5: Report status

```bash
python3 -m specbuilder implement --status
```

Present summary (implemented / failed / skipped counts) to the user.

## Implementation Rules

- **Outputs are code artifacts, not side effects:**
  - SQL → `.sql` files; Python → `.py` files; Config → `.yaml`/`.json`
- Do NOT execute DDL/DML unless user explicitly says "execute this"
- Use project's detected package manager for dependencies
- Spec is source of truth — do NOT over-engineer beyond what it requires
- All output files land under `impl/` by default (configurable via `DEFAULT_IMPL_DIR` in config.py)

## Checkpoint Protocol (batches of 3+ proposals)

For batch implementation of 3+ proposals, read `specbuilder/refs/checkpoint-protocol.md` for the full resumption protocol.

## Synthetic Data Pattern

When a spec requires seed/demo data, follow the pattern in the relevant domain template (e.g., `data-engineering.md` requires Snowflake `GENERATOR()` — never row-by-row INSERT VALUES). Write seed files to `impl/sql/seed/` as `.sql` files; do not execute directly.
