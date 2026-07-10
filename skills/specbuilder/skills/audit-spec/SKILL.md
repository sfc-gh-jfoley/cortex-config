---
name: audit-spec
version: "1.17.1"
description: "Audit project health and generate upgrade proposals"
triggers:
  - audit
  - spec audit
  - project health
---

# audit-spec

Inspects a project's configuration, hooks, and structure against SpecBuilder's current expectations. Produces findings and optionally generates an upgrade proposal.

## Tool Permissions

Read, Write, Edit, Bash

## Stopping Points

- ⚠️ **Before `--apply`** — Present the audit findings to the user and confirm before running `--apply`. The command writes files and may generate a proposal.

## Output

- Findings report printed to stdout
  (categories: config, hooks, structure, changelog, skill-coverage, readme)
- With `--apply`: `spec/architecture/proposals/NNN-infrastructure-upgrade.md` (generated), safe additive fixes applied to `.specbuilder.toml` and `spec/README.md`
- With `--format json`: JSON array of findings for programmatic use
- With `--format json --envelope`: DiagnosticEnvelope wrapping the findings array

> _Requires PYTHONPATH set per the orchestrator's Runtime Environment section. If invoking this sub-skill directly (not via the orchestrator), run the detection loop first._

## Running the Audit

```bash
python3 -m specbuilder audit
```

Reports findings across these categories:

- **Config** — missing or stale fields in `.specbuilder.toml`
- **Hooks** — change-control hook presence and valid JSON structure
- **Structure** — spec/README.md, root README, directory layout
- **Readme** — root README sentinel markers
- **Changelog** — commit accumulation since last changelog entry
- **Skill-coverage** — CLI flags not documented in SKILL.md files

### Checks Reference

All 10 checks run by default:

| Check | Category | Auto-fix |
|-------|----------|----------|
| `check_toml_exists` | config | No |
| `check_version_stamp` | config | Yes (adds `specbuilder_version` to `.specbuilder.toml`) |
| `check_quality_profile_fields` | config | No |
| `check_validation_tier_awareness` | config | No |
| `check_hook_exists` | hooks | No |
| `check_spec_readme_header` | structure | Yes (removes stale Status/Last Updated/Version lines from `spec/README.md`) |
| `check_root_readme_sentinels` | readme | No |
| `check_spec_directory` | structure | No |
| `check_changelog_freshness` | changelog | No (emits `category='changelog'` when >5 commits since last entry; path roots are derived from `.specbuilder.toml` `[project].src_root`/`skills_root` or probed automatically — emits nothing in projects with unrecognised layouts) |
| `check_skill_coverage` | skill-coverage | No (emits a `warning` for each `--flag` from a subcommand's `--help` output absent from the corresponding SKILL.md; excludes `--help` and `--version`; emits nothing in consumer projects — projects without a `specbuilder/skills/` directory; **maintenance**: `audit.py:skill_command_map` must be updated when adding subcommands to any listed subskill — new flags are silently missed until the map is updated) |

## Interpreting Results

- **⚠ missing** — a field, file, or section that should exist but doesn't
- **ℹ info** — an advisory finding that requires no action (e.g. optional fields with auto-resolved defaults)
- **ℹ stale** — content that exists but is outdated
- **⊘ deprecated** — a feature or field that is forward-declared but not yet emitted by any check
- **▲ warning** — a CLI flag or feature present in code but absent from SKILL.md documentation
  (emitted by `check_skill_coverage`)

### Mode-Sensitive Behaviour

`run_audit()` runs all 10 checks unconditionally regardless of the active quality profile
(`poc`, `full`, `strict`, or `prototype`). Check selection and severity levels are
profile-invariant by design — the audit measures structural health, not delivery strictness.
Mode-sensitive escalation (e.g. stricter checks under `strict` profile) is not currently
implemented and would require a separate enhancement proposal.

A finding does NOT mean the project is broken — it means it's not leveraging the latest SpecBuilder capabilities.

## Generating an Upgrade Proposal

> ⚠️ **STOP** — Present the findings from `audit` output to the user and confirm before continuing. Running `--apply` will write files and may generate a proposal.

Preview proposed fixes without writing anything:

```bash
python3 -m specbuilder audit --dry-run
```

Apply fixes (requires explicit `--confirm` to prevent accidental writes):

```bash
python3 -m specbuilder audit --apply --confirm
```

Omitting `--confirm` with `--apply` prints the preview and exits with code 1:

```bash
python3 -m specbuilder audit --apply   # preview only — no files written
```

This:
1. Generates `spec/architecture/proposals/NNN-infrastructure-upgrade.md`
2. Applies safe fixes (`check_version_stamp` adds `specbuilder_version`; `check_spec_readme_header` removes stale Status/Last Updated/Version lines from `spec/README.md`)
3. Reports remaining findings that need manual attention

The generated proposal follows the standard proposal format and is reviewable before any further action.

> **Post-apply:** After `--apply` completes, run:
> ```bash
> python3 -m specbuilder generate-manifest
> ```
> The `--apply` command creates a new `NNN-infrastructure-upgrade.md` proposal file in
> `spec/architecture/proposals/`. The manifest index is not updated automatically — this
> step is required to keep it current.

> **Grant validation is not part of `audit`.**
> `grant_validator.py` implements the `grant-test` subcommand as a standalone pipeline.
> Run `python3 -m specbuilder grant-test` separately to validate grant posture.
> The `audit` checks listed above do not include grant findings.

## What Gets Fixed Automatically

| Finding | Auto-fix |
|---------|----------|
| Missing `specbuilder_version` stamp | Appended to `[project]` section |
| Stale Status/Version header in spec/README.md | Header lines removed |

All other findings produce advisory output + a proposal documenting what to do.

## Recovery from Partial Failure

`--apply` is a two-phase write: (1) generate upgrade proposal, (2) apply safe fixes (version stamp + README header). If the process is interrupted mid-way:

**Scenario 1 — failure before any writes** (e.g., permission error, missing directory): No state was changed. Re-run `python3 -m specbuilder audit --apply` safely.

**Scenario 2 — proposal written but fixes not applied** (interrupted between phases): An orphaned `NNN-infrastructure-upgrade.md` exists in `spec/architecture/proposals/` but `.specbuilder.toml` has no `specbuilder_version` stamp. To recover:
1. Delete the orphaned proposal file manually
2. Re-run `python3 -m specbuilder audit --apply` — it will assign a new number and apply fixes

**Scenario 3 — `proposals/` directory missing**: If `spec/architecture/proposals/` does not exist, `--apply` emits a warning on stderr ("proposals directory not found") and skips proposal generation entirely. Safe fixes (version stamp + README header) are still applied. To recover:
1. Create the missing directory: `mkdir -p spec/architecture/proposals/`
2. Re-run `python3 -m specbuilder audit --apply` — it will now generate the upgrade proposal

## JSON Output

```bash
python3 -m specbuilder audit --format json
```

Returns a JSON array of findings for programmatic consumption or CI integration. Each finding has this shape:

```json
{
  "category": "...",
  "severity": "...",
  "description": "...",
  "auto_fixable": true,
  "fix": "..."
}
```

Add `--envelope` to wrap the array in a `DiagnosticEnvelope` with tool metadata:

```bash
python3 -m specbuilder audit --format json --envelope
```

```json
{
  "tool": "audit",
  "version": "1.x.x",
  "timestamp": "2026-...",
  "module": null,
  "findings": [...]
}
```

### Combining `--format json` with `--apply` or `--dry-run`

`--format json --apply` and `--format json --dry-run --apply` are both valid. In these combinations:

- The JSON findings array is written to **stdout** (as with plain `--format json`).
- Apply-phase messages (generated proposal path, applied fixes, remaining findings) or
  dry-run preview output are written to **stderr**.

A warning header is emitted on stderr when these flags are combined to make the split explicit.
CI consumers reading only stdout receive clean JSON; stderr carries human-readable progress.

Note: `--format json --dry-run` without `--apply` exits cleanly with JSON only — it exits
before the dry-run preview block, so no stderr output is produced.

## CI Integration

Exit codes:
- `0` — audit clean (no findings)
- `1` — findings present (CI should fail)

Usage in CI:
    python3 -m specbuilder audit || exit 1

For richer output, add to your drift-check job:

```yaml
- run: |
    result=$(python3 -m specbuilder audit --format json)
    count=$(echo "$result" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
    if [ "$count" -gt 0 ]; then
      echo "::warning::SpecBuilder audit found $count finding(s)"
    fi
```
