# cortex-agent-optimization

Iterative Snowflake Cortex Agent optimization using dev/test eval splits and statistical rigor.

## When to Use This Skill

Use this skill when you want to systematically improve a Cortex Agent's accuracy using:
- **Dev/test split** — keeps your test set unseen until final acceptance
- **Multi-run evaluations** — averages across N runs to reduce noise
- **Accept/reject decisions** — data-driven criteria, not gut feel
- **Flag sweep** — compare BASE vs AGENTIC vs FASTPATH_OFF variants

## Related Bundled Skills

Snowflake ships a bundled `cortex-agent` skill with sub-skills for agent lifecycle management. Here's how this custom skill relates:

| Capability | Bundled `cortex-agent` | This Skill |
|------------|------------------------|------------|
| Create/edit agent | ✅ Full lifecycle (create, alter, drop) | Reads current spec, edits markdown source |
| Run evaluations | ✅ `adhoc-testing-for-cortex-agent` | ✅ `EXECUTE_AI_EVALUATION` + YAML-on-stage |
| Optimization loop | ✅ `optimize-cortex-agent` (single run) | ✅ DEV/TEST split, N runs, statistical mean/stddev |
| Dataset curation | ✅ `dataset-curation` (Streamlit UI) | Manual + can call bundled for curation |
| Flag comparison | ❌ Not available | ✅ 3-variant A/B test (BASE/AGENTIC/FASTPATH_OFF) |
| Accept/reject | Manual | ✅ Automated: DEV gain + TEST hold = accept |
| Stat significance | ❌ Single run | ✅ Mean ± stddev across N runs per split |

**When to use bundled `cortex-agent` instead:**
- Creating or dropping agents
- Quick one-off test without a structured eval dataset
- Dataset curation from production Events data (Streamlit UI)

**When to use this skill:**
- You have a real eval dataset and want structured optimization
- You need to prevent test leakage (dev/test discipline matters)
- You want to compare flag configs with statistical rigor

## Workflow Overview

```
SETUP → baseline → OPTIMIZE (iterate) → REVIEW (accept/reject) → FLAG SWEEP (optional)
```

Each phase is a sub-skill under the subdirectories. See `SKILL.md` for intent detection and routing.

## Test Fixtures

See `test-fixture-example/` for a complete working validation setup including:
- `fixture_example.yaml` — fixture demonstrating SETUP intent routing
- `build_example.sh` — stub illustrating how the build script is invoked

## Files

```
cortex-agent-optimization/
├── SKILL.md                   — entry point + intent router
├── README.md                  — this file
├── references/setup.md             — scaffold workspace + baseline eval
├── references/optimize.md          — run an optimization iteration
├── references/review.md            — accept/reject decision logic
├── references/eval-data.md         — dataset management + split validation
├── references/flag-sweep.md        — 3-variant flag comparison
├── references/feedback-pipeline.md — feedback ingestion to eval dataset
├── references/                — eval config templates, polling patterns, project structure
├── scripts/
│   └── build_agent_spec.py    — assembles agent/*.md → deploy.sql
└── test-fixture-example/      — example fixture + build stub
```
