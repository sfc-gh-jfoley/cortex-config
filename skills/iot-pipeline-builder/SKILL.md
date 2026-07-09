---
name: iot-pipeline-builder
description: >
  Builds a complete IoT / telemetry data pipeline in Snowsight from raw VARIANT tables to a
  conversational Cortex Agent — pure SQL DDL, no Python required. Use when the user wants to
  normalize raw IoT or telemetry data, or says any of: "flatten this data", "normalize this data",
  "put an SV and agent over this", "IoT pipeline", "build a pipeline from these tables",
  "flatten and normalize", "raw to agent", "normalize and build an agent",
  "flatten raw data", or "one shot pipeline". Executes autonomously:
  raw tables → Dynamic Tables (flatten VARIANT/JSON) → Semantic View → Cortex Agent → sample questions.
  Runs entirely in Snowsight SQL worksheets. No Python, no uv, no filesystem.
triggers:
  - flatten this data
  - normalize this data
  - put an SV and agent over this
  - IoT pipeline
  - build a pipeline from these tables
  - flatten and normalize
  - normalize and build an agent
  - flatten raw data
  - raw to agent
  - one shot pipeline
---

# IoT Pipeline Builder

Build a complete analytics pipeline from raw VARIANT/JSON tables to a chatbot agent — entirely in SQL.

**Pipeline:** `RAW tables → Dynamic Tables (flatten) → Semantic View → Cortex Agent → sample questions`

**Constraint:** Pure SQL DDL only. Every step runs in a Snowsight worksheet.

---

## Quick start

Ask the user ONE question (or detect from context):

> "Which `DB.SCHEMA` holds your raw tables?"

Then run all phases without stopping.

---

## Phase reference

| Phase | File | What CoCo does |
|-------|------|----------------|
| 1 | [phases/01_discover.md](phases/01_discover.md) | Introspect raw tables — VARIANT structure, arrays, nulls, join keys |
| 2 | [phases/02_normalize.md](phases/02_normalize.md) | Create NORMALIZED schema + Dynamic Tables (flatten VARIANT → typed columns) |
| 3 | [phases/03_semantic_view.md](phases/03_semantic_view.md) | Build Semantic View over DTs — classify columns, detect relationships, generate DDL |
| 4 | [phases/04_agent.md](phases/04_agent.md) | Create Cortex Agent — spec assembly, self-check, execute, smoke test |
| 5 | [phases/05_questions.md](phases/05_questions.md) | Generate sample questions + ready-to-run DATA_AGENT_RUN payloads |

**Load Phase 1 now: → [phases/01_discover.md](phases/01_discover.md)**

---

## Critical DDL rules (always active)

| Rule | |
|------|-|
| DT clause order | `TARGET_LAG` and `REFRESH_MODE` at end of CREATE DYNAMIC TABLE |
| SV clause order | `TABLES → RELATIONSHIPS → FACTS → DIMENSIONS → METRICS` — mandatory |
| SV column aliases | `AS col_name` must exactly match the physical column name |
| Agent `execution_environment` | Must be **nested inside `tool_resources`**, NOT a top-level key |
| Agent `tool_spec.name` | Must exactly match the key in `tool_resources` |
| Agent `models.orchestration` | Required — no default |

---

## Execution mode

No mandatory stopping gates. Run each phase to completion and proceed immediately.
The only user interaction is Phase 1 discovery (if tables aren't already in context).
