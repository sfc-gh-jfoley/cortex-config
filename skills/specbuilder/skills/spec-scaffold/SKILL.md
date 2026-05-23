---
name: spec-scaffold
version: "1.13.0"
description: "Initialize spec-driven project structure with schemas, templates, hooks, and generation scripts"
---

# Spec Scaffold

Initializes a project for spec-driven development by creating the `spec/` directory tree, schemas, templates, hooks, and supporting configuration. This is always the first step — other sub-skills require the scaffolded structure to exist.

## Tool Permissions

This skill uses: **Read**, **Write**, **Edit**, **Bash**

## When to Run

- Fresh project with no `spec/` directory
- User explicitly asks to scaffold or initialize spec structure
- The orchestrator (`spec-architect`) routes here because `spec/` is missing

**Mode passthrough from orchestrator:** When the orchestrator detects first-use (no `spec/` and no `.specbuilder.toml`), it prompts the user to choose PoC or Production mode before routing here. The orchestrator passes the mode selection through:
- **PoC selected** → run with `--poc` flag (creates lite structure + `spec/.poc` sentinel + `.specbuilder.toml` with `mode = "poc"`)
- **Production selected** → run with default full scaffold (no special flag)

If the user invokes scaffold directly (bypassing the orchestrator), the existing `--lite` and `--poc` flags remain available as documented below.

## Commands

```bash
# Full scaffold (recommended)
python3 -m specbuilder scaffold --project-name "<name>"

# With CI integration
python3 -m specbuilder scaffold --project-name "<name>" --ci github
python3 -m specbuilder scaffold --project-name "<name>" --ci gitlab

# Lite mode — minimal structure for quick starts
python3 -m specbuilder scaffold --project-name "<name>" --lite

# Upgrade lite → full
python3 -m specbuilder scaffold --upgrade
```

## CI Platform Prompt

During scaffolding, **ask the user** which CI platform to configure for spec drift checks:

```
Question: "Which CI platform should we configure for spec drift checks?"
Options:
  - None (local only)    — no CI template installed
  - GitHub Actions       — installs .github/workflows/spec-drift.yml
  - GitLab CI            — installs .gitlab-ci.yml
```

Pass the answer as `--ci none`, `--ci github`, or `--ci gitlab`. If the user doesn't specify and you detect `.github/` in the project, default to `github`. If `.gitlab-ci.yml` exists, default to `gitlab`. Otherwise ask.

## Full Mode Output

Creates this structure:

```
spec/
├── manifest.json
├── README.md
├── INTAKE.md
├── modules/
├── acceptance-criteria/
├── changelog/
└── architecture/
    ├── SCHEMA.md
    ├── decisions/
    └── proposals/
.cortex/
└── hooks.json          ← pre-prompt hook for spec-first enforcement
agent.md                ← project agent configuration
pyproject.toml          ← only if no package manager detected
```

## Lite Mode Output

Minimal structure for rapid bootstrapping:

```
spec/
├── modules/
└── INTAKE.md
.cortex/
└── hooks.json
```

Use `--upgrade` later to expand lite into full structure.

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

## Post-Scaffold

Once scaffolding completes, the project is ready for spec-driven work. The user can now describe requirements — the orchestrator will route to `spec-generate` for intake and spec authoring.
