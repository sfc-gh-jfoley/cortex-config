---
name: propose-spec
version: "1.17.1"
description: "Guide proposal authoring with pre-flight checks, validation, and impact analysis"
triggers:
  - propose
  - new proposal
  - write a proposal
  - EXT-
---

# Propose Spec

Guides the creation of architecture proposals (EXT-NNN files) with pre-flight validation, correct directory placement, schema compliance, and impact analysis against existing proposals and modules.

## Tool Permissions

Read, Write, Edit, Bash, ask_user_question

## Stopping Points

- ⚠️ **Pre-Flight step 0:** `spec/` directory is absent — STOP and route to scaffold-spec before writing any proposal.
- ⚠️ **Before writing the proposal file** — Confirm title, scope, and EXT number with the user before creating the file.
- ⚠️ **PYTHONPATH required** — Run the detection loop in `## Prerequisites` below before any `python3 -m specbuilder` command.
- ⚠️ **Scope-overlap gate** — If Pre-Flight step 3 finds an existing proposal with overlapping scope, STOP and ask: "EXT-NNN already covers similar scope. Should we extend that proposal or create a new one?" Do not write a new file until the user decides.
- ⚠️ **Batch EXT number confirmation** — When creating multiple proposals in a single session, STOP after determining the full EXT number range and confirm with the user before writing any files. This prevents number gaps and collisions.
- ⚠️ **`generate-manifest` failure** — If `generate-manifest` exits non-zero (frontmatter validation error, missing required fields): **STOP**. Run `python3 -m specbuilder audit` to identify the frontmatter issue. Do not proceed to proposal submission until `generate-manifest` exits 0.
- ⚠️ **Phase 4 impact-write failure** — If the `impacts_modules` frontmatter write fails (partial write, YAML parse error, permission error): **STOP**. Run `python3 -m specbuilder audit` to verify file integrity, then re-apply the frontmatter edit and re-run `generate-manifest` to confirm the field is accepted.

## Prerequisites

Set PYTHONPATH before any `python3 -m specbuilder` command:

```bash
for d in .cortex/skills . vendor; do
  [ -d "$d/specbuilder" ] && export PYTHONPATH="$d:${PYTHONPATH:-}" && break
done
```

If the loop finds nothing, stop and tell the user SpecBuilder is not installed.

## Output

- `spec/architecture/proposals/<NNN>-<slug>.md` — new proposal file (filename uses zero-padded number only; `EXT-` prefix belongs in the frontmatter `id` field, not the filename)
- Updated `spec/manifest.json` and `spec/README.md` (via `generate-manifest`)

## When to Run

- User wants to write a new proposal or extension, or references EXT-NNN creation
- The orchestrator routes here based on proposal-related intent
- **Requires a scaffolded project** — `spec/` must exist. If it doesn't, route to
  `scaffold-spec` first.

## Mode Awareness

- **poc / prototype**: Skip manifest title-skim in Pre-Flight step 3 (`spec/manifest.json` may not exist); `propose validate` optional; `check-overlap` still runs if manifest exists.
- **full** (default): All Pre-Flight steps apply; run `propose validate` after writing.
- **strict**: Run `propose validate` both before and after writing; `generate-manifest` must exit 0 before Phase 4.

## Pre-Flight (MANDATORY — before writing anything)

0. **Verify project is scaffolded.** Run:
   ```bash
   [ -d spec ] && echo "OK" || echo "MISSING"
   ```
   If the output is `MISSING`, **STOP**. Tell the user: "This project has no `spec/`
   directory. Run scaffold-spec to initialize the project before creating proposals."
   Do not proceed.

1. **Read placement rules.** Open `spec/architecture/SCHEMA.md` § "Directory Placement (Lifecycle)". Confirm:
   - Active proposals (`planned`, `in-progress`) → `spec/architecture/proposals/` root
   - Completed → `proposals/implemented/`
   - Shelved → `proposals/parked/`
   - **NEVER** create a `planned/` subdirectory

2. **Determine next EXT number.** Scan ALL proposals (root + `implemented/` + `parked/`):
   ```bash
   # Step 2a — discover the highest existing EXT number
   ls spec/architecture/proposals/*.md spec/architecture/proposals/implemented/*.md \
      spec/architecture/proposals/parked/*.md 2>/dev/null \
      | xargs -I{} basename {} | grep -oE '^[0-9]{3}' | sort -n | tail -1
   ```
   Next number = highest found + 1. Zero-pad to 3 digits. If the command produces no output (no proposals exist yet), the next number is `001`.

   Then verify the candidate is not already in use:
   ```bash
   # Step 2b — verify the proposed candidate EXT is not already in use
   python3 -m specbuilder propose check-collision \
       spec/architecture/proposals EXT-<NNN>
   ```
   If `check-collision` reports a collision, increment the candidate and re-check.

3. **Check for module-scope overlap.** Run `python3 -m specbuilder propose check-overlap spec/architecture/proposals <MOD-IDs...>` with the module IDs expected to appear in `impacts_modules`. If the command reports `OVERLAP: EXT-NNN`, read that proposal to determine whether the scopes conflict. If `spec/manifest.json` does not yet exist, skip this step.

   Additionally, skim existing proposal titles in `spec/manifest.json` for thematic overlap not captured by module IDs.

   If overlap is found:
   - Ask user: "EXT-NNN already covers similar scope. Should we extend that proposal or create a new one?"
   - If extending, route to editing the existing file instead

**Pre-Flight complete.** All checks passed — proceed to Phase 1.

## Phase 1: Intake & Clarification

**Goal**: Fully understand what's being proposed before writing the file.

1. **Clarify the problem.** What's broken or missing? Why does it matter?
2. **Clarify the solution.** What does this proposal enable?
3. **Define scope boundaries.** What's in? What's explicitly out?
4. **Identify dependencies.** Does this depend on other EXT-NNN proposals?
5. **Determine phase.** Which delivery phase does this belong to?

### Decision Gate: Module vs. Proposal

Before proceeding, assess whether this work belongs as a **proposal** or a **module**:

| Route to **generate-spec** (module) when ANY of: | Keep as **proposal** when ALL of: |
|--------------------------------------------------|-----------------------------------|
| Has structured inputs and outputs (data flows) | Infrastructure or tooling change |
| Requires formal ACs with sign-off | One-shot implementation (do it, verify, done) |
| Will produce multiple implementation artifacts | No formal sign-off needed |
| Has cross-module dependencies affecting architecture | Self-contained, doesn't alter module behavior |
| Requires ongoing maintenance | |
If the work is better suited as a module, **stop and route to generate-spec** instead of writing a proposal.

### Batch Mode: Intake Notes

For batch proposals (multiple at once):
- Determine ALL EXT numbers upfront to avoid gaps/collisions
- Establish dependency ordering between the batch members
- Ask: are these independent or do they form a dependency chain?

## Phase 2: Write Proposal File

**Goal**: Create a SCHEMA.md-compliant proposal in the correct location.

1. **File path**: `spec/architecture/proposals/<NNN>-<slug>.md`
   - `NNN` = zero-padded next number from pre-flight
   - `slug` = lowercase-kebab-case summary of the title

2. **Frontmatter** (required fields):
   ```yaml
   ---
   id: EXT-<NNN>
   title: "<Short title>"
   phase: <N>
   status: planned
   depends_on: [<EXT-NNN>, ...]
   impacts_modules: []  # filled in Phase 4 after impact check
   created: YYYY-MM-DD
   # promoted_to: MOD-NN   # optional: set when this proposal is promoted to a spec module
   ---
   ```

3. **Required sections** (per SCHEMA.md):
   - `## Problem Statement` — the pain point or gap
   - `## Summary` — one paragraph of what this enables
   - `## Prerequisites` — concrete dependencies
   - `## Scope` — in-scope and out-of-scope lists

4. **Optional sections** (include when useful):
   - `## Implementation Notes` — technical guidance
   - `## Acceptance Criteria` — how to know it's done (recommended; include when scope is non-trivial)

## Phase 3: Validate

**Goal**: Confirm the proposal passes schema checks and appears in the manifest.

### Dual-Validator Architecture

Two validators check proposal frontmatter at different points in the workflow:

- **`propose.validate_proposal(frontmatter: dict)`** (`propose.py:29`): in-memory validator called
  at write time or via `propose validate --pre-write`. Checks: required fields presence, `status`
  against valid statuses, `id` format (`EXT-NNN`), `promoted_to` pattern, `phase` as positive
  integer. Does **not** check file path, parent directory, or required markdown sections.

- **`validation.validate_proposal(filepath: Path)`** (`validation.py:168`): file validator called
  via `propose validate <file>` and by `generate-manifest`. Checks the same five fields **plus**
  filename pattern, parent directory (rejects `planned/`), and required markdown sections
  (`## Problem Statement`, `## Summary`, `## Prerequisites`, `## Scope`).

A proposal that passes the in-memory validator at write time can still fail the file validator at
Phase 3 due to missing required sections. Always run `propose validate <file>` after writing.

1. **Validate the proposal file:**
   ```bash
   python3 -m specbuilder propose validate \
       spec/architecture/proposals/<NNN>-<slug>.md
   ```
   Confirm `OK` before proceeding. Fix any errors reported.

2. **Run generate-manifest:**
   ```bash
   python3 -m specbuilder generate-manifest
   ```
   Validates ALL spec files first; exits 1 and writes nothing if any frontmatter is malformed.
   On success writes `spec/manifest.json` and regenerates `spec/README.md`.
   ⚠️ On error, run `python3 -m specbuilder audit` to find the malformed field, fix it, then re-run.

3. **Verify in manifest.** Check that `spec/manifest.json` contains the new proposal with:
   - Correct `id` (EXT-NNN)
   - Correct `file` path (relative, in proposals root — NOT in `implemented/`)
   - `status: planned`

4. **If validation fails:** Fix the issue and re-run.

## Phase 4: Impact Check (persisted)

**Goal**: Identify impacted modules and persist the assessment in the proposal frontmatter.

1. **Dependency verification.** If `depends_on` lists other EXT-NNN IDs:
   - Verify each referenced proposal exists in the manifest
   - If not, warn: "EXT-NNN is referenced but doesn't exist"

2. **Module overlap.** Check if the proposal's scope touches existing modules.
   Populate `impacts_modules` with your **project's own module IDs** (not SpecBuilder's
   internal IDs). A module is impacted if this proposal changes behavior in its ACs,
   adds/removes inputs or outputs it specifies, or changes routing rows it defines.

3. **Persist the finding.** Update the proposal's `impacts_modules` frontmatter field:
   ```yaml
   impacts_modules: [MOD-04, MOD-06]  # or [] with inline comment if none impacted
   ```
   Must be written to file — not just reported verbally.
   ⚠️ If the write fails, run `python3 -m specbuilder audit` to verify, re-apply the edit, then re-run `generate-manifest`.

4. **Report to user.** Summarize:
   - Which modules are impacted (if any)
   - Which ACs may need revision when the proposal is implemented
   - This is informational — it doesn't block proposal creation

## Batch Mode: Writing Multiple Proposals

When creating multiple proposals in a single session:

1. **Number allocation**: Determine the full range upfront (e.g., EXT-022 through EXT-031). Validate the full range before writing any file:
   ```bash
   python3 -m specbuilder propose check-range \
       spec/architecture/proposals EXT-<start> EXT-<end>
   ```
   If any ID in the range reports `COLLISION`, adjust the range before proceeding.
2. **Write all files** before running validation
3. **Run `generate-manifest` once** at the end (not per-proposal)
4. **Phase 4 per proposal** — run the impact check individually for each proposal and write `impacts_modules` (with inline comment if `[]`) to its frontmatter. Do not defer or skip this step in batch mode.
5. **Cross-reference**: If proposals in the batch depend on each other, set `depends_on` correctly
6. **Present summary table** showing all created proposals with their IDs, titles, and dependency chain

### Partial Batch Write Recovery

If a batch write fails mid-sequence (e.g., a write error after N of M files have been created),
use `check-collision` to determine which EXT numbers were successfully written:

```bash
python3 -m specbuilder propose check-collision \
    spec/architecture/proposals EXT-<NNN>
```

A `COLLISION` result means the file was written; `OK` means it was not. Resume from the first
missing number. Do not re-write files that already exist; verify their content with
`propose validate <file>` before proceeding to `generate-manifest`.

## Status Transitions (for reference)

| Transition | Action |
|-----------|--------|
| planned → in-progress | Update frontmatter status |
| in-progress → implemented | Move to `implemented/`, update status |
| planned/in-progress → parked | Move to `parked/`, update status |
| any → cancelled | Update frontmatter status to `cancelled` |

These transitions are manual (file moves + frontmatter edits). No CLI command exists for proposal promotion.

## Rules
- **Never create proposals in `implemented/` or `parked/`** — they start in root
- **Never create a `planned/` subdirectory** — it doesn't exist in the lifecycle model
- **Always validate after writing** — `generate-manifest` catches format errors immediately
- **One proposal per concern** — don't bundle unrelated changes into a single EXT
- **Proposals are not modules** — they don't need quality gates, AC files, or sign-off workflows
- **If a proposal becomes large enough to be a module**, set `promoted_to: MOD-NN` in frontmatter and create the module via `generate-spec`

