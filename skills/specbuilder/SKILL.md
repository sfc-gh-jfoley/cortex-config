---
name: specbuilder
version: "1.17.1"
description: "Spec → review → accept → implement → verify. Guides a feature from intake through sign-off with enforced gates, acceptance criteria, and traceability at every phase."
triggers:
  - new feature spec
  - scaffold spec
  - spec intake
  - implement spec
  - batch implement
  - check drift
  - run acceptance tests
  - spec sign off
  - spec audit
  - validate artifacts
---

# Spec Architect (Orchestrator)

SpecBuilder helps teams adopt **spec-driven development**. Every feature starts as a specification — reviewed, accepted, and tracked — before implementation begins. This skill detects project state and user intent, then routes to the appropriate sub-skill.

**Skip SpecBuilder when:** the task is a one-off script, quick bug fix, or throwaway prototype where long-term traceability isn't needed. SpecBuilder adds value when requirements will be revisited, tested, or handed off.

## Tool Permissions

This skill uses: **Read**, **Bash**, **ask_user_question**

## Output

Delegates to the appropriate sub-skill. See each sub-skill's `## Output` section for what it produces.

## Stopping Points

- ⚠️ **First-use detection:** When no `spec/` and no `.specbuilder.toml` are found, run the
  two-step scaffold flow (see dispatch table):
  1. Call `ask_user_question` — PoC Mode or Full SDD Mode.
     PoC selected → `scaffold-spec --poc` immediately. Flow ends.
  2. Full SDD selected → call a second `ask_user_question` — Standard or Minimal files.
     Standard → `scaffold-spec`; Minimal → `scaffold-spec --lite`.
  Do **not** present a generic activity menu. Do **not** ask about quality profile (users
  set `strict` later via `.specbuilder.toml` if needed). No other questions before scaffold.
- ⚠️ **Ambiguous intent:** If the user's request doesn't clearly match a routing row in Context Detection, ask before loading any sub-skill.
- ⚠️ **In-review module gate:** When a module status is `in-review`, STOP and present the review summary to the user before routing. Do not auto-proceed — wait for an explicit decision: accept (→ set status `accepted`, route to `implement-spec`) or request changes (→ route to `generate-spec` to revise).
- ⚠️ **`generate-manifest` failure** — If `python3 -m specbuilder generate-manifest` exits with a
   non-zero status at any point in the session, stop and do not proceed to the next phase. Run
   `python3 -m specbuilder audit` to identify the malformed frontmatter field, fix it, and
   re-run `generate-manifest` before continuing. See §5 for remediation steps.

## Runtime Environment

Before running **any** `python3 -m specbuilder` command, detect and set the Python path. Run this once at the start of the session:

```bash
for d in .cortex/skills . vendor; do
  [ -d "$d/specbuilder" ] && export PYTHONPATH="$d:${PYTHONPATH:-}" && break
done
```

This handles both customer projects (skill at `.cortex/skills/specbuilder/`) and development repos (skill at root `./specbuilder/`). All subsequent `python3 -m specbuilder ...` commands will work without path issues.

**If the detection fails** (no `specbuilder/` directory found in any search path), stop and tell the user: "SpecBuilder is not installed. See the skill README for installation instructions."

**If any `python3 -m specbuilder` command fails with `ModuleNotFoundError`:** The PYTHONPATH detection loop was not run or ran from the wrong directory. Re-run the loop from the project root before retrying the command.

## Mode and Profile Reference

Values sourced from `specbuilder/src/config.py` `QUALITY_PROFILES`. Do not override here — edit config.py for threshold/tier changes.

| Mode / Profile | Threshold | max_retries | skip_checks | validation_tier | self_correct | Activation |
|----------------|-----------|-------------|-------------|-----------------|--------------|------------|
| **poc** | 50 | 0 | `testability`, `edge_case_traceability` | compile | false | `spec/.poc` sentinel OR `[project].mode = "poc"` in `.specbuilder.toml` |
| **full** (default) | 75 | 0 | (none) | dry-run | false | `[project].mode = "full"` or no config |
| **strict** | 90 | 2 | (none) | verify | true | `[quality].profile = "strict"` in `.specbuilder.toml` |
| **prototype** | 50 | 0 | `testability`, `edge_case_traceability` | compile | false | `--prototype` scaffold flag; mutually exclusive with `--poc` |

**Profile resolution order** (highest priority wins):
1. `SPECBUILDER_QUALITY_PROFILE` environment variable
2. `.specbuilder.toml` `[quality].profile` field
3. Auto-detection: `spec/.poc` sentinel exists → poc profile
3a. `[project].mode = "poc"` in `.specbuilder.toml`
4. Default: `full`

**Handover flag** (`[project].handover = true` in `.specbuilder.toml`): Enables automatic generation of a customer handover artifact on `release sign-off`. Set via `--poc --handover` at scaffold time (or the deprecated `[project].sub_mode = "demo"` TOML key, which maps to `[project].handover = true`).

## Workflow

### 1. Context Detection

Check the project state and route accordingly:

> **Row evaluation order:** Rows are evaluated top-to-bottom. State-based rows (left column describes project state) take priority over intent-based rows (left column describes what the user said). **The first matching row wins; subsequent matches are ignored.** Do not reorder rows.

| Condition | Route to |
|-----------|----------|
| No `spec/` AND no `.specbuilder.toml` | **Step 1** — Call `ask_user_question`:<br>**PoC Mode** — "Fast iteration, auto-accepted specs, no CI hooks. Use for exploration or demos." → `scaffold-spec --poc`<br>**Full SDD Mode** — "Full governance scaffold, quality gates. Use for production deliverables." → **Step 2**<br><br>**Step 2 (Full SDD only)** — Call `ask_user_question`:<br>**Standard** — "Full file set including CI templates and agent scaffolding." → `scaffold-spec`<br>**Minimal files** — "Spec governance only; skips CI templates and agent files. Use when adding SpecBuilder to an existing repo." → `scaffold-spec --lite`<br><br>No other options at either step. |
| No `spec/` but `.specbuilder.toml` exists | `scaffold-spec` (mode already configured) |
| `spec/` exists, module status = `in-review` | Present the spec to the user for review — accept → set status `accepted`, route to `implement-spec`; changes requested → route to `generate-spec` to revise |
| `spec/` exists, module status = `implemented` | Project-complete state — run `audit-spec` to verify health |
| `spec/` exists but no modules in `spec/modules/` | `generate-spec` |
| User describes a requirement ("I need…", "new module", fills INTAKE.md) | `generate-spec` |
| `spec/` exists, module status = `draft` | `generate-spec` — spec is incomplete; finish and advance to `in-review` before implementing |
| Accepted spec exists, no implementation artifacts in `impl/` | `implement-spec` |
| User says "implement spec" / "implement module" | `implement-spec` |
| User says "drift" / "stale" / "check spec" | `verify-spec` → Drift Detection section |
| User says "run tests" / "acceptance tests" | `verify-spec` → Acceptance Testing section |
| User says "sign off" | `verify-spec` → Sign-Off Workflow section |
| User says "validate artifacts" / "validate module" / "validate for module N" | `verify-spec` → Artifact Validation (Tiered) section |
| User says "propose" / "new proposal" / "EXT-" / "write a proposal" | `propose-spec` |
| User says "spec audit" / "audit" / "outdated" / "project health" / "upgrade config" | `audit-spec` |
| User says "demo" / "build a demo" / "demo spec" AND no `spec/` exists | `scaffold-spec --poc --handover` |
| User says "prototype" / "enable prototype" / "start prototype" / "bypass hook" | `scaffold-spec` → Prototype Mode section |
| User says "batch implement" / "implement all proposals" / references 2 or more proposals | `checkpoint-spec` to initialize batch and track waves; then dispatch `implement-spec` for each proposal in dependency order |
| User says "checkpoint" / "batch status" / "resume batch" / "record wave" / "init batch" | `checkpoint-spec` |
| User wants to scaffold a new POC project from a demo handover artifact; keywords: "handover consumer", "scaffold from handover", "consume handover", "handover file" | → `handover-consumer` |
| Ambiguous intent | Ask the user what they'd like to do |

> **Demo projects:** Once scaffolded, demo projects follow the same state-based routing as any other project. No special handling needed.

> **In-review gate override:** When a module is `in-review` (row 3), the routing table routes to
> the review flow regardless of any additional matching rows — including intent-based rows such as
> "new module" (row 6). This is intentional: an open review must be resolved before new work
> begins. To unblock: accept the in-review module (set status → `accepted`, route to
> `implement-spec`) or request changes (route to `generate-spec` to revise) before re-stating new-
> module intent.

> **Status transitions:** `generate-spec` produces specs at `status: draft`. Transitioning
> to `in-review` is a **manual step** — update the spec's frontmatter `status` field.
> The orchestrator then detects `in-review` and routes it to the review flow above.

## CLI Utility Commands

The following commands are invoked directly from the CLI and are **not routed via sub-skill
dispatch**. They operate on the current project state without requiring the Context Detection
routing table.

| Command | Purpose | Notes |
|---------|---------|-------|
| `scaffold` | Initialize spec directory structure | Routes to `scaffold-spec` |
| `generate-module` | Generate a spec module from intake | Routes to `generate-spec` |
| `generate-index` | Regenerate manifest.json and README tables | Deprecated alias for `generate-manifest` |
| `generate-manifest` | Regenerate manifest.json and README tables | Preferred over `generate-index` |
| `sync-ac-files` | Create missing AC files and append missing AC sections | Run after `generate-manifest` |
| `bump-version` | Update specbuilder/SKILL.md version from latest changelog | Dev-repo only |
| `regenerate-readme` | Regenerate root README.md auto-sections between sentinel markers | |
| `discover-skills` | Identify relevant CoCo skills for the current spec | |
| `detect-drift` | Compare spec vs. implementation state | |
| `diff` | Semantic diff between spec versions | |
| `implement` | Generate stubs + dispatch plan | Use `--stubs-only` then `--confirm` |
| `validate-artifacts` | Validate implementation artifacts (tiered) | |
| `demo-run` | Execute a demo workflow end-to-end | |
| `demo-handover` | Generate demo handover artifact (sanitized) | |
| `grant-test` | Discover minimum grants via iterative tester-role loop | |
| `audit` | Audit spec completeness and consistency | |
| `test-acceptance` | Run acceptance criteria checks | |
| `release` | Bump version and create changelog entry | |
| `sign-off` | Sign off a module (status → implemented + auto-changelog) | Requires `--confirm` in non-dry-run mode; exits 1 if omitted (see EXT-203) |
| `quality` | Assess spec quality (vagueness, testability) | |
| `ci` | CI integration (drift check, promote, PR context) | |
| `summary` | Generate POC summary artifact | |
| `ac-coverage` | Report acceptance criteria test coverage | |
| `checkpoint` | Execution checkpoint for multi-proposal batches | `--json`: emit structured JSON output (use with `--status`) |
| `handover-consumer` | Scaffold a new POC project from a demo handover artifact | |
| `propose` | Pre-flight checks for new proposals (validate, check-collision, check-overlap, check-range) | |

> **Note:** `generate-index` is a deprecated alias for `generate-manifest`. It no longer bumps
> `specbuilder/SKILL.md` version — use `bump-version` explicitly during releases.

These commands can be invoked at any point in the workflow. They do not transition module state
and are safe to run repeatedly.

### 2. Pre-Flight Check

> Run Context Detection first to identify the routing target, then Pre-Flight Check to determine the path.

**Step 0 — detect active profile:**
Read `.specbuilder.toml` before choosing a path. If `[quality].profile = "strict"`, apply the Strict path below regardless of other flags.

---

**POC path** (`spec/.poc` exists OR `.specbuilder.toml` has `[project].mode = "poc"`):
1. Check if `spec/` exists (if not → `scaffold-spec`)
2. Route directly to the relevant sub-skill — skip manifest read, skip Governance section
3. **Handover flag:** if `.specbuilder.toml` has `[project].handover = true`, `release sign-off` will auto-generate the handover artifact. Quality settings (validation_tier, max_retries) are independent — configure them directly in `[quality]` if elevated checks are needed.

**Full path** (default — `[project].mode = "full"` or no config, and `[quality].profile` is not `"strict"`):
1. Check if `spec/` exists in the project root
2. Check if `.specbuilder.toml` exists in the project root
3. Read `spec/manifest.json` (if exists) — provides module list, statuses, dependencies
4. List `spec/modules/` directory contents

**Strict path** (`[quality].profile = "strict"` in `.specbuilder.toml`):
1. Follow Full path steps 1–4 (strict projects always read the manifest)
2. Apply elevated quality parameters throughout: threshold=90, max_retries=2, validation_tier=verify
3. Do NOT skip quality gate or validation steps — strict disables all skip_checks
4. Self-correction is enabled: on quality gate failure, the sub-skill attempts up to 2 corrective retries before surfacing findings to the user

**Prototype path** (`--prototype` flag used at scaffold time — `.specbuilder.toml` has `[quality].profile = "prototype"`):
1. Follow Full path steps 1–4
2. Apply prototype quality parameters: threshold=50, max_retries=0, skip_checks=[testability, edge_case_traceability], validation_tier=compile
3. Prototype projects use compile-tier validation only; sandbox DDL deployment is not performed

Otherwise (when `spec/` exists and on full or strict path), use manifest data for routing decisions without additional file reads.

### 3. Governance

> **POC mode:** Skip the Governance section below. POC projects opt out of change control, changelog tracking, and multi-module protocols.

- Spec is the source of truth — code that disagrees with spec is wrong.
- Update spec before code when changing inputs, outputs, logic, or ACs.
- New functionality requires a new module (route to `generate-spec`).
- Non-behavioral changes (refactoring, perf) proceed without spec update.
- Acceptance criteria must be testable (programmatic or clear manual procedure).

**Conditional references (load only when needed):**
- For multi-module implementation ("implement all", multiple modules): read `specbuilder/refs/multi-module-protocol.md` (customer projects: `.cortex/skills/specbuilder/refs/multi-module-protocol.md`)
- Before ending a session that modified your implementation files with functional or behavioral changes (not test-only, doc-only, formatting-only, or trivial config-only changes): read `specbuilder/refs/changelog-rules.md` (customer projects: `.cortex/skills/specbuilder/refs/changelog-rules.md`)

### 4. Routing

Read the SKILL.md for the relevant sub-skill using the `Read` tool — do **not** use the `skill` tool, as sub-skills are not registered at the top level. In customer projects the path is `.cortex/skills/specbuilder/skills/<sub-skill>/SKILL.md`; in the development repo it is `specbuilder/skills/<sub-skill>/SKILL.md`.

- `scaffold-spec` — initialize project structure
- `generate-spec` — intake, clarify, produce spec + ACs
- `propose-spec` — author proposals with validation and impact checks
- `implement-spec` — stub generation, batch execution, validation
- `verify-spec` — drift detection, acceptance tests, sign-off
- `audit-spec` — project health checks, upgrade proposals
- `checkpoint-spec` — batch wave tracking and resumption for 2 or more proposal implementations
- `handover-consumer` — scaffold a new POC project from a demo handover artifact

> **Taxonomy Note:** SpecBuilder uses two separate domain taxonomies that must not be unified:
>
> - **`AGENT_REGISTRY`** (`src/agents/registry.py`) — Maps implementation agent domains to CoCo skills. Used by `dispatch.py` to route implementation work.
> - **`domain-hints.json`** (`src/domain-hints.json`) — Keyword→domain mapping for `discover_skills.py` relevance scoring. Separate namespace; domain names intentionally differ from `AGENT_REGISTRY` keys.
>
> When extending either taxonomy, update only the relevant file. Do not attempt to unify keys.

> **Dispatch asymmetry:** Three commands (`discover-skills`, `generate-module`, `detect-drift`) are dispatched via `runpy.run_module()` rather than `module.main()`. These modules use the `if __name__ == "__main__":` pattern. All other commands use a named `main()` entry point. A missing `if __name__` block in these three modules produces a silent no-op rather than an error. The governing structure is `_HAS_MAIN` in `specbuilder/__main__.py` (lines 102–126): a set of command names that expose a `main()` entry point. Commands absent from `_HAS_MAIN` are dispatched via `runpy`. When adding a new command, add it to `_HAS_MAIN` if it has a `main()` entry point; omitting it will silently route the command through `runpy`.

## Supporting Modules

### `src/dispatch.py`
Routes implementation work to CoCo sub-skills based on the artifact type declared in the spec Output section. Reads `AGENT_REGISTRY` from `src/agents/registry.py` which maps implementation domains (e.g. `"data-engineering"`, `"security"`, `"app-dev"`, `"ml"`, `"fallback"`) to their corresponding CoCo skill handles. Called by `implement-spec` after stub generation.

### `src/config.py` — `get_effective_profile()`
Delegates to `get_active_profile()` — single-level resolution, no sub-mode merging.

### `src/environment.py`
Parses the "Existing Environment" section of `INTAKE.md` to extract declared Snowflake objects (databases, schemas, tables, views, roles, warehouses, stages). Generates `SHOW` queries for each object type and caches validation results to `.specbuilder/environment.json`. Called during `handover-consumer` and `scaffold-spec` to pre-validate the target environment before scaffold proceeds.

## 5. Post-Implementation Index Rebuild

After any session that creates or modifies artifacts (modules, ACs, proposals), rebuild the manifest and sync AC files:

```bash
python3 -m specbuilder generate-manifest && python3 -m specbuilder sync-ac-files
```

Omitting this causes manifest drift and AC file staleness when multiple artifacts are generated in sequence.

> **Deprecated:** `generate-index` is a compatibility alias for `generate-manifest`. It no
> longer bumps `specbuilder/SKILL.md` version — use `bump-version` explicitly during releases.

> **`generate-manifest` operations (3 per invocation):**
>
> 1. **Frontmatter validation** — validates ALL spec files project-wide before writing
>    anything. If any file has malformed frontmatter, `generate-manifest` exits with code 1
>    and writes **nothing** (no manifest, no README).
>    ⚠️ **If `generate-manifest` exits with an error**, run:
>    ```
>    python3 -m specbuilder audit
>    ```
>    to identify the malformed frontmatter field, fix it, then re-run `generate-manifest`.
> 2. **Writes `spec/manifest.json`** (prints: `Generated spec/manifest.json`).
> 3. **Writes `spec/README.md` module/proposal tables** (prints: `Regenerated spec/README.md`).

## Drift Detection

`python3 -m specbuilder detect-drift [--format markdown|json] [--staleness-days N]
[--no-git]` — checks spec-vs-implementation alignment: `accepted`/`implemented` specs
with no impl files, post-sign-off code changes, stale `draft`/`in-review` specs, missing
AC files, orphan AC files, and unclaimed impl files. Use `--format json` for CI pipelines.

## Checkpoint Memory

`checkpoint-spec` tracks batch wave execution across sessions using two mechanisms:

1. **Cortex memory** (primary cross-session handoff) — Wave completion events recorded after each wave for resumption across sessions. Use `cortex memory remember` after each `--wave` call; see `refs/checkpoint-protocol.md`.
2. **Committed proposal frontmatter** (durable reference / recovery fallback) — Each proposal's `status` field is updated as waves complete. Readable from disk if cortex memory is unavailable.

**Recovery:** If cortex memory is unavailable mid-batch, reconstruct execution state by scanning proposal frontmatter statuses:

```bash
grep -r "^status:" spec/architecture/proposals/*.md | grep -v "implemented"
```

This lists all proposals that have not yet reached `status: implemented`, giving a complete picture of remaining batch work without relying on cortex memory.

> **CI prerequisite:** The scaffolded CI templates use `pip install -e .` which requires a `pyproject.toml` (or `setup.py`) at the repository root. If your project does not expose a Python package, replace with `pip install specbuilder`.
