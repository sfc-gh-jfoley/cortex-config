---
name: spec-generate
version: "1.13.0"
description: "Guide users through intake clarification and generate spec modules with acceptance criteria"
---

# Spec Generate

Converts user requirements into formal spec modules through structured clarification and generation. Ensures all ambiguity is resolved before producing SCHEMA.md-compliant spec files with acceptance criteria.

## Tool Permissions

Read, Write, Edit, Bash, ask_user_question

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

## Phase 1: Intake & Clarification

**Goal**: Fully understand the requirement before writing anything.

1. **Read the requirement.** Check `spec/INTAKE.md` for a filled form, or treat chat description as intake.
2. **Check environment section.** If INTAKE.md has an "Existing Environment" section with
   declared objects AND a Snowflake connection is available, validate declared objects
   exist and retrieve metadata. Cache results to `.specbuilder/environment.json`.
   If no connection, skip — section is accepted as-is.
3. **Run skill discovery:**
   ```bash
   python3 -m specbuilder discover-skills
   ```
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
   - YAML frontmatter: `id`, `title`, `status: draft`, `version: "0.1.0"`, `last_updated`
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

   ## Summary

   One-line description of what the module does.

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
   - Frontmatter MUST include `spec_reference` pointing to the module file
4. **Regenerate index** — run `python3 -m specbuilder generate-index` to atomically update `manifest.json` and README module tables. Do NOT manually edit spec/README.md.
5. **Present spec for review.** Explain what was generated, ask for feedback, iterate until satisfied.

---

## HARD STOP

Phase 2 is complete. You MUST wait for explicit user acceptance ("approved", "looks good", "accept"). Do NOT:
- Write implementation code or SQL artifacts
- Create file stubs or execute scripts
- Continue to implementation in the same turn

If user said "build X", split into two gated interactions: spec first, implementation only after acceptance.

## POC Mode

**Orchestrator handoff:** In POC mode, the orchestrator routes here via fast path (no manifest read, no governance context). Proceed directly to collapsed flow.

When `is_poc_mode()` returns True (detected via `spec/.poc` sentinel or `.specbuilder.toml` mode):

- **Collapsed flow**: Intake + spec generation happen in a single interaction (no separate phases)
- **Clarification**: Skip clarification cycle if intake contains explicit targets (schema refs, source tables, SLAs). If ambiguous, ask ONE round of questions only (not a loop)
- **Acceptance**: Implicit on user confirmation ("looks good", "yes", "approved") — no separate acceptance phase with multi-status transitions. Status goes directly from draft → accepted.
- **Quality gate**: Uses `poc` profile (threshold: 50, testability check skipped)
