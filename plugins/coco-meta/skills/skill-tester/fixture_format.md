---
name: skill-tester-fixture-format
description: YAML schema for skill test fixtures — defines inputs, stopping-point responses, and assertions
---

# Fixture Format

## Purpose

A fixture defines everything needed to run a skill without interactive user input:
1. **inputs** — what to provide to the skill at each phase
2. **stopping_point_responses** — how to answer each mandatory stop
3. **assertions** — what to verify in the output

---

## Schema

```yaml
# Required metadata
skill: <skill-name>                        # name of the skill to test
scenario: <descriptive-name>               # human-readable test scenario name
connection: <snowflake-connection-name>    # Snowflake connection for DDL execution
description: "What this fixture tests"

# Inputs passed to the skill phases
inputs:
  # Phase 1 inputs (skill-specific)
  sv_name: <SV_IDENTIFIER>
  sv_db: <DATABASE>
  sv_schema: <SCHEMA>
  tables:
    - <DB.SCHEMA.TABLE>
  business_context: "<free text description of the business domain>"
  doc_context: null                        # null = skip, or provide text/file path

# Responses injected at each STOPPING POINT
# Keys match the phase name; values are the response to inject
stopping_point_responses:
  phase_1_confirm: "yes"
  phase_2_description_review: "yes"        # accept generated descriptions
  phase_3_classification: "ok"             # accept auto-classification
  phase_4_relationships: "ok"              # accept detected relationships
  phase_5_ddl_review: "go"                 # execute the generated DDL
  phase_6_result: "accept"                 # accept validation results (or "iterate")
  phase_7_verified_queries: "yes"          # generate verified queries

# Optional: override specific classifications at Phase 3
# phase_3_overrides:
#   VEHICLES.CONDITION_REPORT: "SKIP"      # skip VARIANT columns
#   DEALERS.COX_PRODUCT_COUNT: "DIMENSION" # override numeric → dimension

# Assertions evaluated after all phases complete
assertions:
  ddl_executes: true                       # DDL runs without error
  ddl_or_replace: true                     # DDL uses CREATE OR REPLACE (idempotent)
  describe_tables: ">= 3"                  # min tables in DESCRIBE output
  describe_facts: ">= 4"                   # min facts
  describe_dimensions: ">= 6"             # min dimensions
  describe_relationships: ">= 1"           # min relationships
  descriptions_populated: ">= 8"          # min columns with non-empty COMMENT
  self_test_pass_rate: ">= 0.5"           # fraction of sample questions that pass
  ai_generation_instructions: true         # AI_SQL_GENERATION block present
  no_empty_relationships_block: true       # RELATIONSHIPS clause absent if 0 relationships

# Cleanup — whether to DROP the SV after testing
cleanup:
  drop_after_test: false                   # keep for inspection
  sv_suffix: "_TEST"                       # append to SV name to avoid collisions
```

---

## Adding overrides at stopping points

For testing edge cases, you can force specific behaviors:

```yaml
# Test: what happens if user rejects descriptions
stopping_point_responses:
  phase_2_description_review: "skip descriptions"

# Test: what happens with a custom classification override  
stopping_point_responses:
  phase_3_classification: "VEHICLES.CONDITION_REPORT -> SKIP"
```

---

## Assertions syntax

| Format | Meaning |
|--------|---------|
| `true` | Must be true (boolean) |
| `false` | Must be false |
| `">= N"` | Value must be >= N |
| `"<= N"` | Value must be <= N |
| `"== N"` | Exact match |
| `"contains: 'text'"` | Output string must contain text |

---

## Naming convention

Fixture files: `<skill_name>_<scenario>.yaml`

Examples:
- `doc_reviewer_readme_full.yaml` — doc-reviewer full mode happy path
- `plan_reviewer_full_mode.yaml` — plan-reviewer full mode
- `skill_tester_meta_test.yaml` — meta-test (tests the tester itself)
- `doc_reviewer_edge_no_readme.yaml` — edge case: no README found
