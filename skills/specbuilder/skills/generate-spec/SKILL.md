---
name: generate-spec
version: "1.17.1"
description: "Guide users through intake clarification and generate spec modules with acceptance criteria"
triggers:
  - new module
  - spec intake
  - I need a feature
---

# Generate Spec

Converts user requirements into formal spec modules through structured clarification and generation. Ensures all ambiguity is resolved before producing SCHEMA.md-compliant spec files with acceptance criteria.

## Tool Permissions

Read, Write, Edit, Bash, ask_user_question

## Stopping Points

- ⚠️ **STOP — Phase 2 complete:** Wait for explicit user acceptance ("approved", "looks good", "accept") before any implementation steps. Do NOT write code, create stubs, or execute scripts. If user said "build X", split into two gated interactions: spec first, implementation only after acceptance.

## Output

- `spec/modules/NN-<slug>.md` — spec module file
- `spec/acceptance-criteria/NN-<slug>.md` — AC file
- Updated `spec/manifest.json` and `spec/README.md` (via `generate-manifest` + `sync-ac-files`)

## Plan Mode Integration

Use CoCo plan mode for Phases 1-2. Enter plan mode to explore and gather context.

| CoCo Plan Mode Step | SpecBuilder Phase |
|---------------------|-------------------|
| Explore (read files, understand context) | Phase 1: Intake & Clarification |
| Design (draft the plan) | Phase 2: Draft spec content |
| Present plan for confirmation | Phase 2: Present spec for review |
| User confirms plan | Spec status -> `accepted` |
| Exit plan mode, execute | Implementation begins (separate skill) |

**Critical rule:** When user confirms plan, MUST write spec file to `spec/modules/NN-slug.md` and AC file to `spec/acceptance-criteria/NN-slug.md` BEFORE any implementation begins.

> _Requires PYTHONPATH set per the orchestrator's Runtime Environment section. If invoking this sub-skill directly (not via the orchestrator), run the detection loop first._

## Phase 1: Intake & Clarification

**Goal**: Fully understand the requirement before writing anything.

1. **Read the requirement.** Check `spec/INTAKE.md` for a filled form, or treat chat description as intake.
   > ⚠️ `spec/INTAKE.md` is **read-only input.** Do not write to or modify it at any point
   > in this skill. The only outputs of generate-spec are `spec/modules/`, `spec/acceptance-
   > criteria/`, `spec/manifest.json`, and `spec/README.md`.
2. **Check environment section.** If INTAKE.md has an "Existing Environment" section with
   declared objects AND a Snowflake connection is available, validate declared objects
   exist and retrieve metadata. Cache results to `.specbuilder/environment.json`.
   If no connection, skip — section is accepted as-is.
3. **Run skill discovery:**
    ```bash
    python3 -m specbuilder discover-skills "<paste intake title and description here>"
    ```
   If the command fails or returns no output, skip this step — skill discovery is advisory
   and does not block intake.
   Identifies relevant CoCo skills (e.g., `semantic-view`, `dynamic-tables`, `snowpark-python`).
4. **Assess clarity** across these dimensions:
   - Inputs (data sources, formats, fields)
   - Output (format, structure, delivery)
   - Business rules (explicit or implied)
   - Acceptance criteria (measurable/testable)
   - Edge cases (unconsidered scenarios)
   - Dependencies (external packages needed)
   - Delivery format (scripts for review vs. direct execution)
5. **Ask 2-5 targeted clarifying questions** using `ask_user_question`:
   - Include skill-informed questions from discovery results
   - Ask about priority: must-have vs. nice-to-have for v1
   - If external packages needed, ask which and why
   - If SQL/infrastructure involved, ask: scripts for review or execute directly?
6. **Do NOT proceed** until ambiguities are resolved. One more question is better than a wrong assumption.

## Phase 2: Spec Generation

**Goal**: Produce a reviewable spec and acceptance criteria per SCHEMA.md.

All generated files MUST go in `spec/`. Never create spec files in root, `docs/`, or elsewhere.

1. **Determine next module number.** Check existing `spec/modules/NN-*.md`, pick next sequential (zero-padded).
2. **Generate spec module** at `spec/modules/NN-slug.md`:
   - YAML frontmatter: `id` (format: `MOD-NN`, e.g. `MOD-01`), `title`, `status: draft`, `version: "0.1.0"`, `last_updated`
   - Sections: Executive Summary, Inputs, Output, Acceptance Criteria, Edge Cases
   - Output section MUST specify file paths and whether execution is manual/automated
3. **Generate AC file** at `spec/acceptance-criteria/NN-slug.md`:

   **Exact format (do NOT deviate — the validator rejects non-conforming files):**

   ```markdown
   ---
   id: AC-NN
   title: "AC — Module Title"
   status: draft
   version: "0.1.0"
   last_updated: YYYY-MM-DD
   spec_reference: "../modules/NN-slug.md"
   ---

   ## AC-1: Category Name

   Context line explaining what this group tests.

   | # | Criterion | Pass | Notes |
   |---|-----------|------|-------|
   | 1.1 | Specific testable criterion | ☐ | |
   | 1.2 | Another testable criterion | ☐ | |

   ## Sign-Off

   | Reviewer | Date | Result | Comments |
   |----------|------|--------|----------|
   | | | ☐ Pass / ☐ Fail | |
   ```

   **Rules:**
   - Table MUST have exactly 4 columns: `#`, `Criterion`, `Pass`, `Notes`
   - Do NOT use Given/When/Then (BDD) format
   - Do NOT rename columns or add extra columns
   - Each criterion is a single self-contained sentence (implicitly covers: conditions, action, expected result)
   - `Pass` column always contains `☐` (unchecked)
   - At least one `## AC-N:` section required
   - `## Sign-Off` section required at the end
4. **Regenerate index:**
   ```bash
   python3 -m specbuilder generate-manifest && python3 -m specbuilder sync-ac-files
   ```
   > **`generate-manifest` operations (3 per invocation):**
   >
   > 1. **Frontmatter validation** — validates ALL spec files project-wide before writing
   >    anything. If any file has malformed frontmatter, `generate-manifest` exits with code 1
   >    and writes **nothing** (no manifest, no README).
   >    ⚠️ **If `generate-manifest` exits with an error**, run:
   >    ```
   >    python3 -m specbuilder audit
   >    ```
   >    to identify the malformed frontmatter field, fix it, then re-run `generate-manifest`.
   > 2. **Writes `spec/manifest.json`** (prints: `Generated spec/manifest.json`).
   > 3. **Writes `spec/README.md` module/proposal tables** (prints: `Regenerated spec/README.md`).
   >
    > Additionally, `sync-ac-files`:
    >
    > 4. **Syncs `spec/acceptance-criteria/`** — creates missing AC files and appends missing
    >    sections. Does **not** rewrite AC file `version` fields. Prints a count when
    >    changes are made; **fully silent on stable repos** (no "Updated 0" output).
    >
    > ⚠️ **If `sync-ac-files` exits with an error:** run `python3 -m specbuilder audit`,
    > fix any malformed AC files, then re-run `sync-ac-files`.
   Do NOT manually edit `spec/README.md` — it is fully managed by this command.

> **Note:** `write_module()` already calls `generate-manifest` and `sync-ac-files` internally on success.
> Step 4 is only needed if `write_module()` itself failed after writing the spec file (manifest regeneration failure).
5. **Present spec for review.** Explain what was generated, ask for feedback, iterate until satisfied.

---

> ⚠️ **STOP — Phase 2 complete.** Wait for explicit user acceptance ("approved", "looks good", "accept") before any implementation steps. Do NOT:
> - Write implementation code or SQL artifacts
> - Create file stubs or execute scripts
> - Continue to implementation in the same turn
>
> If user said "build X", split into two gated interactions: spec first, implementation only after acceptance.

> **Before writing files:** Once the user has confirmed the spec (see STOP above), create
> the acceptance gate sentinel:
> ```bash
> echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > .specbuilder/gate-open
> ```
> `write_module()` requires this file to exist with a current UTC timestamp and raises
> `RuntimeError` if it is absent or the timestamp is older than 30 minutes.
> The sentinel is a one-time token: it is automatically deleted after a successful write
> (see `generate_module.py:984`). Recreate it if you need to invoke `generate-module`
> again in the same session.
>
> **After `write_module()` succeeds:** The spec file is written with `status: draft`. Edit
> the spec frontmatter to set `status: in-review`, then re-run `generate-manifest`:
> ```bash
> python3 -m specbuilder generate-manifest
> ```
>
> **Recovery (partial-write failure):** If `generate-module` exits with an error after
> writing the spec file but before completing the AC file, the sentinel will still be
> present in `.specbuilder/`. In that case:
> 1. The spec file is automatically removed by the rollback handler — no manual deletion needed.
> 2. **Keep** `.specbuilder/gate-open` — the spec write succeeded so the gate remains valid.
> 3. Re-run generation to retry the AC file write. The existing sentinel will be consumed.
>
> **Recovery (spec-write failure):** If the spec file write itself fails, the sentinel **is**
> deleted by the failure handler (`generate_module.py:938`). Re-create it before retrying:
> `echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > .specbuilder/gate-open`

## CLI Reference

```
python3 -m specbuilder generate-module [file] [OPTIONS]
```

| Flag | Description |
|------|-------------|
| `file` | Path to intake file (positional). Reads stdin if omitted. |
| `--project-root PATH` | Project root directory (auto-detected if omitted). |
| `--template TEMPLATE` | Domain template to use (e.g., `data-pipeline`, `streamlit-app`, `security-policy`). |
| `--list-templates` | List available domain templates and exit. |
| `--suggest-template` | Suggest a template based on intake content and exit. |
| `--recommendations PATH` | Path to JSON file with skill recommendations. |

## Quality Gate

After authoring acceptance criteria, run the quality check:

```bash
python3 -m specbuilder quality spec/modules/NN-slug.md
```

Run the quality check against the spec module (not the AC file) — all 8 checks inspect sections (`## Acceptance Criteria`, `## Edge Cases`, `## Inputs`, `## Output`) that exist only in `spec/modules/`.

The check runs 8 quality checks from the registry:
`vague_criteria`, `testability`, `edge_case_sufficiency`,
`input_completeness`, `output_specificity`, `ac_coverage_of_outputs`,
`edge_case_traceability`, `input_output_traceability`.

**Profile override**: Set `SPECBUILDER_QUALITY_PROFILE` environment variable as the highest-priority override (takes precedence over `.specbuilder.toml`).

**Built-in profiles**:
- `poc` (threshold 50, skips `testability` and `edge_case_traceability`)
- `prototype` (threshold 50, skips `testability` and `edge_case_traceability`; `validation_tier: compile`, no self-correction — set via `SPECBUILDER_QUALITY_PROFILE=prototype` or `.specbuilder.toml`)
- `full` (threshold 75, no skips) — default
- `strict` (threshold 90, no skips)

> **Blocking behaviour (as of 1.17.0):** Under `full` and `strict` profiles, specs that score below the profile threshold are **blocked** — `write_module()` returns an error dict (`{"error": "quality_below_threshold", ...}`) and the spec file is **not written**. Warn-only behaviour no longer applies to these profiles. To bypass, switch to `poc` or `prototype` profile temporarily, or improve the spec until it meets the threshold.

## Operating Modes

Modes are **not** CLI flags. Activation is via `detect_mode()` reading `.specbuilder.toml`
(`[project] mode = "<mode>"`) or project sentinel files (`spec/.poc`, etc.).

| Mode | Activation | AC generated | Status in spec | Notes |
|------|-----------|--------------|----------------|-------|
| Default | (none — no mode set) | Yes | `draft` | Standard path |
| Strict | `.specbuilder.toml`: `[quality] profile = "strict"` or `SPECBUILDER_QUALITY_PROFILE=strict` | Yes | `draft` | Extra validation gates; threshold 90 |
| POC + Handover | `spec/.poc` + `.specbuilder.toml`: `[project].handover = true` | Yes | `accepted` | Auto-accepts spec on write; runs handover generation on sign-off |
| Prototype | `.specbuilder.toml`: `[project] mode = "prototype"` or `SPECBUILDER_QUALITY_PROFILE=prototype` | Yes | `draft` | `validation_tier: compile`, no self-correction; threshold 50 |
| POC | `spec/.poc` sentinel present or `.specbuilder.toml`: `[project] mode = "poc"` | Yes | `accepted` | Auto-accepts spec on write |

**Programmatic callers note:** When `write_module()` runs in lite mode (detected internally
via the presence/absence of `spec/acceptance-criteria/` in the project root), the return dict
contains `ac_path=None`. Callers must treat `None` as a deliberate skip, not an error. No
exception is raised and no warning is printed. `is_lite` is not a public parameter — lite
behavior is detected via the presence/absence of `spec/acceptance-criteria/` in the project root.

### POC Mode details

**Orchestrator handoff:** In POC mode, the orchestrator routes here via fast path (no manifest read, no governance context). Proceed directly to collapsed flow.

When `is_poc_mode()` returns True (detected via `spec/.poc` sentinel or `.specbuilder.toml` mode):

- **Collapsed flow**: Intake + spec generation happen in a single interaction (no separate phases)
- **Clarification**: Skip clarification cycle if intake contains explicit targets (schema refs, source tables, SLAs). If ambiguous, ask ONE round of questions only (not a loop)
- **Acceptance**: Implicit on user confirmation ("looks good", "yes", "approved") — no separate acceptance phase with multi-status transitions. Status goes directly from draft → accepted.
- **Quality gate**: Uses `poc` profile (threshold: 50, `testability` and `edge_case_traceability` checks skipped)
