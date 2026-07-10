---
name: implement-spec
version: "1.17.1"
description: "Orchestrate implementation from accepted specs — generate stubs, dispatch domain agents, validate artifacts"
triggers:
  - implement
  - build it
  - generate stubs
---

# implement-spec

Orchestrates code generation from an accepted spec. Generates file stubs in `impl/`, dispatches domain-specific agents in dependency order, validates outputs, and tracks artifact status through `.specbuilder/impl-status.json`.

## Tool Permissions

Read, Write, Edit, Bash, ask_user_question, team_create, team_delete

## Stopping Points

- ⚠️ **PYTHONPATH required** — Before any `python3 -m specbuilder` command, set PYTHONPATH per the orchestrator's `## Runtime Environment` section. If loading this sub-skill directly (not via the orchestrator), run the detection loop first.
- ⚠️ **Spec must be `accepted` or `implemented`** — Check frontmatter status before proceeding. If `draft` or `in-review`, stop and ask user to accept the spec first. If `implemented`, treat as a re-implementation run — existing stubs are preserved and only missing artifacts are regenerated.
- ⚠️ **STOP — Stub Review Gate (after Step 1, before Step 3)** — Review generated stubs and the artifact execution order in `dispatch.json` before dispatching agents. Enforce with `python3 -m specbuilder implement <module_num> --stubs-only` (halts after stubs); then re-run with `--confirm` to dispatch. Skipping on a partially-complete module risks dispatching artifacts whose dependencies are still in progress. **Technical enforcement:** `implement()` writes `.specbuilder/.stub-review-pending` on every path except `--confirm`: plain `implement <module>` exits 3 (gate-blocked) and writes the sentinel; `--stubs-only` exits 0 and writes the sentinel. The `--confirm` path requires and deletes this sentinel before dispatch proceeds — the two-step sequence is mechanically enforced, not merely behavioral, for both `--stubs-only → --confirm` and plain `implement → --confirm` flows.
- ⚠️ **After stub review (Step 2)** — Confirm artifact list and execution order with user before spawning agents.

## Output

- `impl/<artifact-paths>` — file stubs at their final locations
- `.specbuilder/impl-status.json` — artifact inventory with status tracking
- `.specbuilder/dispatch.json` — batched execution plan with dependency ordering

**`impl-status.json` ownership:**

| Operation | Command / function |
|-----------|--------------------|
| Create / initial write | `generate_stubs()` — called by `implement <module>` (Step 1) |
| Per-artifact update (safe write path) | `write_artifact_status()` — agents write to `.specbuilder/.status/<slug>.json`; **never** call `update_artifact_status()` directly during parallel execution |
| Merge status files into manifest | `reconcile_status_files()` — called at each batch barrier in Step 3 |
| Read for validation | `prepare_validation()` — called by `implement <module> --validate-only` (Step 4) |

`checkpoint.py` does not read or write `impl-status.json`; its scope is proposal-batch tracking only.

## Prerequisites

Detect and export `PYTHONPATH` before running any `python3 -m specbuilder` command:

```bash
for d in .cortex/skills . vendor; do
  [ -d "$d/specbuilder" ] && export PYTHONPATH="$d:${PYTHONPATH:-}" && break
done
```

If the loop finds nothing, stop and tell the user SpecBuilder is not installed.

**Hard gate:** If `spec/modules/` does not exist or is empty, STOP. The project needs scaffolding and a spec module before implementation can begin. Route the user to `scaffold-spec` then `generate-spec`.

## Step 1: Generate stubs and dispatch plan *(CLI-invoked)*

```bash
python3 -m specbuilder implement <module_num>
```

**Flags:**

| Flag | Description |
|------|-------------|
| `--stubs-only` | Generate file stubs only — skip agent dispatch. Use to preview what artifacts will be created without running implementation agents. |
| `--validate-only` | Re-run validation against already-generated artifacts without re-generating them. |
| `--confirm` | Required after stub generation to confirm stub review before dispatch proceeds. Without this flag, `implement` exits with code 3 (gate-blocked). |

**Exit codes:**

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Validation failure |
| `2` | Usage error |
| `3` | Gate-blocked — awaiting stub review confirmation via `--confirm` |

Produces:
- `impl/<artifact-path>` — file stubs at their final locations (under the output directory)
- `.specbuilder/impl-status.json` — artifact inventory with status tracking
- `.specbuilder/dispatch.json` — batched execution plan with dependency ordering

The `impl/` directory is the default output root. Paths in the spec's `## Output` section are relative within it. For example, if the spec says `sql/tables/users.sql`, the file lands at `impl/sql/tables/users.sql`.

## Step 2: Review stubs with user *(CoCo-orchestrated)*

Present generated stubs and the dispatch plan. Confirm artifact list and execution order before proceeding. The user may request path or ordering changes. **This review applies regardless of batch size** — the single-artifact fallback (below) only affects how the artifact is executed, not whether it is reviewed.

**Note:** This gate is behavioral only — no sentinel or exit-code enforcement exists for the Step 2 user review. The `--stubs-only → --confirm` sentinel mechanism (see Stopping Points) enforces that stubs exist before dispatch; it does not enforce that the user has reviewed them. CoCo must not proceed to Step 3 without explicit user confirmation.

## Step 3: Execute batches (parallel within batch) *(CoCo-orchestrated)*


Read `.specbuilder/dispatch.json`. For each batch in `execution_order`:

1. Check `"parallel": true` on the batch (all same-batch artifacts are independent)
2. For each artifact in the batch, **construct the agent prompt**:
   a. Read the domain template from `specbuilder/src/agents/templates/<artifact.template>` (customer projects: `.cortex/skills/specbuilder/src/agents/templates/<artifact.template>`)
      Use the path root prepended to PYTHONPATH by the detection loop:
      `specbuilder/src/agents/templates/<artifact.template>` for dev repos,
      `.cortex/skills/specbuilder/src/agents/templates/<artifact.template>` for customer projects,
      or `vendor/specbuilder/src/agents/templates/<artifact.template>` for vendor installs.
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
    3d. Replace `<REASON>` in all dispatched agent stubs with the specific error or rejection reason before finalizing.
3. Spawn one Task agent per artifact concurrently:
    - **Before spawning:** Create the coordination team if it doesn't already exist:
      `team_create(team_name=IMPL_TEAM_NAME_FMT.format(module_num))` where `IMPL_TEAM_NAME_FMT = "specbuilder-impl-{:02d}"` is defined via the SpecBuilder skill configuration (e.g. `specbuilder-impl-03`). On retry, skip `team_create` if the team
      already exists.
    - Use `run_in_background=true` and `team_name=IMPL_TEAM_NAME_FMT.format(module_num)` for
      parallel execution
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
   - Run `skip_dependents()` for downstream artifacts:
     ```python
     python3 -c "
     from pathlib import Path
     from specbuilder.src.workspace import skip_dependents
     failed_artifact_path = '<artifact-path>'
     skipped = skip_dependents(Path('.specbuilder'), failed_artifact_path)
     print('Skipped:', skipped)
     "
     ```
     > **Note:** Cascades transitively through all downstream batches in `dispatch.json`, not just direct dependents (BFS traversal).
   - Continue with remaining independent artifacts in next batch
8. Proceed to next batch

**CRITICAL:** After each batch, run `--validate-only` and confirm zero failures before proceeding to the next batch. Errors compound downstream — fix first, then continue.

**Fallback (single artifact in batch):** If a batch has only one artifact, implement it directly without spawning a background agent — the overhead isn't worth it.

**Concurrency cap**: Defined by `MAX_CONCURRENT_AGENTS` via the SpecBuilder skill configuration (default: 0, unlimited — defers to CoCo's native agent limits). If a batch contains more artifacts than the cap, and the cap is set to a non-zero value:
1. Sub-divide the batch into groups of `MAX_CONCURRENT_AGENTS` (preserving domain-priority ordering from dispatch.json)
2. Execute each sub-group sequentially (barrier between sub-groups)
3. All sub-groups within the same batch share the same reconciliation step

Example (cap=4): A batch with 7 artifacts becomes [4] → barrier → [3] → reconcile.

**IMPORTANT — manifest write isolation**: Agents must NEVER call `update_artifact_status()` directly. This function performs a read-modify-write on `impl-status.json` which races during parallel execution. Agents must ONLY use `write_artifact_status()` which writes to isolated `.specbuilder/.status/<slug>.json` files. The orchestrator calls `reconcile_status_files()` at batch barriers to merge status into the manifest atomically.

### Quality Profile Fields

When `implement.py` generates `.specbuilder/dispatch.json`, it embeds the resolved
quality profile under the `quality_profile` key. Agents executing the dispatch plan
should respect these fields:

| Field | Effect on agent dispatch |
|-------|--------------------------| 
| `validation_tier` | Minimum validation depth to run on each artifact after implementation (`compile`, `dry-run`, `smoke-test`, `verify`) |
| `self_correct` | If `true`, the agent should attempt one self-correction pass when an artifact fails validation before marking it failed |
| `max_retries` | Maximum number of self-correction retry attempts (0 = no retries, 2 = up to two passes) |
| `prototype` profile | `validation_tier`: `compile`; `threshold`: 50; `skip_checks`: `[testability, edge_case_traceability]`; `max_retries`: 0. Intended for rapid prototyping where testability and edge-case traceability are deferred. (source: `config.py:216–221`) |

The profile is resolved once at `implement` invocation time using:
1. `SPECBUILDER_QUALITY_PROFILE` env var (highest priority)
2. `.specbuilder.toml [quality].profile`
3. `spec/.poc` sentinel (→ `poc` profile)
4. Default: `full`

> **Version note:** Only `compile` (Tier 1) is currently implemented. If `validation_tier` is
> set to `dry-run`, `smoke-test`, or `verify`, `implement --validate-only` prints a `Warning:`
> to stderr and runs Tier 1 compile checks only (`implement.py:146–152`). The field will be
> respected when Tiers 2–4 are implemented.

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

The number of retries is controlled by `quality_profile.max_retries` in `dispatch.json` (0 for `poc`/`full`/`prototype`, 2 for `strict`). Failed artifacts (whether from error or timeout) are retried up to `max_retries` times before being permanently marked as failed:

1. On first failure: re-spawn the agent with the same prompt
2. On second failure: mark as permanently failed, run `skip_dependents()`
3. Log both attempts in the reconciliation summary

Retry agents are spawned individually (not in parallel with other retries) to isolate failure causes. Retries happen BEFORE moving to the next batch — they are part of the current batch's execution.

The orchestrator tracks retry attempts via the `retry_count` field in `.specbuilder/.status/<slug>.json`. Pass the current count to `write_artifact_status(..., retry_count=N)` when re-spawning a failed agent.

**Conflict failures:** An artifact may be marked `failed` with error `"Conflict: target file exists and is not a stub"` — a non-stub file already occupies the target path. Conflict failures are **not retried automatically**; retrying would overwrite potentially valid work. Recovery: (1) inspect the target file; (2) if stale/incorrect, delete and re-run the batch; (3) if valid but path is wrong, update the spec's `## Output` section and re-run `python3 -m specbuilder implement <module_num>` to regenerate stubs with the corrected paths. Run `--validate-only` to confirm resolution before proceeding.

## Step 4: Validate *(CLI-invoked)*

```bash
python3 -m specbuilder implement <module_num> --validate-only
```

Fix any failures and re-validate until clean.

**After all batches validate clean:** Delete the coordination team:
`team_delete()` — relies on `CORTEX_TEAM_NAME` set by the preceding `team_create` call.

### Stale `specbuilder-impl-*` teams (interrupted batch recovery)

If a batch is interrupted, call `team_delete(specbuilder-impl-<N>)`, check
`.specbuilder/.status/` for partial writes, then re-run the batch from the current wave.

**Rebuild the manifest index:**

```bash
python3 -m specbuilder generate-manifest && python3 -m specbuilder sync-ac-files
```

⚠️ **STOP if `generate-manifest` exits non-zero** — a non-zero exit indicates a spec parse
error or a missing artifact referenced in the Output section. Do not proceed to Step 5. Run
`python3 -m specbuilder audit <module_num>` to identify the cause, then re-run the manifest
rebuild after resolving the error.

Rebuilds `spec/manifest.json` and `spec/README.md`, and syncs any new AC files. Omitting this causes manifest drift when multiple artifacts are generated in sequence.

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

## Status Transitions

Accepted input statuses for `implement-spec`:

| Status | Behaviour |
|--------|-----------|
| `accepted` | Normal implementation run — all stubs are generated and all batches are dispatched. |
| `implemented` | Re-implementation run — existing stubs are **preserved**; only missing artifacts are regenerated. Artifacts already marked `implemented` in `.specbuilder/impl-status.json` are skipped. |

If the status is `draft` or `in-review`, STOP. Do not proceed until the spec has been signed off via `verify-spec`.

## Checkpoint Protocol (2 or more proposals)

For batch implementation of 3+ proposals, read `specbuilder/refs/checkpoint-protocol.md` (customer projects: `.cortex/skills/specbuilder/refs/checkpoint-protocol.md`) for the full resumption protocol.

## Synthetic Data Pattern

When a spec requires seed/demo data, follow the pattern in the relevant domain template (e.g., `data-engineering.md` requires Snowflake `GENERATOR()` — never row-by-row INSERT VALUES). Write seed files to `impl/sql/seed/` as `.sql` files; do not execute directly.
