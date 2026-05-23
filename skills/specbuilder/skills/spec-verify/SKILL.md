---
name: spec-verify
version: "1.13.0"
description: "Detect spec drift, run acceptance tests, and manage sign-off workflow"
---

# spec-verify

Detects divergence between specs and implementation, runs acceptance tests, and manages the sign-off lifecycle that transitions modules from `accepted` to `implemented`.

## Tool Permissions

Read, Write, Edit, Bash

## Drift Detection

```bash
python3 -m specbuilder detect-drift [--format json]
```

Reports three categories:
- **Divergence** — spec says X but implementation says Y
- **Staleness** — draft specs not updated in 30+ days
- **Coverage gaps** — implementation exists without a corresponding spec

Present findings to the user with recommended actions (update spec, regenerate, or accept current state).

## Acceptance Testing

```bash
python3 -m specbuilder test-acceptance <module_num>
```

Review the test report:
- **PASS** — no action needed
- **FAIL** — fix implementation and re-run; do not proceed with failures
- **MANUAL_REVIEW** — present to user with context for human judgment

## Cross-Reference Validation

```bash
python3 -m specbuilder implement <module_num> --validate-only
```

Checks:
- SQL compilation (`only_compile=true`)
- Identifier cross-references (procedures reference correct columns)
- Config key consistency across artifacts
- Python import resolution

Fix originating artifact on failure, then re-run.

## Artifact Validation (Tiered)

```bash
python3 -m specbuilder validate-artifacts <module_num> [--tier compile|dry-run|smoke-test|verify]
```

Validates artifacts at configurable depth (tier resolved from active profile unless overridden):

| Tier | Name | What it checks | Requires |
|------|------|----------------|----------|
| 1 | `compile` | SQL compiles, Python parses, YAML/JSON loads | Nothing (offline) |
| 2 | `dry-run` | Tier 1 + DDL deploys to sandbox + object count | `--database` + connection |
| 3 | `smoke-test` | Tier 2 + seed data + row count assertions | `--database` + warehouse |
| 4 | `verify` | Tier 3 + AC assertions + self-correction + privilege discovery | `--database` + warehouse |

**Profile defaults**: `poc` → compile, `production` → dry-run, `strict` → verify.

**Tier 4 options:** `--self-correct` (re-invoke on AC failure, bounded `--max-retries` default 2), `--privilege-discovery` (test-role grant capture). Generates `impl/teardown.sql` and `.specbuilder/privilege-manifest.json`.

**Graceful degradation:** Without `--database`, Tier 2+ falls back to Tier 1 with a warning. Stale cleanup: `--cleanup-stale --database <DB> [--older-than 24]`.

Run artifact validation AFTER cross-reference validation and BEFORE acceptance testing.

## Quality Gate (before acceptance)

Before transitioning a spec to `accepted`, run the quality check:

```bash
python3 -m specbuilder quality <module_num>
```

**Profiles**: The quality gate uses configurable profiles that define thresholds and optional check skips. The active profile is resolved automatically in this order:

1. `SPECBUILDER_QUALITY_PROFILE` environment variable
2. `.specbuilder.toml` `[quality].profile` field at project root
3. Auto-detection from project mode (`spec/.poc` → poc profile)
4. Default: `production` (threshold 75)

Built-in profiles: `poc` (50, skips testability), `production` (75), `strict` (90).

Override with `--profile`:

```bash
python3 -m specbuilder quality <module_num> --profile strict
```

**Threshold**: The `--threshold` flag takes highest priority and overrides the profile's threshold:

```bash
python3 -m specbuilder quality <module_num> --threshold 80  # explicit override
```

If the score is below the threshold:
- BLOCK the status transition
- Present the quality findings to the user
- The spec must be improved before acceptance (fix vague ACs, add edge cases, etc.)

If score passes, proceed to sign-off.

## Sign-Off Workflow

1. Run quality gate (above) — STOP if score below threshold
2. Present the passing test report (acceptance + validation)
3. Ask user to review and approve
4. **Update AC file checkboxes** — re-run ALL acceptance tests and mark the `Pass` column based on CURRENT results:
   - Passing criteria: `☐` → `☑`
   - Failing criteria: MUST remain `☐` (or reset to `☐` if previously marked)
   - Do NOT inherit stale checkmarks from prior runs — verify each criterion NOW
   - This is a PRE-CONDITION for sign-off. All criteria must pass to proceed.
   - If any criterion fails, STOP — fix the implementation, re-run tests, then retry.
5. **Environment drift check (optional).** If `.specbuilder/environment.json` exists and a
   connection is available, re-validate declared objects. Warn if any are missing (advisory,
   does not block sign-off).
6. Run the sign-off command to atomically transition status and create a changelog entry:
   ```bash
   python3 -m specbuilder sign-off <module_num> [--type feature|fix|pattern|governance]
   ```
   This command:
   - Transitions the spec status to `implemented`
   - Auto-creates a changelog entry (version bump, context from Executive Summary)
   - Regenerates `manifest.json` and `SKILL.md` version
7. **POC mode: auto-generate summary.** If `is_poc_mode()`, the sign-off command automatically
   generates `spec/POC-SUMMARY.md`. No separate command needed.

## Recovery from Partial Failure

If the sign-off process fails mid-way:

1. **Quality gate failed**: No state was changed. Fix the spec and re-run.
2. **AC update failed** (before sign-off command): No state was changed. Fix AC file and retry.
3. **Sign-off command failed after starting**:
   - Check spec frontmatter — if status is still `accepted`, no rollback needed
   - If status changed to `implemented` but changelog wasn't created:
     ```bash
     python3 -m specbuilder generate-index  # regenerate manifest
     ```
     Then manually verify the changelog entry exists
4. **Session interrupted after successful sign-off**: The atomic transition completed. Verify with `python3 -m specbuilder implement --status` that everything is consistent.

## Status Lifecycle

```
draft → in-review → accepted → implemented
```

Transitions are gated: `accepted` requires user sign-off; `implemented` requires all acceptance tests passing.

## Regenerate Index

```bash
python3 -m specbuilder generate-index
```

Utility to rebuild `manifest.json` and README tables from source spec files. Use after manual edits or when index appears stale.
