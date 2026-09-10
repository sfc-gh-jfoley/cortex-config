---
name: scaffold-spec
version: "1.17.1"
description: "Initialize spec-driven project structure with schemas, templates, hooks, and generation scripts"
triggers:
  - scaffold
  - initialize spec
  - set up spec structure
---

# Scaffold Spec

Initializes a project for spec-driven development by creating the `spec/` directory tree, schemas, templates, hooks, and supporting configuration. This is always the first step — other sub-skills require the scaffolded structure to exist.

## Tool Permissions

This skill uses: **Read**, **Write**, **Edit**, **Bash**

## Stopping Points

- ⚠️ **Before running scaffold** — Mode must be confirmed (PoC vs Full SDD Mode). The orchestrator handles this prompt; if invoking directly with `--poc`, pass `--confirm` to proceed (the CLI will exit with an error otherwise).
- ⚠️ **Before POC-to-Full upgrade** — Confirm the user is ready to permanently remove POC enforcement. Deleting `spec/.poc` and changing the toml mode are irreversible.

## Output

- Full mode: `spec/` directory tree, `spec/manifest.json`, `spec/README.md`, `spec/INTAKE.md`, `spec/architecture/SCHEMA.md`, `.cortex/hooks.json`, `agent.md`
- Lite mode: `spec/modules/`, `spec/INTAKE.md`, `.cortex/hooks.json`,
  `.cortex/hooks/change-control-gate.sh`, `agent.md`, `.gitignore`
- Optional: `.github/workflows/spec-drift.yml` or `.gitlab-ci.yml` (if CI platform selected)

## When to Run

- Fresh project with no `spec/` directory
- User explicitly asks to scaffold or initialize spec structure
- The orchestrator (`spec-architect`) routes here because `spec/` is missing
- User says "graduate this POC", "promote to full project", or "going to production with this" — use POC-to-Full Upgrade section

**Mode passthrough from orchestrator:** When the orchestrator detects first-use (no `spec/` and no `.specbuilder.toml`), it prompts the user to choose PoC or Full SDD Mode before routing here. The orchestrator passes the mode selection through:
- **PoC selected** → run with `--poc` flag (creates lite structure + `spec/.poc` sentinel + `.specbuilder.toml` with `mode = "poc"`)
- **Full SDD Mode selected** → run with default full scaffold (no special flag)

If the user invokes scaffold directly (bypassing the orchestrator), the existing `--poc` flag remains available as documented below.

> **First-use flow:** `--lite` is offered as "Minimal files" in the Step 2 prompt when
> Full SDD Mode is selected at first use. It may also be passed directly on the command
> line at any time: `python3 -m specbuilder scaffold --lite`.

## Workflow

Run the appropriate command below based on the mode confirmed with the user.

> _Requires PYTHONPATH set per the orchestrator's Runtime Environment section. If invoking this sub-skill directly (not via the orchestrator), run the detection loop first._

## Commands

```bash
# Full scaffold (recommended)
python3 -m specbuilder scaffold --project-name "<name>"

# With CI integration
python3 -m specbuilder scaffold --project-name "<name>" --ci github
python3 -m specbuilder scaffold --project-name "<name>" --ci gitlab

# PoC mode — minimal structure + spec/.poc sentinel
python3 -m specbuilder scaffold --project-name "<name>" --poc --confirm

# PoC with handover artifact generation — POC structure + handover = true in .specbuilder.toml
python3 -m specbuilder scaffold --project-name "<name>" --poc --handover --confirm

# Prototype mode — suspend change-control enforcement with auto-expiry
python3 -m specbuilder scaffold --prototype [--expires-in <duration>]

# End prototype mode and audit files changed
python3 -m specbuilder scaffold --end-prototype

# Upgrade poc/minimal → full
python3 -m specbuilder scaffold --upgrade

# Graduate POC → Full SDD (manual steps — see POC-to-Full Upgrade section below)
python3 -m specbuilder scaffold --upgrade-from-poc
```

**`--upgrade` (poc/minimal → full):** Upgrades a minimal or POC scaffold to a full SpecBuilder project structure.
Creates `spec/architecture/decisions/`, `spec/architecture/proposals/`, `spec/acceptance-criteria/`,
and `spec/changelog/`. Renders template files: `README.md`, `SCHEMA.md`,
`architecture/decisions/001-spec-driven-development.md`, and `acceptance-criteria/ac-readme.md`.
Upgrades `agent.md` to include the full workflow section. Rollback on failure: all partial writes
are restored automatically. Regenerates `spec/manifest.json` and `spec/README.md` on completion.
Safe to re-run: existing files are not overwritten.

## Additional Flags

| Flag | Description |
|------|-------------|
| `--lite` | Minimal file footprint: spec governance only (`spec/modules/`, `spec/INTAKE.md`, `.cortex/hooks/`, `agent.md`), no CI templates |
| `--from-handover PATH` | Initialize scaffold from a handover package at PATH |
| `--dry-run` | Print what would be created/modified without writing files |
| `--reason TEXT` | Reason text for prototype mode activation (used in audit trail) |
| `--template-style {standard,minimal}` | Template variant (default: standard) |
| `--protected-dirs DIR...` | Additional directories protected by change-control hook |
| `--spec-dir NAME` | Name of spec directory (default: spec) |
| `--confirm` | Confirm irreversible operations (required for `--upgrade-from-poc`) |

> **Note:** `spec/` is not protected by default. To protect spec files from
> unreviewed direct commits, pass `--protected-dirs spec/` at scaffold time.

    > **`--poc` and `--prototype` are mutually exclusive** — Cannot be combined. Specifying both raises an error (enforced at CLI argument parsing).

## CI Platform Prompt

> **Skip for Demo mode** — demo projects are temporary Snowflake sandboxes and are not connected to CI. Ask this question for Full SDD and PoC modes only.

During scaffolding, **ask the user** which CI platform to configure for spec drift checks:

```
Question: "Which CI platform should we configure for spec drift checks?"
Options:
  - None (local only)    — no CI template installed
  - GitHub Actions       — installs .github/workflows/spec-drift.yml
  - GitLab CI            — installs .gitlab-ci.yml
```

Pass the answer as `--ci none`, `--ci github`, or `--ci gitlab`. If the user doesn't specify and you detect `.github/` in the project, default to `github`. If `.gitlab-ci.yml` exists, default to `gitlab`. Otherwise CI scaffold is silently skipped — no prompt is issued. To enable CI on a project with no detected platform, pass `--ci github` or `--ci gitlab` explicitly.

## Full Mode Output

Creates this structure:

```
spec/
├── manifest.json
├── README.md
├── INTAKE.md
├── modules/
├── acceptance-criteria/
│   └── README.md
└── architecture/
    ├── SCHEMA.md
    ├── decisions/
    │   └── 001-spec-driven-development.md
    └── proposals/
.cortex/
├── hooks.json          ← pre-prompt hook for spec-first enforcement
└── hooks/
    └── change-control-gate.sh
.specbuilder.toml
agent.md                ← project agent configuration (explains the spec-driven workflow to CoCo at session start; acts as the project's AGENTS.md)
pyproject.toml          ← only if no package manager detected
```

## Package Manager Detection

Before generating `pyproject.toml`, checks for existing:
- `pyproject.toml`
- `requirements.txt`
- `Pipfile` / `Pipfile.lock`
- `poetry.lock`
- `uv.lock`

If any exist, `pyproject.toml` is **not** generated — the project already has dependency management.

## Hook Merging

If `.cortex/hooks.json` already exists, the scaffold **merges** the new hook entry into the existing array rather than overwriting. Existing hooks are preserved.

## Idempotency

Running scaffold twice on an already-scaffolded project:
- Detects existing `spec/` structure
- Reports "already scaffolded" with no changes
- Exits cleanly (no error)

## Environment Pre-Validation

> **Not implemented in the scaffold path.** The root `specbuilder/SKILL.md`
> §Supporting Modules section describes `environment.py` as providing pre-validation
> (Snowflake connectivity, role access, warehouse existence) during scaffold.
> `src/scaffold/` does not import or call `environment.py` — no pre-validation
> runs during scaffold. Connectivity checks must be performed manually before
> invoking scaffold on a Snowflake-connected project.

## Post-Scaffold

Once scaffolding completes, the project is ready for spec-driven work. The user can now describe requirements — the orchestrator will route to `generate-spec` for intake and spec authoring.

## Handover Mode (`--poc --handover`)

`--poc --handover` creates a POC scaffold and writes `handover = true` under `[project]`
in `.specbuilder.toml`. It also appends a `## Demo Configuration` block to `spec/INTAKE.md` with:
- **Target database** (required) — Snowflake DB for demo deployment
- **Sandbox schema prefix** (default: `_SPECBUILDER_DEMO`)
- **Test role name** (default: `SPECBUILDER_DEMO_ROLE`)
- **Source data references** (optional — validates SELECT access during Tier 4)

After scaffolding, run the full demo lifecycle with:
```bash
python3 -m specbuilder demo-run <module_num>
```

> **`--demo` is a deprecated alias** for `--poc --handover`. It still works but prints a
> deprecation warning. Use `--poc --handover` for new projects.

> **Quality settings are independent:** Unlike the old demo sub-mode, `--poc --handover` does
> NOT automatically elevate `validation_tier` or `max_retries`. To use elevated validation,
> add them explicitly to `.specbuilder.toml [quality]`:
> ```toml
> [quality]
> validation_tier = "verify"
> max_retries = 2
> ```

    > **`--poc --handover` and `--prototype` are mutually exclusive** — Cannot be combined.

## Prototype Mode

Temporarily suspends change-control hook enforcement so you can spike ideas without writing
a spec first. Activate via `--prototype` (creates `spec/.prototype` with 24h default expiry)
or set `SPECBUILDER_PROTOTYPE=1` for a session-scoped override (no sentinel, no expiry).
The hook emits a reminder on each bypassed edit; the sentinel auto-deletes on expiry.

Exit prototype mode and get an audit of modified files:
```bash
python3 -m specbuilder scaffold --end-prototype
```

## Mode Differences

Two distinct hooks are installed during scaffolding — they serve different purposes and have
different mode coverage:

**CoCo pre-prompt hook (`change-control-gate.sh`):** Installed in **all** modes (POC and
full). Written to `.cortex/hooks/change-control-gate.sh` and registered in
`.cortex/hooks.json`. Gates CoCo tool use before implementation changes are made, enforcing
spec-first discipline. Both `_scaffold_minimal()` (POC mode) and `_build_file_map()`
(full mode) include this file.

**Git manifest-regeneration hook:** Installed **only in full mode** by
`_install_git_precommit()`. Registers a git pre-commit hook that automatically regenerates
`spec/manifest.json` on every commit. POC mode does **not** install this hook — commits
in POC mode will not trigger automatic manifest regeneration.

To add the git manifest hook to an existing POC project: graduate to full mode via
`python3 -m specbuilder scaffold --upgrade-from-poc` (which runs the full scaffold path
including `_install_git_precommit()`), or install the hook manually.

## Mode Detection (`detect_mode`)

`detect_mode(project_root, spec_dir)` returns one of three strings:

| Return value | Condition |
|---|---|
| `"full"` | `spec/architecture/SCHEMA.md` exists (structural sentinel, takes highest precedence) |
| `"poc"` | `.specbuilder.toml` has `mode = "poc"`, OR `spec/.poc` sentinel exists, OR `spec/modules/` exists **and contains at least one `.md` file** |
| `"fresh"` | None of the above — includes the case where `spec/modules/` exists but is **empty** |

> **Empty-modules-dir semantics:** A `spec/modules/` directory with no `.md` files is treated as `"fresh"`, not `"poc"`. This prevents a bare empty directory (e.g. from `git init`) from being misidentified as an existing scaffold.

## POC-to-Full Upgrade

> ⚠️ **Before upgrading** — Confirm the user is ready to permanently graduate this
> project. Deleting `spec/.poc` and changing the toml mode are irreversible. Ask
> before proceeding.

Graduate a POC project to full SDD mode with a single atomic flag:

    python3 -m specbuilder scaffold --upgrade-from-poc

This flag:
1. Removes `spec/.poc` sentinel
2. Updates `.specbuilder.toml`: `mode = "poc"` → `mode = "full"`
3. Runs the standard upgrade pass to add any missing full-mode structure

If `spec/.poc` is not found, the command warns and proceeds with the upgrade pass only.
