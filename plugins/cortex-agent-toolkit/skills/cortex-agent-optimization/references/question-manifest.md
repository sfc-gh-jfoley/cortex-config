# Question Manifest

Per-question score history across all eval runs — flag sweeps, optimization iterations, and re-validations. Enables cross-run analysis: which questions are consistently hard, which are flag-sensitive, and which instruction changes transfer across flag configs.

## Table DDL

```sql
CREATE TABLE IF NOT EXISTS <DATABASE>.<SCHEMA>.<AGENT_NAME>_QUESTION_MANIFEST (
    MANIFEST_ID    NUMBER(38,0) AUTOINCREMENT,
    INPUT_ID       VARCHAR      NOT NULL,   -- Hash from GET_AI_EVALUATION_DATA (stable per question)
    INPUT_TEXT     VARCHAR,                  -- Question text (from INPUT column)
    METRIC_NAME    VARCHAR      NOT NULL,   -- e.g. answer_correctness, logical_consistency
    SCORE          FLOAT        NOT NULL,   -- EVAL_AGG_SCORE (0-1)
    SOURCE         VARCHAR      NOT NULL,   -- 'flag_sweep' | 'optimize_dev' | 'optimize_test' | 'revalidation'
    RUN_LABEL      VARCHAR      NOT NULL,   -- e.g. 'FASTPATH_OFF_dev_r1', 'iter3_dev_r2'
    VARIANT        VARCHAR,                 -- Flag variant suffix (BASE, AGENTIC, FASTPATH_OFF) or NULL for optimize runs
    ITERATION      VARCHAR,                 -- Iteration name (iter1, iter3) or NULL for flag sweep runs
    AGENT_FQN      VARCHAR,                 -- Fully qualified agent name that was evaluated
    RECORDED_AT    TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    DURATION_MS    NUMBER,                  -- Agent response time
    LLM_CALL_COUNT NUMBER,                  -- Number of LLM calls
    ERROR          VARCHAR                  -- Error message if agent failed on this question
);
```

**Co-location:** This table MUST be in the same schema as the agent and eval dataset.

## INSERT Pattern

After extracting results from `GET_AI_EVALUATION_DATA`, INSERT into the manifest:

```sql
INSERT INTO <DATABASE>.<SCHEMA>.<AGENT_NAME>_QUESTION_MANIFEST
    (INPUT_ID, INPUT_TEXT, METRIC_NAME, SCORE, SOURCE, RUN_LABEL, VARIANT, ITERATION, AGENT_FQN, DURATION_MS, LLM_CALL_COUNT, ERROR)
SELECT
    INPUT_ID,
    INPUT,
    METRIC_NAME,
    EVAL_AGG_SCORE,
    '<SOURCE>',          -- 'flag_sweep', 'optimize_dev', 'optimize_test', 'revalidation'
    '<RUN_LABEL>',       -- e.g. 'FASTPATH_OFF_dev_r1' or 'iter3_dev_r2'
    '<VARIANT>',         -- e.g. 'FASTPATH_OFF' or NULL
    '<ITERATION>',       -- e.g. 'iter3' or NULL
    '<AGENT_FQN>',
    DURATION_MS,
    LLM_CALL_COUNT,
    ERROR
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT', '<RUN_NAME>'
))
WHERE METRIC_NAME IS NOT NULL;
```

Repeat for each run in a batch (UNION ALL or sequential INSERTs).

## Key Queries

### 1. Transfer Opportunities — "What worked under one config but fails under another?"

Find questions that scored well under a different flag variant but poorly under the current one.
Use this during `optimize/SKILL.md` Step 4 to identify instruction patterns worth borrowing.

```sql
WITH best AS (
    SELECT INPUT_ID, INPUT_TEXT, VARIANT, SCORE
    FROM <DATABASE>.<SCHEMA>.<AGENT_NAME>_QUESTION_MANIFEST
    WHERE SOURCE = 'flag_sweep'
      AND METRIC_NAME = 'answer_correctness'
      AND SCORE >= 0.8
),
worst AS (
    SELECT INPUT_ID, VARIANT, SCORE
    FROM <DATABASE>.<SCHEMA>.<AGENT_NAME>_QUESTION_MANIFEST
    WHERE SOURCE = 'flag_sweep'
      AND METRIC_NAME = 'answer_correctness'
      AND SCORE < 0.5
)
SELECT
    b.INPUT_TEXT,
    b.VARIANT AS passing_variant,
    b.SCORE AS passing_score,
    w.VARIANT AS failing_variant,
    w.SCORE AS failing_score,
    b.SCORE - w.SCORE AS gap
FROM best b
JOIN worst w ON b.INPUT_ID = w.INPUT_ID AND b.VARIANT != w.VARIANT
ORDER BY gap DESC
LIMIT 20;
```

### 2. Instruction Impact — "Did an instruction change fix this question?"

Track a specific question's score across optimization iterations.

```sql
SELECT
    ITERATION,
    VARIANT,
    ROUND(AVG(SCORE), 3) AS AVG_SCORE,
    COUNT(*) AS RUNS
FROM <DATABASE>.<SCHEMA>.<AGENT_NAME>_QUESTION_MANIFEST
WHERE INPUT_ID = '<INPUT_ID>'
  AND METRIC_NAME = 'answer_correctness'
GROUP BY ITERATION, VARIANT
ORDER BY ITERATION, VARIANT;
```

### 3. Flag Sensitivity — "Which questions change the most between flag configs?"

```sql
SELECT
    INPUT_ID,
    MAX(INPUT_TEXT) AS QUESTION,
    MAX(SCORE) - MIN(SCORE) AS SCORE_RANGE,
    MAX(CASE WHEN VARIANT = 'BASE' THEN SCORE END) AS BASE,
    MAX(CASE WHEN VARIANT = 'AGENTIC' THEN SCORE END) AS AGENTIC,
    MAX(CASE WHEN VARIANT = 'FASTPATH_OFF' THEN SCORE END) AS FASTPATH_OFF
FROM <DATABASE>.<SCHEMA>.<AGENT_NAME>_QUESTION_MANIFEST
WHERE SOURCE IN ('flag_sweep', 'revalidation')
  AND METRIC_NAME = 'answer_correctness'
GROUP BY INPUT_ID
HAVING SCORE_RANGE > 0.3
ORDER BY SCORE_RANGE DESC
LIMIT 20;
```

### 4. Consistently Hard Questions — "What never scores well?"

```sql
SELECT
    INPUT_ID,
    MAX(INPUT_TEXT) AS QUESTION,
    COUNT(DISTINCT RUN_LABEL) AS TOTAL_RUNS,
    ROUND(AVG(SCORE), 3) AS AVG_SCORE,
    MAX(SCORE) AS BEST_EVER,
    COUNT(DISTINCT VARIANT) AS VARIANTS_TRIED,
    COUNT(DISTINCT ITERATION) AS ITERATIONS_TRIED
FROM <DATABASE>.<SCHEMA>.<AGENT_NAME>_QUESTION_MANIFEST
WHERE METRIC_NAME = 'answer_correctness'
GROUP BY INPUT_ID
HAVING AVG_SCORE < 0.5 AND TOTAL_RUNS >= 3
ORDER BY AVG_SCORE ASC
LIMIT 20;
```

### 5. Re-validation Drift — "Did the flag winner shift after instruction changes?"

```sql
WITH baseline AS (
    SELECT INPUT_ID, VARIANT, AVG(SCORE) AS BASELINE_SCORE
    FROM <DATABASE>.<SCHEMA>.<AGENT_NAME>_QUESTION_MANIFEST
    WHERE SOURCE = 'flag_sweep' AND METRIC_NAME = 'answer_correctness'
    GROUP BY INPUT_ID, VARIANT
),
reval AS (
    SELECT INPUT_ID, VARIANT, AVG(SCORE) AS REVAL_SCORE
    FROM <DATABASE>.<SCHEMA>.<AGENT_NAME>_QUESTION_MANIFEST
    WHERE SOURCE = 'revalidation' AND METRIC_NAME = 'answer_correctness'
    GROUP BY INPUT_ID, VARIANT
)
SELECT
    r.INPUT_ID,
    r.VARIANT,
    b.BASELINE_SCORE,
    r.REVAL_SCORE,
    r.REVAL_SCORE - b.BASELINE_SCORE AS DRIFT
FROM reval r
JOIN baseline b ON r.INPUT_ID = b.INPUT_ID AND r.VARIANT = b.VARIANT
WHERE ABS(DRIFT) > 0.2
ORDER BY DRIFT ASC
LIMIT 20;
```

## Maintenance

- The manifest is append-only. Never DELETE rows — historical data is the whole point.
- If the eval dataset questions change (new questions added, old ones removed), old manifest rows for removed questions become orphaned but harmless.
- To reset: `TRUNCATE TABLE <AGENT_NAME>_QUESTION_MANIFEST;` (only if starting fresh).
