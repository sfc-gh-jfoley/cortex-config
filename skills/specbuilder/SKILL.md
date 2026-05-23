---
name: specbuilder
version: "1.13.0"
description: "Spec-driven development orchestrator — routes to the right sub-skill based on project state and user intent"
triggers:
  - scaffold spec
  - new module
  - spec intake
  - check drift
  - run acceptance
  - propose
  - new proposal
  - build a demo
  - demo spec
  - specbuilder
  - spec-architect
  - implement
  - build it
  - sign off
  - audit
  - spec audit
---

# Spec Architect (Orchestrator)

SpecBuilder helps teams adopt **spec-driven development**. Every feature starts as a specification — reviewed, accepted, and tracked — before implementation begins. This skill detects project state and user intent, then routes to the appropriate sub-skill.

**Skip SpecBuilder when:** the task is a one-off script, quick bug fix, or throwaway prototype where long-term traceability isn't needed. SpecBuilder adds value when requirements will be revisited, tested, or handed off.

## Tool Permissions

This skill uses: **Read**, **Bash**, **ask_user_question**, **Skill** (to load sub-skills)

## Stopping Points

- ⚠️ **First-use detection:** Before routing to `spec-scaffold`, present the PoC vs Production prompt. Do not scaffold without user confirmation.
- ⚠️ **Ambiguous intent:** If the user's request doesn't clearly match a routing row in Context Detection, ask before loading any sub-skill.

## Runtime Environment

Before running **any** `python3 -m specbuilder` command, detect and set the Python path. Run this once at the start of the session:

```bash
for d in .cortex/skills . vendor; do
  [ -d "$d/specbuilder" ] && export PYTHONPATH="$d:${PYTHONPATH:-}" && break
done
```

This handles both customer projects (skill at `.cortex/skills/specbuilder/`) and development repos (skill at root `./specbuilder/`). All subsequent `python3 -m specbuilder ...` commands will work without path issues.

**If the detection fails** (no `specbuilder/` directory found in any search path), stop and tell the user: "SpecBuilder is not installed. See the skill README for installation instructions."

## Context Detection

Check the project state and route accordingly:

| Condition | Route to |
|-----------|----------|
| No `spec/` AND no `.specbuilder.toml` | Prompt user: PoC or Production? Then `spec-scaffold` with appropriate mode |
| No `spec/` but `.specbuilder.toml` exists | `spec-scaffold` (mode already configured) |
| `spec/` exists but no modules in `spec/modules/` | `spec-generate` |
| User describes a requirement ("I need…", "new module", fills INTAKE.md) | `spec-generate` |
| Accepted spec exists, no implementation artifacts in `impl/` | `spec-implement` |
| User says "implement" / "build it" | `spec-implement` |
| User says "drift" / "stale" / "check spec" / "test" / "sign off" | `spec-verify` |
| User says "propose" / "new proposal" / "EXT-" / "write a proposal" | `spec-propose` |
| User says "audit" / "spec audit" / "outdated" / "project health" / "upgrade config" | `spec-audit` |
| User says "demo" / "build a demo" / "demo spec" | `spec-scaffold --demo` |
| Ambiguous intent | Ask the user what they'd like to do |

## Pre-Flight Check

> Run Context Detection first to identify the routing target, then Pre-Flight Check to determine fast path vs full path.

**Fast path (POC mode or single-module intent):**
If `spec/.poc` exists OR `.specbuilder.toml` has `mode = "poc"`, OR the user names exactly one module/feature:
1. Check if `spec/` exists (if not → `spec-scaffold`)
2. Route directly to the relevant sub-skill — skip manifest read, skip Governance section

**Full path (production mode or multi-module intent):**
If user says "implement all", "build everything", or references multiple modules:
1. Check if `spec/` exists in the project root
2. Check if `.specbuilder.toml` exists in the project root
3. Read `spec/manifest.json` (if exists) — provides module list, statuses, dependencies
4. List `spec/modules/` directory contents

**⚠️ STOP — First-use detection:** If `spec/` is missing AND no `.specbuilder.toml` exists, this is a first-time user. Before routing to `spec-scaffold`, prompt:

```
Question: "What kind of engagement is this?"
Options:
  - PoC / Exploration  — "Lightweight mode: minimal ceremony, auto-generated summaries, relaxed quality gates. Best for 2-5 day proof-of-concept engagements."
  - Production         — "Full governance: complete spec structure, strict quality gates, change control. Best for production implementations."
```

- If the user selects **PoC**, route to `spec-scaffold` with `--poc` flag (creates `spec/.poc` sentinel + lite structure)
- If the user selects **Production**, route to `spec-scaffold` with default full mode
- If `spec/` is missing but `.specbuilder.toml` already exists, skip the prompt — the mode is already configured. Route to `spec-scaffold` directly.

Otherwise (when `spec/` exists and full path), use manifest data for routing decisions without additional file reads.

## Governance

> **POC mode:** Skip the Governance section below. POC projects opt out of change control, changelog tracking, and multi-module protocols.

- Spec is the source of truth — code that disagrees with spec is wrong.
- Update spec before code when changing inputs, outputs, logic, or ACs.
- New functionality requires a new module (route to `spec-generate`).
- Non-behavioral changes (refactoring, perf) proceed without spec update.
- Acceptance criteria must be testable (programmatic or clear manual procedure).

**Conditional references (load only when needed):**
- For multi-module implementation ("implement all", multiple modules): read `specbuilder/refs/multi-module-protocol.md`
- Before ending a session that modified `specbuilder/src/` or `specbuilder/skills/`: read `specbuilder/refs/changelog-rules.md`

## Routing

Load the relevant sub-skill from `specbuilder/skills/` based on the detection table above:

- `spec-scaffold` — initialize project structure
- `spec-generate` — intake, clarify, produce spec + ACs
- `spec-propose` — author proposals with validation and impact checks
- `spec-implement` — stub generation, batch execution, validation
- `spec-verify` — drift detection, acceptance tests, sign-off
- `spec-audit` — project health checks, upgrade proposals
