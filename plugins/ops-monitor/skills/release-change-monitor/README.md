# Release Change Monitor — Cortex Code Skill

A Cortex Code skill that proactively monitors Snowflake release notes for behavior changes that could break data pipelines, generates impact assessments, remediation plans, and test strategies.

## Why This Exists

Snowflake ships ~10 **Behavior Change Bundles** per year (monthly, skipping Nov/Dec). Each bundle follows a 3-month lifecycle:

1. **Month 1** — Disabled by Default (opt-in testing)
2. **Month 2** — Enabled by Default (opt-out grace period)
3. **Month 3** — Generally Enabled (locked, no override)

Changes in these bundles can silently break pipelines if not caught early. This skill automates the detection-to-remediation workflow.

## What It Does

| Phase | Description |
|-------|-------------|
| **1. Fetch & Parse** | Scrapes Snowflake BCR bundle documentation pages and extracts structured change data |
| **2. Inventory Pipelines** | Queries your Snowflake account to catalog tasks, dynamic tables, procedures, UDFs, streams, pipes, and views |
| **3. Impact Analysis** | Cross-references behavior changes against your pipeline inventory using keyword matching, query history analysis, and optional AI classification |
| **4. Remediation Plan** | Generates before/after SQL diffs, priority scores, and deadlines for each affected object |
| **5. Test Strategy** | Produces a step-by-step test plan using `SYSTEM$ENABLE_BEHAVIOR_CHANGE_BUNDLE` in a dev/QA account with zero-copy clones |

## Installation

Copy this folder into your Cortex Code skills directory:

```
~/.snowflake/cortex/skills/release-change-monitor/
```

## File Structure

```
release-change-monitor/
├── .my_skill                  # Marks this as a personal skill
├── SKILL.md                   # Main skill prompt (router + workflow)
├── skill_evidence.yaml        # Test scenarios and validation notes
├── README.md                  # This file
└── references/
    ├── scrape-workflow.md     # Phase 1: How to fetch & parse release notes
    ├── impact-analysis.md    # Phase 3: Severity scoring and cross-referencing
    ├── remediation-plan.md   # Phase 4: Fix patterns and priority assignment
    └── test-strategy.md      # Phase 5: BCR bundle testing workflow
```

## Usage

Trigger the skill with any of these prompts in Cortex Code:

| Prompt | What runs |
|--------|-----------|
| "What changed in the latest Snowflake release?" | Phase 1 only (quick check) |
| "Will the next BCR bundle break my pipelines?" | Full scan (Phases 1-5) |
| "Run impact analysis for bundle 2026_03 against PROD_DB" | Phases 2-3 scoped to a database |
| "Generate a test plan for BCR bundle 2026_03" | Phase 5 only |
| "Show remediation status for bundle 2026_02" | Loads previous scan from memory |

## Prerequisites

- **Snowflake account access** via Cortex Code
- **ACCOUNTADMIN** role (required for `SYSTEM$ENABLE_BEHAVIOR_CHANGE_BUNDLE`)
- **SNOWFLAKE.ACCOUNT_USAGE** access (for query history analysis)
- A **non-production account** is recommended for bundle testing (Phase 5)

## Recommended Cadence

| When | Action |
|------|--------|
| Monthly (when new BCR bundle drops) | Full scan: all 5 phases |
| Weekly (optional) | Quick check: Phase 1 only for deprecation notices |
| On-demand | Before major deployments or when alerted to a specific change |

## Limitations

- Release notes are fetched via HTML scraping (`web_fetch`), not a structured API. Page structure changes may require updates to the scrape workflow.
- Impact analysis cannot inspect encrypted/obfuscated stored procedures.
- Driver and connector changes (client-side) are flagged but cannot be verified from within Snowflake.
- Large accounts (thousands of objects) should scope scans to specific databases/schemas.
