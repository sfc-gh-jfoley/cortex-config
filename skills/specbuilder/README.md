# SpecBuilder

SpecBuilder helps you adopt spec-driven development. Every feature starts as a written specification — reviewed and accepted — before any code is written. This ensures requirements are clear, acceptance criteria are testable, and implementation matches intent.

## Installation

From your project root:

```bash
git clone --depth 1 https://github.com/sfc-gh-skaramarti/specbuilder.git /tmp/specbuilder-install
mkdir -p .cortex/skills
cp -r /tmp/specbuilder-install/specbuilder .cortex/skills/specbuilder
rm -rf /tmp/specbuilder-install
```

This installs the skill into `.cortex/skills/specbuilder`. CoCo will detect it automatically on next invocation.

To update to the latest version, re-run the same commands — it overwrites the existing installation.

## How to Use

Talk to CoCo naturally. SpecBuilder activates when you say things like:

| You say... | What happens |
|------------|--------------|
| "scaffold spec" or "set up spec structure" | Initializes your project with a `spec/` directory |
| "new module" or "I need a feature for..." | Guides you through requirements → produces a formal spec |
| "check drift" or "are specs up to date?" | Reports where implementation has diverged from specs |
| "run acceptance" or "test module 3" | Runs acceptance criteria checks and reports results |
| "audit my project" or "is my spec setup current?" | Detects stale config, missing hooks, and outdated profiles; can auto-fix |
| "validate artifacts for module 2" | Runs tiered validation (compile → dry-run → smoke → verify) against a module's artifacts |

You don't need to run any commands directly — CoCo handles execution. Just describe what you need.

## What to Expect

When you request a new feature, SpecBuilder follows a gated workflow:

1. **Clarification** — CoCo asks 2-5 targeted questions to fill gaps in your requirement
2. **Spec generation** — A formal spec is written and presented for your review
3. **Acceptance gate** — You approve (or request changes) before any code is written
4. **Implementation** — CoCo builds artifacts following the spec
5. **Verification** — Acceptance criteria are checked; you sign off

The key principle: nothing gets built until you've seen and approved the spec.

## Modes

- **Full** (default) — Complete governance: specs, acceptance criteria, architecture decisions, changelog tracking
- **Lite** — Minimal structure for small projects (just specs + change-control hook)
- **POC** — Time-boxed engagements: lite structure with `poc` quality profile, auto-generates a `POC-SUMMARY.md` at sign-off
- **Demo** — POC plus auto-deploy/verify lifecycle and customer handover package generation (`--demo` scaffold flag)
- **Prototype** — Temporarily suspends change-control enforcement for rapid exploration (auto-expires)

## More Information

- Workflow details: see `SKILL.md` in this directory
- Spec format and conventions: see `spec/architecture/SCHEMA.md` (after scaffolding)
- Module index and status: see `spec/README.md` (auto-generated)
