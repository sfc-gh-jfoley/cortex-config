# Skill: lab-builder

Build a complete Snowflake hands-on lab package from scratch.
Output: all files needed to deliver a customer or SE workshop.

**Trigger phrases:**
- "build a lab for..."
- "create a HOL for..."
- "scaffold a hands-on lab..."
- "invoke skill lab-builder"
- "[feature], [time]" — e.g. "Dynamic Tables, 3 hours" (Quick Mode)

---

## Reference: Gold Standard Lab

The canonical reference is `/Users/jfoley/src/demos/cai/`.
Before generating any file, read that lab to understand tone, data volume, and structure.

Framework standard: `/Users/jfoley/src/demos/labs/FRAMEWORK.md`
Template directory: `/Users/jfoley/src/demos/labs/_template/`

---

## Module Library

A reusable module catalog lives at `labs/_modules/`. Before building from scratch,
check whether the requested feature is already covered as a module.

**Index:** `labs/_modules/INDEX.md` — searchable by tag, duration, audience, and feature.

**When to use modules:**
- SE requests a specific feature (e.g. "ML lab", "Feature Store module") → find by tag
- Building a multi-feature lab → string modules by `Feeds from / Feeds into` order
- se-lab-intake generates a curriculum plan → match module IDs to the plan

**Module assembly rules:**
1. Read `INDEX.md` to find matching modules by tag
2. Check `Prerequisites` field — load modules in dependency order
3. Each module's `hol_setup.sql` blocks contribute to the lab's `hol_setup.sql`
4. Each module's exercises contribute to `hol_prompts.md` in order
5. Each module's Verify SQL contributes to `validate.sql`

**Available module tracks:**
- `ml/` — ml-01 through ml-06 (Registry → Feature Store → Training → Experiments → Registration → Drift)
- `data-eng/` — coming (dbt-staging, dynamic-tables-intro, dynamic-tables-monitoring)
- `ai/` — ai-01 (Semantic Views Basics, 25min). More coming (cortex-complete-intro, cortex-search)

---

## Intake Document Fast Path

If the SE pastes or references a file matching `*-lab-intake.md`, read it first.
It was produced by the `se-lab-intake` skill and contains:
- All Phase 0 (discovery) answers
- All Phase 0.5 (curriculum plan) answers
- Account configuration (isolation, CLI status, DBA contact)
- Company research (domain, synthetic data suggestions, hero question candidates)

**When an intake doc is present: skip Phase 0 and Phase 0.5 entirely.**
Start at Phase 1 (Scaffold) using values from the doc.
Note any open questions from the "Open Questions" section and ask them up front.

---

## Quick Mode — Minimal Input, Immediate 3 Options

**When the SE is on a call and types just `[feature] + [time]`**, skip the discovery
questionnaire and immediately output 3 ready-to-confirm lab options.

The SE picks one → THEN fill in domain, hero question, and tailoring details.

### Trigger

Any input matching: `<Snowflake feature>, <time available>`
Examples:
- `Dynamic Tables, 3 hours`
- `Streamlit, 1 hour`
- `Notebooks, full day`
- `dbt Snowflake, 90 minutes`

### Immediate output format

For each of the 3 options, output:

```
── Option A ─────────────────────────────────────────
Title:         <Lab title — domain-specific>
Domain:        <Business domain>
Hero question: "<The one question participants answer in the last module>"
Audience:      <Primary audience>

Module 00 — Setup & Data Load                    15 min
Module 01 — <Core concept introduction>          35 min
Module 02 — <Key use case + failure moment>      45 min  ← failure here
Module 03 — <Advanced pattern / capstone>        40 min
Validate + Wrap                                  15 min
Total: ~150 min (fits in 3 hours with 10 min buffer)

Adapt from: <existing lab if applicable, or "build new">
─────────────────────────────────────────────────────
```

The 3 options differ by **domain** (industries), giving the SE options to match
what the company cares about. All fit the requested time.

### 3-option rules

1. **Option A** — closest to the company's likely domain (infer from context if known)
2. **Option B** — a different domain angle (different industry, same feature)
3. **Option C** — a different depth angle (beginner-friendly vs. advanced track, or mixed audience)

If the company's domain is known from the conversation, make Option A their domain
and generate B and C as alternatives.

### After SE picks an option

Ask only 2 follow-up questions before building:
1. "What's the company's actual domain/data? I'll swap the synthetic data to match." (if Option A domain doesn't fit)
2. "Is there a specific business question they want to be able to answer at the end?"

Then go straight to Phase 2 (Scaffold). Skip the full discovery questionnaire — that
was the pre-call conversation, not a live-session interview.

---

## Phase 0 — Customer Discovery (Pre-Call)

**This phase happens BEFORE building anything.** The SE has a conversation with the
company — not a technical call, a business conversation — to understand what the lab
should actually be about.

A generic lab is a starting point. A tailored lab uses the company's domain, their
terminology, and a hero question they actually care about. That's what makes it land.

**Discovery conversation guide:**

Ask the company contact these questions. Take notes — the answers become the inputs
to Phase 1 (Intake):

| Question | Why it matters |
|----------|----------------|
| "What problem are you trying to solve with Snowflake?" | Becomes the hero question |
| "Who will be in the room — data engineers, analysts, or business users?" | Drives module depth and prompt style |
| "What industry/domain is your data in?" | Determines synthetic data domain |
| "What Snowflake features have you used so far?" | Calibrates what to skip vs. what to show |
| "Is there a specific outcome you want participants to be able to do after?" | Defines objectives and validate.sql checks |
| "How much time do you have?" | Sets duration and number of modules |
| "Individual databases per participant, or a shared Snowflake account with per-user schemas?" | **Company decides this — not the SE.** DBA or security policy owns the answer. Drives the entire grant model. |

**Domain tailoring:**

The synthetic data should feel like the company's world, not a generic example.

| Company | Domain | Lab data should look like |
|---------|--------|--------------------------|
| Verizon | Telecom | Network devices, subscriber events, CDRs, 5G signal metrics |
| Hospital system | Healthcare | Patient encounters, device readings, lab results |
| Retailer | Commerce | Orders, products, customers, transactions |
| Media company | Streaming | Titles, viewing sessions, recommendation events |
| Industrial mfg | IoT | Sensors, machines, maintenance logs, alerts |

If the company's domain doesn't fit an existing lab's data, build a new one via lab-builder
with their domain as the answer to Phase 1 Question 4.

**What makes a good hero question:**

The hero question is the one business outcome participants can't answer until the final
module. It should come from the discovery conversation, not be invented by the SE.

- Good: "Which of our network nodes exceeded SLA in the last hour?" (Verizon said this)
- Good: "Who are our top 10 customers by lifetime value?" (they said this in discovery)
- Weak: "How do dynamic tables work?" (feature-focused, not business-focused)

**After discovery:**

Take the conversation notes and run `invoke skill lab-builder`. The Phase 1 questions
map directly to what the company told you. If an existing lab already matches the domain
and hero question closely enough, adapt it. If not, build a new one.

---

## Phase 0.5 — Curriculum Planning

**Before asking about domain or hero question, plan the curriculum.**

Take the time available and audience from Phase 0 discovery and produce a suggested
session structure. Present it to the SE. They confirm or adjust. Then proceed to Phase 1.

This is the step where the SE decides whether to adapt an existing lab or build new.

---

### Step 1 — Map time to sessions and module count

| Time available | Sessions | Module count | Structure |
|----------------|----------|--------------|-----------|
| 1 hour | 1 | 1–2 | Setup (10 min) + 1 module (40 min) + validate (10 min) |
| 90 minutes | 1 | 2–3 | Setup (15 min) + 2 modules (30 min each) + validate (15 min) |
| Half day (3 hr) | 1 | 3–4 | Setup (20 min) + 3 modules (40 min each) + validate + wrap |
| Full day | 2 (two 3-hr sessions) | 5–6 | Session 1: core + failure moment · Session 2: advanced + capstone |
| Multi-day | 3+ sessions | 6–8 | Day 1: foundation · Day 2: advanced · Day 3: capstone + team presentations |

---

### Step 2 — Check existing labs first

Before building from scratch, scan `labs/LABS_INDEX.md` for a lab that matches:
- Same Snowflake feature(s)
- Same or adaptable audience
- Comparable duration

If a close match exists: **adapt it** — swap the data domain, update the hero question,
keep the module structure. This is faster than building from scratch and the module
pacing has already been tested.

If no match: build new from Phase 2 onward.

---

### Step 3 — Present the curriculum plan to the SE

Output a draft agenda. Example format:

```
Proposed curriculum for [Company] — [Feature] Lab
Time: [X] hours · [N] sessions · Audience: [DE/Analyst/BU]

Session 1 (~3 hours):
  Module 00 — Setup & Pre-Work Verification       15 min
  Module 01 — [Core Feature Introduction]         40 min
  Module 02 — [Key Use Case — failure moment]     45 min  ← intentional failure here
  Validate + Q&A                                  20 min

Session 2 (~3 hours):
  Module 03 — [Advanced Pattern]                  40 min
  Module 04 — [Integration / Capstone]            50 min
  Final Validate + Build Review                   30 min

Skipped (time constraint): Module 05 — [Optional advanced topic]
Suggested skip for Business Users: Module 01 SQL deep-dive
```

Ask the SE: "Does this structure work, or do you want to adjust timing or module order?"
**Do not proceed to Phase 1 until the agenda is confirmed.**

---

### Step 4 — Audience skip list

Apply these adjustments before finalizing:

| Audience | Adjustment |
|----------|-----------|
| Business Users / Executives | Remove 1 SQL-heavy module; add 10 min context per module for "why this matters" |
| Analysts (no SQL) | Skip raw DDL modules; start from pre-loaded data |
| Mixed (DE + Analyst) | Mark DE-only modules as optional; provide Analyst shortcut path |
| SE internal training | Keep full depth; add failure moment; Q&A after each module |

---

## Phase 1 — Intake

Ask the following questions (all required before proceeding):

1. **Topic:** What Snowflake feature(s) does this lab cover?
   (e.g., Streamlit in Snowflake, Dynamic Tables, dbt + Snowflake, Notebooks, Cortex Agents)

2. **Audience:** Who are the participants?
   (e.g., Customer Data Engineers, Analysts, SE internal training, conference demo)

3. **Duration:** How long is the session?
   (30 min / 60 min / 90 min / 2 hr)

4. **Domain:** What business domain should the synthetic data use?
   (e.g., IoT/telemetry, e-commerce, financial analytics, healthcare, media streaming)
   If unsure, suggest 2-3 options based on the audience.

5. **Isolation pattern:** What did the company say in discovery?
   - **Schema-per-user** (default): Shared database, each participant creates their own schema.
     Company has a shared Snowflake account. Mirrors `cai/` gold standard.
   - **Database-per-user**: Each participant gets a pre-created database.
     Company has dedicated sandbox accounts, or their security policy requires full DB isolation.
   **This is the company's decision** — their DBA or security team owns it. If it wasn't asked in discovery, go back and ask before building. The isolation choice drives every grant in `facilitator_setup.sql`.

6. **Hero question:** What is the one business question that is impossible until the final module?
   (This drives the build-out story. Example: "Which devices exceeded their critical threshold in the last hour?")

---

## Phase 2 — Scaffold

Create the lab directory and file skeleton:

```
labs/<lab-slug>/
├── AGENTS.md
├── README.md
├── hol_setup.sql
├── hol_teardown.sql
├── hol_prompts.md
├── hol_facilitator_guide.md
├── validate.sql
├── grant_audit.sql          ← NEW: SE verification script
├── facilitator_setup.sql    ← if elevated privileges needed
├── modules/
│   ├── 00_setup.md          ← includes Pre-Work CLI block
│   ├── 01_<topic>.md
│   └── ...
├── examples/
├── hints/
├── prompts/
└── solutions/
```

Write `AGENTS.md` first — CoCo reads this on session open and uses it for all prompts.
Include: lab name, hero question, data model table, join paths, Cortex AI features used.

---

## Phase 3 — Setup SQL (hol_setup.sql)

Apply the isolation pattern chosen in Phase 1:

**Pattern A (schema-per-user):**
```sql
-- ← Participant changes this to their name (e.g. 'JFOLEY_HOL')
SET MY_DB     = '<LAB_DATABASE>';
SET MY_SCHEMA = 'CHANGE_ME';

USE DATABASE IDENTIFIER($MY_DB);
CREATE SCHEMA IF NOT EXISTS IDENTIFIER($MY_SCHEMA);
USE SCHEMA IDENTIFIER($MY_SCHEMA);
```

**Pattern B (database-per-user):**
```sql
-- ← Participant changes this to their name (e.g. 'HOL_JFOLEY')
SET MY_DB = 'HOL_CHANGE_ME';

USE DATABASE IDENTIFIER($MY_DB);
CREATE SCHEMA IF NOT EXISTS LAB;
USE SCHEMA LAB;
```

Data sizing guidelines:
- Small lookup tables: 10-50 rows (explicit VALUES)
- Medium tables: 100-500 rows (VALUES or GENERATOR)
- Large/event tables: 1,000-100,000 rows (GENERATOR with UNIFORM/RANDOM)
- Use PARSE_JSON() for VARIANT columns (condition reports, metadata, etc.)
- Always end with a row count verification SELECT

**Also generate `grant_audit.sql`** for this lab:
1. Copy `labs/_template/grant_audit.sql`
2. Uncomment the module sections matching this lab's features
3. Fill in the lab name, database name, and feature comments
4. This is the SE's sign-off script — the DBA provisions, the SE verifies

---

## Phase 4 — Prompts and Facilitator Guide

**hol_prompts.md** — 3-6 exercises, following the build-out story:

Structure each exercise:
```
## Exercise N — <Title>

### Context
<1-2 sentences: what the participant knows at this point>

### Your Turn
Paste this into CoCo:
\```
I'm working in Snowflake database [DB], schema [SCHEMA], warehouse COMPUTE_WH.
I have these tables: [list with brief description].

[Specific ask]
\```

### What to Watch For
<Key observation — what CoCo should infer, or the failure moment>

### Verify
\```sql
SELECT ...;  -- expected: N rows / specific value
\```
```

**Failure moment rule:** One exercise must demonstrate a limitation before resolving it.
- The failure is intentional — frame it as "This is expected. Let's diagnose it."
- The fix demonstrates why the next feature/approach exists
- See `labs/streamlit-sis/hol_prompts.md` for the `import requests` → `session.sql()` pattern

**hol_facilitator_guide.md** — SE's delivery script:
- Agenda table with timing
- Pre-workshop checklist (reference grant_audit.sql)
- Per-module: what to watch for, common mistakes, timing notes
- Failure moment section: "When this happens, say: 'This is expected...'"
- Troubleshooting table

---

## Phase 5 — validate.sql

UNION ALL pattern — one row per objective, no Python:

```sql
-- ============================================================
-- Lab Completion Validator
-- Run at the end of the lab. Each check prints PASS or FAIL.
-- ============================================================

SELECT sort_key, check_name, status,
    CASE status WHEN 'PASS' THEN '✓' ELSE '✗ FAIL — re-run the referenced module' END AS result
FROM (
    SELECT 1 AS sort_key,
        'Objective 1: <description>' AS check_name,
        CASE WHEN <condition> THEN 'PASS' ELSE 'FAIL' END AS status

    UNION ALL SELECT 2, 'Objective 2: ...', CASE WHEN ... THEN 'PASS' ELSE 'FAIL' END
    -- ... one per objective
)
ORDER BY sort_key;
```

**Feature-specific check patterns:**
- **Streamlit exists:** `(SELECT COUNT(*) FROM INFORMATION_SCHEMA.STREAMLITS WHERE STREAMLIT_NAME = '<APP>') = 1`
- **Dynamic Table active:** `(SELECT SCHEDULING_STATE FROM INFORMATION_SCHEMA.DYNAMIC_TABLES WHERE TABLE_NAME = '<DT>') = 'ACTIVE'`
- **Cortex permission:** `IS_DATABASE_ROLE_IN_SESSION('SNOWFLAKE.CORTEX_USER')`
- **Notebook exists:** `(SELECT COUNT(*) FROM INFORMATION_SCHEMA.NOTEBOOKS WHERE NOTEBOOK_NAME = '<NB>') = 1`
- **dbt mart exists:** `(SELECT COUNT(*) FROM DBT_LAB.ANALYTICS.<MART_TABLE>) > 0`
- **Agent exists:** `(SELECT COUNT(*) FROM INFORMATION_SCHEMA.CORTEX_AGENTS WHERE AGENT_NAME = '<AGENT>') = 1`

**Agent smoke tests take 5-15 seconds** — put them in `smoke_test.sql` (facilitator-only),
not in `validate.sql` (participant-facing). DATA_AGENT_RUN with `content:[{type:'text',text:'...'}]`.

---

## Phase 6 — Self-Check

Before declaring the lab complete, verify:

- [ ] `hol_setup.sql` is idempotent (safe to re-run)
- [ ] Row counts are in comments and verified by final SELECT
- [ ] `hol_teardown.sql` drops everything `hol_setup.sql` created (test it)
- [ ] `validate.sql` uses UNION ALL — no Python, no external calls
- [ ] Every `validate.sql` check is verifiable without running the full lab
- [ ] Failure moment is documented in `hol_prompts.md` with facilitator callout
- [ ] Module 00 `Pre-Work` block is present with VPN warning
- [ ] `grant_audit.sql` covers all modules in the lab (check Section B)
- [ ] `README.md` `**Isolation:**` field is filled in
- [ ] `AGENTS.md` contains the hero question and full data model

---

## Phase 7 — HOL QA (prompt-determinism-tester)

Before any live CoCo-guided delivery, run the determinism tester:

```
invoke skill prompt-determinism-tester
```

The skill runs each CoCo prompt 3 times independently and checks that ≥90% of runs
produce consistent, correct results.

**Sequential gate:** Prompt N must reach 90% before testing Prompt N+1.
Any prompt below 90% must be rewritten before the workshop.

---

## Phase 8 — Register

Update `labs/LABS_INDEX.md` with the new lab entry. Include:
- Path, topic, interface, duration, audience, maturity (`complete`)
- Isolation pattern in Notes field
- Known Gaps if any (incomplete modules, untested prompts)

Announce the lab in `labs/LAB_ROADMAP.md` Known Gaps table if there are follow-up items.

---

## Topic-Specific Notes

### Streamlit in Snowflake
- Deploy with `snow streamlit deploy --replace -c default`
- `INFORMATION_SCHEMA.STREAMLITS` — correct view for SiS existence check (not STREAMLIT_APPS)
- `import requests` → `ModuleNotFoundError` in SiS managed runtime — use `session.sql()` instead
- `SNOWFLAKE.CORTEX.COMPLETE` via SQL, not `import cortex`
- Pattern for Cortex in SiS: `session.sql("SELECT SNOWFLAKE.CORTEX.COMPLETE(...)").collect()`

### Snowflake Notebooks
- `import cortex` does not exist → use `session.sql()` with `SNOWFLAKE.CORTEX.COMPLETE`
- `session.sql().to_pandas()` for Python cell processing
- `INFORMATION_SCHEMA.NOTEBOOKS` for existence checks

### dbt + Snowflake
- **Required macro:** `macros/generate_schema_name.sql` — without it, `+schema: analytics` in
  `dbt_project.yml` produces `analytics_analytics` (doubled prefix). With it: `DBT_LAB.ANALYTICS`
- `profiles.yml` authenticator: externalbrowser (not password)
- Pattern B (db-per-user) is more natural for dbt — each participant owns their own DB

### Dynamic Tables
- `TARGET_LAG` minimum: `'1 minute'` — `'0 seconds'` is the deterministic failure moment
- `SCHEDULING_STATE` (not REFRESH_STATE) for active-check in validate.sql
- `INFORMATION_SCHEMA.DYNAMIC_TABLES` for existence and state checks
- Pipeline pattern: raw → 1-min aggregate → 5-min summary (teaches chained DT dependency)

### Cortex Agents
- `CREATE AGENT db.schema.name FROM SPECIFICATION $$ json $$`
- Test via `SNOWFLAKE.CORTEX.DATA_AGENT_RUN` — content must be `[{type:'text',text:'...'}]`
- Agent smoke tests (5-15s) → `smoke_test.sql`, not `validate.sql`
- Requires `SNOWFLAKE.CORTEX_USER` database role
