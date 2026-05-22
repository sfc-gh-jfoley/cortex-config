---
name: cortex-agent-optimization-eval-data
description: "Create, validate, and re-balance dev/test eval splits for a Cortex Agent."
parent_skill: cortex-agent-optimization
---

This sub-skill has four workflows. Detect which the user wants, or default to **Validate** if an eval table already exists with a SPLIT column.

Read `metadata.yaml` for parameters if not already loaded (`<DATABASE>`, `<SCHEMA>`, `<EVAL_TABLE>`, `<DEV_SPLIT_VALUE>`, `<TEST_SPLIT_VALUE>`).

**Detect existing split values:** Run `SELECT DISTINCT SPLIT FROM <EVAL_TABLE> WHERE SPLIT IS NOT NULL`. If two distinct values exist, map them to DEV/TEST by checking which value the `AGENT_EVAL_DEV` view filters on, or ask the user. Set `<DEV_SPLIT_VALUE>` and `<TEST_SPLIT_VALUE>` accordingly. Defaults: `'TRAIN'` / `'VALIDATION'`.

---

**Note on dataset creation:**

This skill assumes the eval table already exists and focuses on split assignment and validation. For creating the initial dataset:
- **From scratch:** Create table with TEST_ID, TEST_CATEGORY, INPUT_QUERY, GROUND_TRUTH, SPLIT columns
- **From production data:** See bundled `dataset-curation` skill (Option B) for Agent Events Explorer workflow
- **From user feedback:** Use `feedback-pipeline/SKILL.md` to curate thumbs up/down feedback into eval rows
- **Complex curation needs:** See bundled `dataset-curation` skill for Streamlit-based annotation and format conversion

This skill handles splitting existing data; the bundled skill handles collecting and curating that data.

---

## Workflow A: Create Split

### Step 1: Profile

Read the eval table and count questions per category:
```sql
SELECT TEST_CATEGORY, COUNT(*) AS TOTAL
FROM <EVAL_TABLE>
GROUP BY TEST_CATEGORY
ORDER BY TOTAL DESC;
```

### Step 2: Assign Splits

For each category independently, randomly assign ~45% of questions to `<DEV_SPLIT_VALUE>` (DEV) and ~55% to `<TEST_SPLIT_VALUE>` (TEST). Target DEV count per category: `ROUND(N * 0.45)`.

Use a deterministic method (e.g., `ROW_NUMBER() OVER (PARTITION BY TEST_CATEGORY ORDER BY RANDOM(42))`) so the assignment is reproducible.

### Step 3: Validate Minimum Coverage

If any category has fewer than 3 questions in either split after assignment, flag it:
> ⚠️ Category `<CAT>` has only N questions — too small for reliable stratification. Recommend: add more questions or merge with a related category.

If any category has fewer than 6 total questions, it cannot achieve ≥3 per split — this must be flagged as a hard warning.

### Step 4: Present and Execute

Generate `UPDATE` SQL to set the `SPLIT` column for each `TEST_ID`:
```sql
UPDATE <EVAL_TABLE> SET SPLIT = '<DEV_SPLIT_VALUE>' WHERE TEST_ID IN (...);
UPDATE <EVAL_TABLE> SET SPLIT = '<TEST_SPLIT_VALUE>' WHERE TEST_ID IN (...);
```

Present the proposed split with a per-category distribution table:

| Category | Total | DEV | TEST | DEV Ratio |
|----------|-------|-----|------|-----------|

**⚠️ STOP**: Present proposed split. Wait for user approval before executing the UPDATE statements.

---

## Workflow B: Validate Split

### Step 1: Query Distribution

```sql
SELECT TEST_CATEGORY,
       COUNT(*) AS TOTAL,
       COUNT_IF(SPLIT = '<DEV_SPLIT_VALUE>') AS DEV_COUNT,
       COUNT_IF(SPLIT = '<TEST_SPLIT_VALUE>') AS TEST_COUNT,
       ROUND(COUNT_IF(SPLIT = '<DEV_SPLIT_VALUE>') / NULLIF(COUNT(*), 0), 2) AS DEV_RATIO
FROM <EVAL_TABLE>
GROUP BY TEST_CATEGORY
ORDER BY TOTAL DESC;
```

### Step 2: Run Quality Checks

| Check | Condition | Status |
|-------|-----------|--------|
| **Category proportionality** | Each category's DEV ratio is between 0.35 and 0.55 | PASS / WARN |
| **Minimum coverage** | Every category has ≥3 questions in each split | PASS / FAIL |
| **Overall balance** | Total DEV/TEST ratio is between 0.40 and 0.50 | PASS / WARN |

### Step 3: Report

Present results with PASS/WARN/FAIL per check. If all PASS, confirm the split is healthy. If any WARN or FAIL, recommend running Workflow C to re-balance.

---

## Workflow C: Re-balance

### Step 1: Identify Issues

Run Workflow B validation to identify WARN/FAIL categories.

### Step 2: Propose Moves

For each flagged category, propose specific `TEST_ID` moves between splits to bring the ratio within bounds. Minimize total moves — prefer moving questions from the over-represented split in that category.

### Step 3: Present and Execute

Generate `UPDATE` SQL for the proposed moves:
```sql
UPDATE <EVAL_TABLE> SET SPLIT = '<DEV_SPLIT_VALUE>' WHERE TEST_ID IN (...);
UPDATE <EVAL_TABLE> SET SPLIT = '<TEST_SPLIT_VALUE>' WHERE TEST_ID IN (...);
```

Present a before/after distribution table:

| Category | Before DEV | Before TEST | After DEV | After TEST | Moves |
|----------|-----------|------------|----------|-----------|-------|

**⚠️ STOP**: Present proposed moves. Wait for user approval before executing.

After execution, re-run Workflow B to confirm all checks now pass.

---

## Workflow D: Merge Small Categories

Use when Workflow B validation identifies categories with <6 total questions.

### Step 1: Identify Merge Candidates

For each category with <6 questions, query similar categories:
```sql
SELECT TEST_CATEGORY, 
       COUNT(*) AS TOTAL,
       EDITDISTANCE(TEST_CATEGORY, '<SMALL_CATEGORY>') AS EDIT_DISTANCE
FROM <EVAL_TABLE>
WHERE TEST_CATEGORY != '<SMALL_CATEGORY>'
GROUP BY TEST_CATEGORY
ORDER BY EDIT_DISTANCE ASC, TOTAL DESC
LIMIT 5;
```

Present top 5 candidates to user for merge target selection.

### Step 2: Preview Merge Impact

Show before/after distribution if merge proceeds:

| Metric | Before | After Merge |
|--------|--------|-------------|
| Total categories | N | N-1 |
| Questions in <TARGET> | X | X + M |
| <TARGET> DEV count | D1 | D1 + d |
| <TARGET> TEST count | T1 | T1 + t |
| <TARGET> DEV ratio | 0.XX | 0.YY (calculated) |
| Minimum coverage | FAIL (<3 in split) | PASS (≥3 in each) |

### Step 3: Execute Merge

Generate UPDATE SQL:
```sql
UPDATE <EVAL_TABLE> 
SET TEST_CATEGORY = '<TARGET_CATEGORY>' 
WHERE TEST_CATEGORY = '<SMALL_CATEGORY>';
```

**⚠️ STOP**: Present merge proposal with impact table. Wait for user approval before executing.

### Step 4: Re-validate

After execution, re-run Workflow B (Validate Split) to confirm all quality checks now pass.

---

## Workflow E: Validate Ground Truth Completeness

**CRITICAL — Run this before every eval execution.** Missing ground truth causes the evaluator to return `{"code":400,"message":"Missing ground truth"}` and score 0 for the question. This silently corrupts aggregate metrics — a 50% GT fill rate makes a 0.90-quality agent look like 0.45.

### Step 1: Check Completeness

```sql
SELECT 
    SPLIT,
    COUNT(*) AS TOTAL_QUESTIONS,
    COUNT_IF(GROUND_TRUTH IS NULL) AS NULL_GT,
    COUNT_IF(GROUND_TRUTH IS NOT NULL 
             AND TRY_PARSE_JSON(GROUND_TRUTH):ground_truth_output::STRING IS NULL) AS EMPTY_GT_OUTPUT,
    COUNT_IF(GROUND_TRUTH IS NOT NULL 
             AND TRY_PARSE_JSON(GROUND_TRUTH):ground_truth_output::STRING IS NOT NULL
             AND LEN(TRIM(TRY_PARSE_JSON(GROUND_TRUTH):ground_truth_output::STRING)) = 0) AS BLANK_GT_OUTPUT,
    TOTAL_QUESTIONS - NULL_GT - EMPTY_GT_OUTPUT - BLANK_GT_OUTPUT AS VALID_GT
FROM <EVAL_TABLE>
GROUP BY SPLIT
ORDER BY SPLIT;
```

### Step 2: Gate Decision

| Condition | Action |
|-----------|--------|
| **VALID_GT = TOTAL_QUESTIONS** for all splits | **PASS** — proceed with eval |
| **Any NULL_GT > 0 or EMPTY_GT_OUTPUT > 0 or BLANK_GT_OUTPUT > 0** | **HARD STOP** — list affected questions, do NOT run eval |

If HARD STOP, list every question missing ground truth:
```sql
SELECT TEST_ID, SPLIT, INPUT_QUERY,
       CASE 
         WHEN GROUND_TRUTH IS NULL THEN 'NULL'
         WHEN TRY_PARSE_JSON(GROUND_TRUTH):ground_truth_output::STRING IS NULL THEN 'MISSING ground_truth_output key'
         WHEN LEN(TRIM(TRY_PARSE_JSON(GROUND_TRUTH):ground_truth_output::STRING)) = 0 THEN 'BLANK ground_truth_output'
       END AS GT_ISSUE
FROM <EVAL_TABLE>
WHERE GROUND_TRUTH IS NULL
   OR TRY_PARSE_JSON(GROUND_TRUTH):ground_truth_output::STRING IS NULL
   OR LEN(TRIM(TRY_PARSE_JSON(GROUND_TRUTH):ground_truth_output::STRING)) = 0
ORDER BY SPLIT, TEST_ID;
```

> **Why this matters:** In a real optimization cycle, 10/18 DEV questions with missing GT produced a fake baseline of 0.33 — the true score was 0.69. Six eval runs, failure analysis, and iteration planning were wasted before the GT gap was discovered. This gate prevents that.

### Step 3: Remediate

For each question missing GT:
1. Run the question against the agent (or query the underlying data directly) to determine the correct answer
2. Write ground truth as: `{"ground_truth_output": "<accurate answer text>"}`
3. Optionally add `ground_truth_invocations` for tool-sequence validation
4. UPDATE the eval table row
5. Re-run Step 1 to confirm all gaps are filled

**⚠️ STOP**: Do not proceed to eval execution until Step 1 shows VALID_GT = TOTAL_QUESTIONS for ALL splits.
