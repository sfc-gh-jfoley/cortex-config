---
name: spec-audit
version: "1.13.0"
description: "Audit project health and generate upgrade proposals"
---

# spec-audit

Inspects a project's configuration, hooks, and structure against SpecBuilder's current expectations. Produces findings and optionally generates an upgrade proposal.

## Tool Permissions

Read, Write, Edit, Bash

## Running the Audit

```bash
python3 -m specbuilder audit
```

Reports findings across these categories:

- **Config** — missing or stale fields in `.specbuilder.toml`
- **Hooks** — change-control hook presence and freshness
- **Profile** — quality profile completeness
- **Structure** — spec/README.md, root README, directory layout

## Interpreting Results

- **⚠ missing** — a field, file, or section that should exist but doesn't
- **ℹ stale** — content that exists but is outdated or deprecated

A finding does NOT mean the project is broken — it means it's not leveraging the latest SpecBuilder capabilities.

## Generating an Upgrade Proposal

```bash
python3 -m specbuilder audit --apply
```

This:
1. Generates `spec/architecture/proposals/NNN-infrastructure-upgrade.md`
2. Applies safe fixes (additive only — adds fields, never removes content)
3. Reports remaining findings that need manual attention

The generated proposal follows the standard proposal format and is reviewable before any further action.

## What Gets Fixed Automatically

| Finding | Auto-fix |
|---------|----------|
| Missing `specbuilder_version` stamp | Appended to `[project]` section |
| Stale Status/Version header in spec/README.md | Header lines removed |

All other findings produce advisory output + a proposal documenting what to do.

## JSON Output

```bash
python3 -m specbuilder audit --format json
```

Returns a JSON array of findings for programmatic consumption or CI integration.

## CI Integration

Add to your drift-check job:

```yaml
- run: |
    result=$(python3 -m specbuilder audit --format json)
    count=$(echo "$result" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
    if [ "$count" -gt 0 ]; then
      echo "::warning::SpecBuilder audit found $count finding(s)"
    fi
```
