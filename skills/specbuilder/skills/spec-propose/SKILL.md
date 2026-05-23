---
name: spec-propose
version: "1.13.0"
description: "Guide proposal authoring with pre-flight checks, validation, and impact analysis"
---

# Spec Propose

Guides the creation of architecture proposals (EXT-NNN files) with pre-flight validation, correct directory placement, schema compliance, and impact analysis against existing proposals and modules.

## Tool Permissions

Read, Write, Edit, Bash, ask_user_question

## When to Run

- User wants to write a new proposal or extension
- User describes a problem/enhancement that isn't covered by existing proposals
- User says "propose", "new proposal", "write a proposal", or references EXT-NNN creation
- The orchestrator routes here based on proposal-related intent

## Pre-Flight (MANDATORY — before writing anything)

1. **Read placement rules.** Open `spec/architecture/SCHEMA.md` § "Directory Placement (Lifecycle)". Confirm:
   - Active proposals (`planned`, `in-progress`) → `spec/architecture/proposals/` root
   - Completed → `proposals/implemented/`
   - Shelved → `proposals/parked/`
   - **NEVER** create a `planned/` subdirectory

2. **Determine next EXT number.** Scan ALL proposals (root + `implemented/` + `parked/`):
   ```bash
   ls spec/architecture/proposals/*.md spec/architecture/proposals/implemented/*.md spec/architecture/proposals/parked/*.md 2>/dev/null | grep -oP '\d{3}' | sort -n | tail -1
   ```
   Next number = highest found + 1. Zero-pad to 3 digits.

3. **Check for scope overlap.** Read `spec/manifest.json` proposals list. Compare the new proposal's problem/scope against existing proposal titles. If overlap is found:
   - Ask user: "EXT-NNN already covers similar scope. Should we extend that proposal or create a new one?"
   - If extending, route to editing the existing file instead

## Phase 1: Intake & Clarification

**Goal**: Fully understand what's being proposed before writing the file.

1. **Clarify the problem.** What's broken or missing? Why does it matter?
2. **Clarify the solution.** What does this proposal enable?
3. **Define scope boundaries.** What's in? What's explicitly out?
4. **Identify dependencies.** Does this depend on other EXT-NNN proposals?
5. **Determine phase.** Which delivery phase does this belong to?

### Decision Gate: Module vs. Proposal

Before proceeding, assess whether this work belongs as a **proposal** or a **module**:

| Route to **spec-generate** (module) when ANY of: | Keep as **proposal** when ALL of: |
|--------------------------------------------------|-----------------------------------|
| Has structured inputs and outputs (data flows) | Infrastructure or tooling change |
| Requires formal ACs with sign-off | One-shot implementation (do it, verify, done) |
| Will produce multiple implementation artifacts | No formal sign-off needed |
| Has cross-module dependencies affecting architecture | Self-contained, doesn't alter module behavior |
| Requires ongoing maintenance | |

If the work is better suited as a module, **stop and route to spec-generate** instead of writing a proposal.

### Batch Mode

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
   phase: <2|3|4>
   status: planned
   depends_on: [<EXT-NNN>, ...]
   impacts_modules: []  # filled in Phase 4 after impact check
   ---
   ```

3. **Required sections** (per SCHEMA.md):
   - `## Problem Statement` — the pain point or gap
   - `## Summary` — one paragraph of what this enables
   - `## Prerequisites` — concrete dependencies
   - `## Scope` — in-scope and out-of-scope lists

4. **Optional sections** (include when useful):
   - `## Implementation Notes` — technical guidance
   - `## Acceptance Criteria` — how to know it's done (strongly recommended)

## Phase 3: Validate

**Goal**: Confirm the proposal passes schema checks and appears in the manifest.

1. **Run generate-index:**
   ```bash
   python3 -m specbuilder generate-index
   ```
   This validates frontmatter, required sections, and updates `manifest.json`.

2. **Verify in manifest.** Check that `spec/manifest.json` contains the new proposal with:
   - Correct `id` (EXT-NNN)
   - Correct `file` path (relative, in proposals root — NOT in `implemented/`)
   - `status: planned`

3. **If validation fails:** Fix the issue (usually missing section or frontmatter field) and re-run.

## Phase 4: Impact Check (persisted)

**Goal**: Identify impacted modules and persist the assessment in the proposal frontmatter.

1. **Dependency verification.** If `depends_on` lists other EXT-NNN IDs:
   - Verify each referenced proposal exists in the manifest
   - If not, warn: "EXT-NNN is referenced but doesn't exist"

2. **Module overlap.** Check if the proposal's scope touches existing modules:
   - Read `spec/manifest.json` modules list
   - For each module, check if this proposal modifies, extends, or depends on its implementation
   - Indicators: references MOD-NN implementation files, changes behavior covered by a module's ACs, adds inputs/outputs to an existing module

3. **Persist the finding.** Update the proposal's `impacts_modules` frontmatter field:
   ```yaml
   impacts_modules: [MOD-04, MOD-06]  # or [] if no modules impacted
   ```
   This MUST be written to the file — not just reported verbally. Future sessions implementing this proposal will read this field to know what ACs to check.

4. **Report to user.** Summarize:
   - Which modules are impacted (if any)
   - Which ACs may need revision when the proposal is implemented
   - This is informational — it doesn't block proposal creation

## Batch Mode

When creating multiple proposals in a single session:

1. **Number allocation**: Determine the full range upfront (e.g., EXT-022 through EXT-031)
2. **Write all files** before running validation
3. **Run `generate-index` once** at the end (not per-proposal)
4. **Cross-reference**: If proposals in the batch depend on each other, set `depends_on` correctly
5. **Present summary table** showing all created proposals with their IDs, titles, and dependency chain

## Status Transitions (for reference)

After a proposal is created:

| Transition | Action | Who |
|-----------|--------|-----|
| planned → in-progress | Update frontmatter, keep in root | Author |
| in-progress → implemented | Move to `implemented/`, update status | Author (after work is verified) |
| planned → parked | Move to `parked/`, update status | Author (deprioritizing) |
| parked → planned | Move back to root, update status, review content | Author (re-activating) |

These transitions are manual (file moves + frontmatter edits). There is no CLI command for proposal promotion.

## Rules

- **Never create proposals in `implemented/` or `parked/`** — they start in root
- **Never create a `planned/` subdirectory** — it doesn't exist in the lifecycle model
- **Always validate after writing** — `generate-index` catches format errors immediately
- **One proposal per concern** — don't bundle unrelated changes into a single EXT
- **Proposals are not modules** — they don't need quality gates, AC files, or sign-off workflows
- **If a proposal becomes large enough to be a module**, set `promoted_to: MOD-NN` in frontmatter and create the module via `spec-generate`
