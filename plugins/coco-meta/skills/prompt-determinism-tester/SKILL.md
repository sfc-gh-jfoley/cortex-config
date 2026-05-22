---
name: prompt-determinism-tester
description: "Test HOL/demo prompts for build determinism by swarming 3 independent Plan agents and comparing their execution plans. Use when: testing prompts, prompt determinism, HOL quality, demo prep, prompt convergence, swarm test. Triggers: test prompt, determinism, swarm test, prompt quality, HOL test, prompt convergence."
---

# Prompt Determinism Tester

Test whether a CoCo prompt produces the same **build plan** regardless of which agent instance interprets it. If 3 independent agents given the same prompt produce structurally identical plans, the prompt is lab-ready. If they diverge, the skill shows exactly where and suggests tightening.

## When to Use

- Before running a hands-on lab, to verify every attendee will get the same outcome
- When iterating on a prompt to make it more deterministic
- When building a new HOL and want to QA prompts before packaging

## Core Concept

The test is NOT about data content (synthetic data can vary). The test is about the **build plan**: same objects created, same DDL sequence, same row counts, same Snowflake features used, same artifacts produced. If all 3 agents agree on WHAT gets built, the prompt is deterministic enough for a lab.

## Sequential Dependency Model

HOL prompts build on each other — Prompt 2 assumes Prompt 1's objects exist. This skill enforces a **gated sequential pipeline**:

```
Prompt 1 → SWARM → COMPARE → PASS? ─yes─→ lock build plan as context
                                │                    ↓
                                no              Prompt 2 → SWARM → COMPARE → PASS? → ...
                                ↓
                          STOP: fix Prompt 1 before testing Prompt 2
```

**Rules:**
1. Test prompts in order (1, 2, 3, ...). A prompt CANNOT be tested until all prior prompts pass.
2. When a prompt passes, its **agreed build plan** (the consensus objects/DDL/columns) becomes part of the **cumulative schema context** fed to the next prompt's swarm agents.
3. If a prompt fails (convergence < 90%), STOP. Fix that prompt and re-test it before proceeding.
4. The cumulative context grows with each passed prompt — by Prompt 7, agents see: base setup SQL + Prompt 1 objects + Prompt 2 objects + ... + Prompt 6 objects.

This mirrors what happens in a real lab: each attendee's Snowflake session accumulates the objects from prior prompts.

## Workflow

### Step 1: Gather Input

**Ask user for:**

1. **The prompt(s)** — either:
   - Paste a single prompt inline (single-prompt mode), OR
   - Provide a path to a `hol_prompts.md` file (multi-prompt mode — skill parses ALL fenced code blocks and tests them sequentially with the gated pipeline)
2. **Schema context** (optional but recommended) — path to a setup SQL file (e.g., `hol_setup.sql`) that defines the base tables/data the prompts operate against. This is the starting schema context.
3. **Mode** — ask the user:
   ```
   How should I handle prompt improvements when divergence is found?
   
   1. SUGGEST — Show divergence + suggested edits. You rewrite manually.
   2. AUTO — I auto-rewrite the prompt, show you the diff, and re-test
            in a loop until convergence >= 90% (max 5 iterations).
   ```

**If schema context is provided:**
- **Read** the setup SQL file
- Extract table names, column names, types, and row counts from CREATE TABLE and INSERT statements
- This becomes the **base context** — it persists across all prompts

**If multi-prompt mode:**
- Parse the `hol_prompts.md` file and extract all fenced code blocks in order
- Display the list: "Found N prompts. Testing sequentially — each must pass before the next."
- Initialize cumulative context = base schema context

**⚠️ STOP**: Confirm the prompt(s), context, and mode before proceeding.

### Step 1.5: Full Lab Audit (Multi-Prompt Mode)

**Before testing individual prompts, scan the entire lab for structural issues.**

Read ALL lab files provided (hol_prompts.md, hol_setup.sql, facilitator guide, broken query files, teardown SQL, etc.) and check for:

**Setup SQL consistency:**
- Every table referenced in any prompt must exist in setup SQL
- Column names in prompts must match actual DDL in setup SQL
- Row counts in facilitator notes must match INSERT counts in setup SQL
- Verify teardown SQL drops everything setup SQL creates (no orphans)

**Cross-prompt consistency:**
- Prompts that reference objects from prior prompts — verify the name/type matches
- Facilitator notes reference specific values (e.g., "VIN-014 at 62 days CRITICAL") — verify these values are actually in the INSERT data
- Expected outputs in facilitator notes must be achievable from the setup data

**Broken query files:**
- Verify the bugs described in facilitator notes actually exist in the SQL
- Verify the "correct" output described in facilitator notes is achievable after fixing the bugs

**Present audit results:**
```
═══════════════════════════════════════════════════
  LAB AUDIT
═══════════════════════════════════════════════════

Files scanned: 7
  hol_setup.sql ........... 8 tables, 175 rows
  hol_prompts.md .......... 7 prompts + 1 bonus
  hol_facilitator_guide.md  337 lines
  hol_broken_query.sql .... 3 documented bugs
  hol_teardown.sql ........ DROP SCHEMA CASCADE

Issues found: 2

  ⚠️  Prompt 4 references "sentiment_label" column on CONSUMER_INTERACTIONS
     but setup SQL column is "SENTIMENT_LABEL_MANUAL"
     → Fix: rename column in setup SQL or update prompt text

  ⚠️  Facilitator note for Prompt 5 says "VIN-014 (62 days, CRITICAL)"
     but setup SQL list_date for VIN-014 would be 58 days as of today
     → Fix: update list_date in setup SQL or change facilitator note

  ✅ All 8 tables in setup SQL are referenced by at least one prompt
  ✅ Teardown covers all setup objects
  ✅ Broken query bugs match facilitator notes
  ✅ All 3 documented bugs are present in hol_broken_query.sql

═══════════════════════════════════════════════════
```

**⚠️ STOP**: Present audit. If issues found, ask user to fix before proceeding to prompt determinism testing. Audit issues will cause false divergence in the swarm tests.

### Step 2: Swarm 3 Independent Plan Agents

**Load** `references/plan-schema.md` — this is the output format contract.

Launch **3 parallel** Task agents with `subagent_type="Plan"`. Each agent gets an identical prompt constructed as follows:

```
You are testing a hands-on lab prompt for determinism. Your job is to produce
a BUILD PLAN — the exact list of Snowflake objects that would be created if
this prompt were executed by Cortex Code.

RULES:
- Produce ONLY the build plan in the format below. Do not execute anything.
- Do not explain your reasoning. Just output the structured plan.
- For tables with INSERT statements, state the exact row count.
- Use fully qualified object names where the prompt defines them.
- If the prompt uses SET variables, use the variable references.
- For every TABLE and DYNAMIC TABLE, list ALL columns with:
  name, data type (use Snowflake canonical types with precision, e.g.
  NUMBER(10,2) not just NUMBER), nullable (TRUE/FALSE), and column order.
  DDL STRUCTURE IS CRITICAL — downstream objects (DTs, SVs, Agents) will
  be built on top of these tables and will break if the schema differs.
- Be precise about which Snowflake features are used (Dynamic Table vs View,
  AI_CLASSIFY vs CORTEX.COMPLETE, etc.)
- When the prompt says "create a table with X columns", infer the exact
  column names, types, and order from the prompt context. If ambiguous,
  choose the most standard Snowflake convention.

SCHEMA CONTEXT (tables available to the prompt):
{schema_context or "No schema context provided — infer from prompt."}

CUMULATIVE CONTEXT (objects created by prior prompts in this lab):
{cumulative_context or "This is the first prompt — no prior objects."}

THE PROMPT TO ANALYZE:
---
{prompt_text}
---

OUTPUT FORMAT:
{contents of references/plan-schema.md, the BUILD_PLAN format section}
```

**Each agent MUST be independent** — do not pass any agent's output to another.

### Step 3: Collect Plans

Wait for all 3 agents to return. Parse each plan into structured fields:
- `objects`: list of {name, type, ddl_action, row_count, columns}
- `sequence`: ordered list of object names
- `artifacts`: set of final deliverables
- `features`: set of Snowflake features

### Step 4: Compare Plans

Score convergence across 6 dimensions:

| Dimension | Weight | Comparison Method |
|-----------|--------|-------------------|
| **Objects** | 20% | Set similarity of object names + types. All 3 match = 100%. 2/3 match = 50%. All different = 0%. |
| **DDL Structure** | 30% | Per-table comparison of column names, types, and order. This is the heaviest dimension — downstream DTs, SVs, and Agents break if the base DDL diverges. Score = average per-table match across all tables in 2+ plans. A table scores 100% if all 3 agents produce identical column lists (name + type + order). |
| **Sequence** | 15% | Ordered comparison of DDL sequence. Same order = 100%. Same objects different order = 50%. Different objects = 0%. |
| **Row Counts** | 10% | Per-table row count comparison. All 3 match exactly = 100%. Within 20% = 75%. Differs by >20% = 0%. |
| **Features** | 15% | Set intersection of Snowflake features used. 3/3 agree = 100%. 2/3 = 50%. All different = 0%. |
| **Artifacts** | 10% | Set intersection of final deliverables. 3/3 agree = 100%. 2/3 = 50%. |

**Overall convergence** = weighted average.

**Comparison rules:**
- Normalize object names to UPPERCASE before comparing
- Ignore differences in database/schema prefix if the core object name matches
- Treat `CREATE` and `CREATE_OR_REPLACE` as equivalent
- Normalize equivalent Snowflake types: VARCHAR/STRING/TEXT → VARCHAR, TIMESTAMP/TIMESTAMP_NTZ → TIMESTAMP_NTZ
- Column types: `NUMBER(10,2)` vs `FLOAT` is a MISMATCH (precision matters for downstream). `NUMBER` vs `INT` is a MISMATCH (INT = NUMBER(38,0), different from NUMBER(10,2))
- Column order matters — position N in agent 1 must match position N in agent 2

### Step 5: Report

Present results in this format:

```
═══════════════════════════════════════════════════
  PROMPT DETERMINISM REPORT
═══════════════════════════════════════════════════

Prompt: [first 80 chars of prompt...]
Context: [schema file name or "none"]

CONVERGENCE SCORE: XX% — [VERDICT]

  Objects ......... XX% (N/N objects agreed)
  DDL Structure ... XX% (N tables compared, name+type+order)
  Sequence ........ XX%
  Row Counts ...... XX% (N/N tables agreed)
  Features ........ XX% (N/N features agreed)
  Artifacts ....... XX% (N/N artifacts agreed)

─── DIVERGENCE DETAIL ────────────────────────────

[For each dimension scoring < 90%, show:]

OBJECTS divergence:
  Agent 1: INVENTORY_AGING_REPORT (DYNAMIC_TABLE)
  Agent 2: INVENTORY_AGING_REPORT (DYNAMIC_TABLE)
  Agent 3: INVENTORY_AGING_VW (VIEW)              ← DIVERGENT
  → Fix: Specify "Dynamic Table" explicitly in the prompt

DDL STRUCTURE divergence (INVENTORY_AGING_REPORT):
  Column 3:
    Agent 1: DAYS_ON_MARKET NUMBER(10,0)
    Agent 2: DAYS_ON_MARKET NUMBER(10,0)
    Agent 3: DAYS_ON_MARKET INT                   ← DIVERGENT (INT = NUMBER(38,0))
  → Fix: Specify "DAYS_ON_MARKET NUMBER(10,0)" in prompt or add a column spec table

  Agent 1 has 12 columns, Agent 3 has 14 columns  ← DIVERGENT
  Extra in Agent 3: LAST_PRICE_CHANGE_DATE, PRICE_CHANGE_COUNT
  → Fix: List exact columns expected, or remove ambiguity about price reduction tracking

FEATURES divergence:
  Agent 1: AI_CLASSIFY
  Agent 2: AI_CLASSIFY
  Agent 3: CORTEX.COMPLETE with classification prompt  ← DIVERGENT
  → Fix: Name the exact Cortex function: "Use AI_CLASSIFY()"

─── SUGGESTED PROMPT EDITS ───────────────────────

1. Line "Build a ... aging report" →
   "Build a Dynamic Table called INVENTORY_AGING_REPORT"
   (forces object type + name)

2. Line "classify the PRIMARY concern" →
   "Use AI_CLASSIFY() to tag the PRIMARY concern"
   (forces specific Cortex function)

═══════════════════════════════════════════════════
```

**Verdicts:**
- **90-100%**: `DETERMINISTIC` — prompt is lab-ready
- **70-89%**: `MOSTLY_DETERMINISTIC` — minor tightening needed, divergence points shown
- **50-69%**: `DIVERGENT` — prompt is ambiguous in key areas
- **<50%**: `NON_DETERMINISTIC` — prompt needs significant rework

**⚠️ STOP**: Present report. Ask user if they want to iterate.

### Step 6: Iterate (SUGGEST mode) / Auto-Rewrite (AUTO mode)

**SUGGEST mode:**

If the user provides an edited prompt (or asks for suggestions to be applied):

1. Apply the suggested edits to the prompt text
2. Present the revised prompt for confirmation
3. Loop back to Step 2 with the revised prompt
4. Compare new convergence score to previous run

**AUTO mode:**

If convergence < 90%, automatically rewrite the prompt to close divergence gaps:

1. For each divergence point, apply the most specific fix:
   - **Object name divergence** → Add explicit name: "Create a table called EXACT_NAME"
   - **Object type divergence** → Add explicit type: "Create a Dynamic Table" (not "create a report")
   - **DDL structure divergence** → Add a column spec to the prompt: "with columns: COL1 VARCHAR, COL2 NUMBER(10,2), ..."
   - **Feature divergence** → Name the exact function: "Use AI_CLASSIFY()" not "classify"
   - **Row count divergence** → Add explicit count: "Insert exactly 20 rows"
2. Show the diff between original and rewritten prompt
3. Re-test by looping back to Step 2 with the rewritten prompt
4. Repeat until convergence >= 90% or max 5 iterations reached

**If max iterations reached without convergence:**
- Present the best version achieved with its score
- Show remaining divergence points that resist auto-fix
- These likely need the user to make a design decision (e.g., "should this be a view or a dynamic table?")

Track iteration history (both modes):
```
Iteration 1: 62% DIVERGENT
Iteration 2: 78% MOSTLY_DETERMINISTIC (fixed: object types, function names)
Iteration 3: 94% DETERMINISTIC (fixed: column list in step 4)
```

Continue until the user is satisfied or the prompt hits 90%+.

### Step 7: Advance Pipeline (Multi-Prompt Mode)

**Only applies when testing a full HOL file with multiple prompts.**

When the current prompt passes (convergence >= 90% or user accepts):

1. **Lock the consensus build plan** — take the agreed objects/columns/types from the 3 agents (use the majority when 2/3 agree, or Agent 1 when all 3 differ on a non-critical detail).

2. **Append to cumulative context** — add the locked build plan objects to the running schema context:
   ```
   CUMULATIVE CONTEXT (objects created by prior prompts):
   
   [Prompt 1 — Schema Discovery] (PASSED 94%)
     No new objects created (read-only prompt)
   
   [Prompt 5 — Dynamic Table] (PASSED 91%)
     INVENTORY_AGING_REPORT: DYNAMIC_TABLE
       Columns: VIN VARCHAR, MAKE VARCHAR, MODEL VARCHAR, ...
       Row count: NULL (dynamic)
     AGING_DEALER_SUMMARY: DYNAMIC_TABLE
       Columns: DEALER_NAME VARCHAR, FRESH_COUNT NUMBER, ...
       Row count: NULL (dynamic)
   ```

3. **Advance to next prompt** — display:
   ```
   ✅ Prompt N PASSED (XX%) — locked N objects into cumulative context
   
   Next: Prompt N+1 — [title from hol_prompts.md section header]
   Cumulative context: base setup + N objects from prior prompts
   
   Proceed? (Yes / Skip / Stop)
   ```

4. **If user says Yes** — loop back to Step 2 with the next prompt + updated cumulative context
5. **If user says Skip** — skip this prompt, do NOT add to cumulative context, advance to next
6. **If user says Stop** — end pipeline, present final summary

**When all prompts are tested (or user stops), present the pipeline summary:**

```
═══════════════════════════════════════════════════
  HOL PIPELINE SUMMARY
═══════════════════════════════════════════════════

Lab: Retail Analytics HOL (7 prompts)
Context: hol_setup.sql (8 base tables)

  Prompt 1 — Schema Discovery .... 97% DETERMINISTIC     ✅
  Prompt 2 — Product Lifecycle ... 88% MOSTLY_DETERM.     ⚠️ (col order)
  Prompt 3 — Debug & Optimize .... 94% DETERMINISTIC     ✅
  Prompt 4 — Cortex AI on Notes .. 72% MOSTLY_DETERM.     ⚠️ (AI func)
  Prompt 5 — Dynamic Table ....... 91% DETERMINISTIC     ✅
  Prompt 6 — Semantic View ....... 85% MOSTLY_DETERM.     ⚠️ (metrics)
  Prompt 7 — Cortex Agent ........ 93% DETERMINISTIC     ✅

  Overall: 5/7 DETERMINISTIC, 2/7 need tightening
  Blocking: None (all >= 70%)

═══════════════════════════════════════════════════
```

**⚠️ STOP**: Present pipeline summary. Ask if user wants to fix the failing prompts.

### Step 8: Save Results (Optional)

**Ask user:** "Want to save these results to a Snowflake table for tracking?"

If yes, ask for database.schema, then create and populate:

```sql
CREATE TABLE IF NOT EXISTS <db>.<schema>.PROMPT_DETERMINISM_RESULTS (
    TEST_ID VARCHAR DEFAULT UUID_STRING(),
    TEST_DATE TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PROMPT_NAME VARCHAR,
    PROMPT_TEXT VARCHAR,
    CONTEXT_FILE VARCHAR,
    ITERATION NUMBER,
    CONVERGENCE_SCORE FLOAT,
    VERDICT VARCHAR,
    OBJECTS_SCORE FLOAT,
    DDL_STRUCTURE_SCORE FLOAT,
    SEQUENCE_SCORE FLOAT,
    ROW_COUNTS_SCORE FLOAT,
    FEATURES_SCORE FLOAT,
    ARTIFACTS_SCORE FLOAT,
    DIVERGENCE_DETAIL VARIANT,
    AGENT_PLANS VARIANT
);
```

Insert one row per iteration tested.

## Stopping Points

- ✋ Step 1: Confirm prompt(s), context, and mode (SUGGEST/AUTO)
- ✋ Step 1.5: Lab audit results — fix issues before testing prompts
- ✋ Step 5: Review determinism report before iterating (SUGGEST mode) or review auto-rewrite diff (AUTO mode)
- ✋ Step 7: Pipeline advancement — confirm proceed/skip/stop between prompts
- ✋ Step 7: Pipeline summary — review full HOL results
- ✋ Step 8: Confirm before DDL/DML to Snowflake

## Output

- Per-prompt convergence score + verdict
- Per-prompt divergence detail with specific fix suggestions
- Iteration history per prompt showing improvement
- Pipeline summary for full HOL (multi-prompt mode)
- Cumulative context document (locked build plans from all passed prompts)
- Optional: Snowflake table with full test history

## Notes

- Each swarm run costs 3x a normal Plan agent call. For a 7-prompt HOL, that's 21 Plan calls minimum (more if prompts need iteration).
- Prompts that are read-only (e.g., Schema Discovery — no DDL produced) will score 100% on Objects/DDL/Sequence/RowCounts since there's nothing to diverge on. They still test Feature and Artifact convergence.
- Prompts that ask for creative output (e.g., "write a pitch paragraph") will always score low on artifact convergence — that's expected. Focus on the Objects/DDL/Features dimensions for those.
- Schema context dramatically improves convergence because agents have real table/column names to anchor on. Always provide it for HOL prompts.
- In multi-prompt mode, a failing prompt blocks all downstream prompts. Fix it first — downstream convergence is meaningless if the base schema differs.
