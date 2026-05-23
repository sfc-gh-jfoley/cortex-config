# <Lab Title>
### <Subtitle — products covered e.g. "Cortex Analyst · Cortex Search · Snowflake Intelligence">

**Duration:** ~N minutes
**Environment:** CoCo CLI + Snowsight (or: Snowsight only)
**Interface:** Requires Cortex Code CLI (or: browser-only, no CLI required)
**Audience:** SEs | Data Engineers | Analysts
**Account:** Pre-provisioned by facilitator (or: any Snowflake account with CORTEX_USER role)

---

## What You Will Build

<1-3 sentence summary of what the learner creates and why it matters>

```
Module 1         Module 2         Module 3         Module 4
Setup + Data  →  Build X       →  Add Y         →  Validate + Demo
```

---

## Objectives

By the end of this lab you will be able to:
- [ ] Objective 1
- [ ] Objective 2
- [ ] Objective 3

---

## Prerequisites

- Cortex Code CLI installed (`cortex --version`) — *if using CoCo path*
- Snowflake account with `SNOWFLAKE.CORTEX_USER` database role
- `CREATE DATABASE`, `CREATE TABLE`, `CREATE SEMANTIC VIEW` privileges
- Cross-region inference enabled (`CORTEX_ENABLED_CROSS_REGION = 'AWS_US'`) — *if using AI functions*

---

## Agenda

| Module | Topic | Duration |
|--------|-------|----------|
| [00 - Setup](modules/00_setup.md) | Account setup, run DDL, verify data | 5 min |
| [01 - Topic One](modules/01_topic_one.md) | Description | N min |
| [02 - Topic Two](modules/02_topic_two.md) | Description | N min |
| [03 - Topic Three](modules/03_topic_three.md) | Description | N min |
| [04 - Validate](modules/04_validate.md) | Run completion checks, explore | N min |

---

## Quick Start (Easy Path)

For time-constrained demos, use the prompts in `prompts/` — they generate each section automatically.

```bash
# Easy path: opens CoCo and runs each prompt in sequence
# 1. Run sql/setup.sql in a Snowflake worksheet first
# 2. Open a CoCo session and paste prompts/01_easy_path.txt
```

---

## File Structure

```
<lab-slug>/
├── README.md                  # This file
├── modules/
│   ├── 00_setup.md
│   ├── 01_topic_one.md
│   ├── 02_topic_two.md
│   ├── 03_topic_three.md
│   └── 04_validate.md
├── sql/
│   ├── setup.sql              # DDL + synthetic data (idempotent)
│   ├── validate.sql           # Completion checks
│   └── teardown.sql           # Clean up all objects
├── examples/
│   └── complete_reference.sql # Full working reference
├── prompts/
│   └── 01_easy_path.txt       # Easy-path CoCo prompt
├── hints/
│   └── hints.md               # Progressive hints
└── solutions/
    └── solution.sql           # Full solution
```
