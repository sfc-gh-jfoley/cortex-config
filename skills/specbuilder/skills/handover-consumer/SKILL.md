---
name: handover-consumer
version: "1.17.1"
description: "Scaffold a new POC project from a demo handover artifact"
triggers:
  - handover consumer
  - consume handover
  - scaffold from handover
  - handover file
---

# handover-consumer

## Consumer Onboarding

When you receive a demo handover artifact (`spec/modules/<NN>-handover.md` produced by
`python3 -m specbuilder demo-handover`), use the consumer path to scaffold a
new POC project in your own environment:

```bash
python3 -m specbuilder handover-consumer <handover_file> [--dry-run]
```

The command:
1. Parses the handover module (frontmatter `type: handover` required)
2. Runs a guided intake questionnaire to collect environment details:
   - Whether source data exists or synthetic data should be used
   - Target database, schema, and POC role
   - Any environment placeholder substitutions (`## Environment Placeholders` section)
3. Validates the responses against the security posture embedded in the handover
4. Scaffolds a new POC project at the current working directory using
   `scaffold_from_handover()`

### CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `<handover_file>` | (required) | Path to the handover module (`.md` with `type: handover` frontmatter) |
| `--database` | `POC_DB` | Target Snowflake database for the scaffolded POC |
| `--schema` | `_POC_<demo_id>` | Target schema. When combined with `--database`, enables real-data mode in non-interactive runs |
| `--role` | `POC_<demo_id>_ROLE` | POC role name |
| `--dry-run` | off | Preview scaffolded files without writing to disk |
| `--quality-profile` | `poc` | Quality profile written to `[quality].profile` and `[project].mode` in the scaffolded `.specbuilder.toml` |

> **Phase 1 limitation:** The root SKILL.md §Supporting Modules describes `environment.py`
> pre-validation as part of the handover-consumer pipeline. This validation is **not currently
> implemented** — `handover_consumer.py` does not import or call `environment.py`. The
> scaffolded `[environment]` TOML section is populated from intake responses only; no live
> Snowflake environment queries are performed. This will be addressed in a future proposal
> once the `environment.py` integration architecture is resolved.

**⚠️ Security check:** The command validates collected responses against the privilege
manifest and security posture in the handover before scaffolding. A `block`-severity
finding causes a non-zero exit; `warn`-severity findings are printed but do not block.

## Auto-Trigger via `release sign-off`

In **handover mode** (`[project].handover = true` in `.specbuilder.toml`), running:

```bash
python3 -m specbuilder release sign-off <module_num>
```

automatically calls `demo_handover()` as a post-sign-off side effect (implemented in
`release.py`). The handover file (`spec/modules/<NN>-handover.md`) is generated without a
separate `demo-handover` invocation.

⚠️ **Do not run `demo-handover` manually after `release sign-off`** in handover mode — the
file will already exist. If the handover file is missing after sign-off, check:
- `get_handover_flag()` returned `True` (confirm `[project].handover = true` in `.specbuilder.toml`)
- The sign-off exit code was 0 (a sign-off failure suppresses handover generation)

> **Legacy note:** `spec/.demo` sentinel and `SPECBUILDER_DEMO_MODE=1` env var are no longer
> supported. Use `[project].handover = true` in `.specbuilder.toml` instead. The legacy
> `[project].sub_mode = "demo"` is accepted with a deprecation warning.

## Placeholder Substitution (EXT-071)

When the handover file contains a `## Environment Placeholders` table, `scaffold_from_handover()`
collects a value for each `{{TOKEN}}` from the user and substitutes them throughout all generated
content (`.specbuilder.toml` and `spec/modules/01-poc-module.md`).

**Pipeline:**
1. Parse `## Environment Placeholders` table into `HandoverContext.env_placeholders`
   (columns: `Placeholder | Description | Example`)
2. Call `_collect_placeholder_values_cli()` to resolve each token interactively or via
   non-interactive fallback (see below)
3. Call `_substitute_placeholders(content, substitutions)` on TOML and spec content
4. After substitution, scan for remaining `{{[A-Z_]+}}` patterns — any found emit a
   `Warning: unresolved placeholder(s): [...]` to stderr

Backward compatible: handovers without the `## Environment Placeholders` section skip
the substitution pipeline entirely and use the fixed `--database`/`--schema`/`--role` values.

## Non-Interactive Mode

When `sys.stdin.isatty()` is `False` (CI, piped input, scripted invocation), the CLI skips
the guided questionnaire and falls back to CLI argument values or defaults:

| Argument | Default used in non-interactive mode |
|----------|--------------------------------------|
| `--database` | `POC_DB` |
| `--schema` | `_POC_<demo_id>` (derived from handover frontmatter) |
| `--role` | `POC_<demo_id>_ROLE` (derived from handover frontmatter) |

For each `{{TOKEN}}` placeholder that falls back to its example value, a warning is written
to stderr:

```
Warning: non-interactive mode — using example value for '{{TOKEN}}': '<example>'
```

## Environment Configuration (`[environment]` TOML section)

The generated `.specbuilder.toml` includes an `[environment]` section that records the
scaffolded environment details:

```toml
[environment]
target_database = "POC_DB"
target_schema = "_POC_demo123"
poc_role = "POC_demo123_ROLE"
synthetic_data = true
# source_tables = ["DB.SCHEMA.TABLE"]  # present only when real data mode
```

This section is written by `scaffold_from_handover()` and is reserved for future use by
other modules. No current module reads `[environment]` at runtime.

## `from_handover` Frontmatter Field

The generated `spec/modules/01-poc-module.md` includes a `from_handover` field in its
YAML frontmatter that records which demo produced the handover:

```yaml
from_handover: "demo-2024-customer-xyz"
```

This field is required by `HANDOVER_SPEC_FIELDS` (defined in `config.py`) and validated
after spec generation. It is intentionally separate from `REQUIRED_SPEC_FIELDS` so that
non-handover specs are not required to carry it.
