---
name: verify-spec
version: "1.17.1"
description: "Detect spec drift, run acceptance tests, and manage sign-off workflow"
triggers:
  - check drift
  - run acceptance
  - sign off
---

# verify-spec

Detects divergence between specs and implementation, runs acceptance tests, and manages the sign-off lifecycle that transitions modules from `accepted` to `implemented`.

## Tool Permissions

Read, Write, Edit, Bash, ask_user_question

## Prerequisites

Set `PYTHONPATH` so the `specbuilder` package is importable:

```bash
for d in .cortex/skills . vendor; do
  [ -d "$d/specbuilder" ] && export PYTHONPATH="$d:${PYTHONPATH:-}" && break
done
```

If the loop finds nothing, stop and tell the user SpecBuilder is not installed.

## Stopping Points

- ⚠️ **Breaking spec changes detected (Step 0)** — If `diff --breaking-only` exits code 1, STOP. Do NOT proceed to sign-off until breaking changes are resolved or explicitly accepted.
- ⚠️ **Before sign-off** — All ACs must pass and the user must explicitly approve. Do NOT run `sign-off` command without confirmation.
- ⚠️ **Quality gate failure** — If spec quality score is below threshold (poc: 50, full: 75, strict: 90, prototype: 50), STOP and present findings to user before proceeding.
- ⚠️ **Quality gate failure (prototype)** — threshold is 50 (same as `poc`); the gate still blocks sign-off. `testability` and `edge_case_traceability` checks are skipped but all other quality dimensions apply.

## Output

**Drift Detection:** Findings report only — no file writes.

**Acceptance Testing:** Test report only — no file writes by default; if `output_file` is provided, results are written to that path.

**Sign-Off (full workflow only):**
- Updated AC file (`spec/acceptance-criteria/NN-<slug>.md`) with checkboxes marked
- Updated spec frontmatter: `status: implemented`
- Changelog entry in `spec/changelog/`
- *(Conditional — handover flag only)* Handover artifact via `demo_handover()`

> _Requires PYTHONPATH set per the orchestrator's Runtime Environment section. If invoking this sub-skill directly (not via the orchestrator), run the detection loop first._
## Drift Detection

```bash
python3 -m specbuilder detect-drift [--format json] [--staleness-days N] [--no-git] [--fail-on high|medium|low]
```

Flags:
- `--staleness-days N` — number of days before a spec is considered stale (default: 30)
- `--no-git` — skip git-log-based staleness check
- `--fail-on {high,medium,low}` — exit 1 if any finding is at or above this severity level. Severity ranks: `high` > `medium` > `low`. Use in CI to enforce a hard gate on HIGH findings: `--fail-on high`.

**Git availability degradation:** When `--no-git` is not passed, the post-signoff modification check calls `git log` per implementation file. Failure modes are handled asymmetrically:
- **Git absent** (`FileNotFoundError`): silent — post-signoff checks are skipped entirely with no warning emitted. The drift report will not include modification-after-signoff findings.
- **Timeout** (`subprocess.TimeoutExpired`): per-file warning to stderr; other files continue.
- **OS error**: per-file warning to stderr; other files continue.

If running in an environment without git and post-signoff drift accuracy is required, pass `--no-git` explicitly to make the skip intentional, then perform modification checks manually.

Reports three categories with seven specific triggering conditions:

**Divergence** (three subtypes):
- *(1)* Spec status is `accepted` but no implementation files found — spec accepted with no matching `impl/` artifacts
- *(2)* Spec status is `implemented` but no implementation files found — files deleted or mis-pathed after sign-off
- *(3)* Implementation files modified after sign-off date (`last_updated` proxy) — re-verification required

**Staleness** (one subtype):
- *(4)* `draft` or `in-review` spec not updated within `--staleness-days` (default 30) — may be abandoned

**Coverage gaps** (three subtypes):
- *(5)* No AC file found for a spec module — generate one with `generate-spec` or author manually
- *(6)* AC file exists with no matching spec module — orphan artifact, safe to delete after confirming intent
- *(7)* Implementation file in `impl/` not claimed by any spec module — undocumented code, consider authoring a spec

Present findings to the user with recommended actions (update spec, regenerate, or accept current state).

> **Note:** The `GATE_SENTINEL_MAX_AGE_SECONDS` constant (1800 s) governs generate-spec's
> sentinel file freshness check. It is not used by verify-spec; the only time-based
> threshold in this skill is `--staleness-days` (sourced from `DRIFT_STALENESS_DAYS`).

## Acceptance Testing

```bash
python3 -m specbuilder test-acceptance <module_num> [output_file] [--schema SCHEMA_FQN]
```

Flags:
- `--schema SCHEMA_FQN` — fully qualified sandbox schema (e.g. `MY_DB.SANDBOX_SCHEMA`). When provided, translatable ACs are surfaced as AUTOMATED items with their assertion SQL shown.
- `--execute-assertions` — execute SQL assertion blocks against the active Snowflake connection via the cortex CLI. Requires an active cortex connection. When set, AUTOMATED items are promoted to PASS or FAIL based on query results.
- `--format {text,json}` — output format (default: `text`). Pass `json` to emit a DiagnosticEnvelope-wrapped result set suitable for CI consumption.

If `output_file` is provided, acceptance test results are written to that path.

Review the test report:
- **PASS** — no action needed
- **FAIL** — fix implementation and re-run; do not proceed with failures
- **MANUAL_REVIEW** — present to user with context for human judgment
    - **AUTOMATED** — SQL assertion surfaced for Tier 4; assertion SQL is shown by default; pass `--execute-assertions` to also execute SQL assertion blocks against the active Snowflake connection via `cortex sql`. Each assertion is reported as PASS or FAIL with the actual query result included. This flag is a no-op for non-SQL assertion types.

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
python3 -m specbuilder validate-artifacts <module_num> [--tier compile|dry-run|smoke-test|verify] [--format json]
```

Validates artifacts at configurable depth (tier resolved from active profile unless overridden):

| Tier | Name | What it checks | Requires |
|------|------|----------------|----------|
| 1 | `compile` | SQL compiles, Python parses, YAML/JSON loads | Nothing (offline) |
| 2 | `dry-run` | Tier 1 + DDL deploys to sandbox + object count | `--database` + connection |
| 3 | `smoke-test` | Tier 2 + seed data + row count assertions | `--database` + warehouse |
| 4 | `verify` | Tier 3 + AC assertions + retry loop + privilege discovery | `--database` + warehouse |

**Profile defaults**: `poc` → compile, `full` → dry-run, `strict` → verify, `prototype` → compile.

**Tier 4 options:** `--retry` (re-run failed AC assertions up to `--max-retries` times without corrective action between attempts, default 0 for full, poc, and prototype profiles; default 2 for strict profile only), `--privilege-discovery` (test-role grant capture). Generates `impl/teardown.sql` and `.specbuilder/privilege-manifest.json`.

**Flags:**
- `--format json` — emit results as a DiagnosticEnvelope JSON object instead of the default markdown report.

> **Note:** The `--retry` loop executes within `validate-artifacts --tier verify` and retries failed AC assertions before the spec transitions to sign-off. It does not operate inside `sign_off()` itself.

**SQL tier availability:** Tiers 2/3/4 (dry-run, smoke-test, verify) require SQL executor implementation and are not available in this version. Invoking any of these tiers exits with an error regardless of whether `--database` is supplied. Use `--tier compile` for Tier 1 compile-only validation. Stale cleanup: `--cleanup-stale --database <DB> [--older-than 24]`.

Run artifact validation AFTER cross-reference validation and BEFORE acceptance testing.

## Quality Gate (before sign-off)

Before transitioning a spec to `implemented`, run the quality check:

```bash
python3 -m specbuilder quality <module_num> [--profile poc|full|strict] [--threshold N]
```

Profile resolved from: env `SPECBUILDER_QUALITY_PROFILE` → `.specbuilder.toml [quality].profile` → project mode (`spec/.poc` → poc) → default `full`. Built-in thresholds: `poc` 50, `full` 75, `strict` 90, `prototype` 50. `--threshold N` takes highest priority.

**Prototype profile:** threshold=50 (same as `poc`); `skip_checks` = [`testability`, `edge_case_traceability`]; validation tier = `compile`. The quality gate still runs and will block sign-off if the score falls below 50. The relaxed skip_checks list means testability and edge-case traceability scoring is omitted; all other quality dimensions apply normally.

If score below threshold: BLOCK transition, present findings to user, fix spec (vague ACs, edge cases) before sign-off.

## AC Coverage

Check which acceptance criteria have test coverage:

    python3 -m specbuilder ac-coverage [MODULE_NUM] [OPTIONS]

Flags:
- `--new-only` — check only ACs not in `.ac-coverage-baseline`
- `--strict` — exit 1 if any unmapped ACs found (without `--strict`, unmapped ACs produce warnings only)
- `--format json` — emit findings as a DiagnosticEnvelope JSON object (single-module only). The JSON path uses the same qualified marker key (`module_id/ac_id`) and heuristic-match logic as the text path.

Output: per-AC test mapping report; non-zero exit only with `--strict`.

**`check_strict()` absent-directory behavior:** If `spec/modules/` does not exist, `check_strict()` exits with code **2** and prints a diagnostic to stderr. Exit code 2 means the directory was absent (configuration error), distinct from exit code 1 (uncovered ACs found) and exit code 0 (all covered).

## Sign-Off Workflow

**Step 0 — Check for breaking spec changes (required):**
```bash
python3 -m specbuilder diff <module_num> --breaking-only
```
If `diff` exits with code 1 (breaking changes detected), **STOP**. Breaking changes must be resolved or explicitly accepted before sign-off proceeds. A non-zero exit from `diff` means downstream consumers of this spec may break silently; do not proceed until the change rationale is reviewed.

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
6. Run the sign-off command. Before writing any files, the command programmatically
   re-runs three gates — (a) breaking-diff check, (b) AC test suite (all criteria must
   pass), and (c) quality gate using `get_effective_profile()`. Pass `--confirm` to
   attest that you have reviewed the test report:
   ```bash
   python3 -m specbuilder sign-off <module_num> --confirm [--type feature|fix|pattern|governance] [--dry-run]
   ```
   - `--dry-run` — preview the sign-off (version bump, changelog entry, status change) without writing any files. The three programmatic gates (breaking-diff, AC, quality) **all run first**; the dry-run early-return fires only after all three gates pass. `--confirm` is not required when `--dry-run` is set.
   If any gate blocks, the command exits with a message identifying which check failed.
   Refer back to step 0 (breaking changes), step 4 (AC checkboxes), or step 1 (quality
   gate) to resolve before retrying. Note: the quality gate inside `sign_off()` uses
   `get_effective_profile()` (`config.py`), which delegates directly to `get_active_profile()` —
   single-level resolution with no sub-mode merging. The `demo` sub_mode (or
   `[project].handover = true`) does not affect the quality gate threshold; it controls handover
   artifact generation only, via `get_handover_flag()`. If the active profile at sign-off differs
   from the one used in step 1, re-run the quality check with the same `--profile` flag before
   proceeding.
   This command:
   - Transitions the spec status to `implemented`
   - Auto-creates a changelog entry (version bump, context from Executive Summary)
   - Regenerates `manifest.json` and `SKILL.md` version
7. **POC mode: auto-generate summary.** If `is_poc_mode()`, the sign-off command automatically
   generates `spec/POC-SUMMARY.md`. No separate command needed.

7b. **Handover flag: auto-generate handover module.** If `get_handover_flag()` is true
    (`[project].handover = true` in `.specbuilder.toml`, or the deprecated
    `[project].sub_mode = "demo"`), the sign-off command automatically invokes
    `demo_handover()` after the POC summary step. This is a **conditional side-effect**:
    - On success: prints `"Demo handover generated."` to stdout.
    - On failure: prints a warning to stderr but **does not block sign-off** — the spec
      status transition and changelog entry are already committed. Re-run
      the `handover-consumer` sub-command manually to regenerate if needed.
    The handover artifact is not listed in the §Output section's three-artifact inventory
    because it is only generated for projects with the handover flag set.

## Recovery from Partial Failure

If the sign-off process fails mid-way:

1. **Quality gate failed**: No state was changed. Fix the spec and re-run.
2. **AC update failed** (before sign-off command): No state was changed. Fix AC file and retry.
3. **Sign-off command failed after starting**:
   - Check spec frontmatter — if status is still `accepted`, no rollback needed
   - If status changed to `implemented` but changelog wasn't created:
      ```bash
      python3 -m specbuilder generate-manifest  # regenerate manifest
      ```
     Then manually verify the changelog entry exists
4. **Session interrupted after successful sign-off**: The atomic transition completed. Verify with `python3 -m specbuilder implement --status` that everything is consistent.

**Changelog created but status still `accepted` (reverse partial failure):**
This occurs when the changelog file was written but `sign_off()` raised an error
(e.g., missing YAML frontmatter block) before the status update completed.
Recovery:
1. Identify the orphaned entry in `spec/changelog/` — it will be the highest-numbered
   file and will contain TODO placeholder content.
2. Delete the orphaned changelog file.
3. Re-run `python3 -m specbuilder sign-off <module_num>`.
   A new changelog entry will be created and the spec status will be updated.
Do NOT re-run sign-off without deleting the orphaned entry first: `get_next_changelog_number()` always increments with no deduplication check, creating a duplicate entry.

## Status Lifecycle

```
draft → in-review → accepted → implemented
```

Transitions are gated: `accepted` requires user sign-off; `implemented` requires all acceptance tests passing.

> **POC mode exception:** When `spec/.poc` exists or `.specbuilder.toml` has `mode = "poc"`,
> the `in-review` state is skipped. Status transitions directly: `draft → accepted`.
> The quality gate and sign-off (`accepted → implemented`) still apply.

## Regenerate Index

```bash
python3 -m specbuilder generate-manifest
```

Utility to rebuild `manifest.json` and README tables from source spec files. Use after manual edits or when index appears stale.
> **Operations (3 per invocation):** (1) validates ALL spec frontmatter — exits code 1 and writes nothing if any file is malformed; run `python3 -m specbuilder audit` to identify issues. (2) Writes `spec/manifest.json`. (3) Writes `spec/README.md` tables.

## Spec Version Diff

```bash
python3 -m specbuilder diff <module_num> [--from COMMIT] [--to COMMIT] [--json] [--breaking-only]
```
Compares two spec versions section-by-section. Change types: **breaking** (items removed from `Inputs`, `Output`, `Acceptance Criteria`, `Edge Cases`), **additive** (new items added), **cosmetic** (rewording in `Executive Summary`/`Extension Points`). Flags: `--from`/`--to COMMIT` (defaults: `HEAD`/working tree), `--json`, `--breaking-only`. Exit codes: `0` = clean, `1` = breaking (CI gate), `2` = usage error. Add to pre-merge CI to block PRs with unversioned breaking spec changes.
