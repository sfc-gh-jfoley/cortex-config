# Eval Table Schema

## Table DDL

```sql
CREATE TABLE IF NOT EXISTS {DATABASE}.{SCHEMA}.{AGENT}_EVAL (
    TEST_ID        NUMBER(38,0) AUTOINCREMENT,
    TEST_CATEGORY  VARCHAR,
    INPUT_QUERY    VARCHAR      NOT NULL,
    GROUND_TRUTH   VARIANT,
    SPLIT          VARCHAR      DEFAULT 'VALIDATION'
);
```

## Ground Truth Format

The `GROUND_TRUTH` column must be VARIANT (not VARCHAR). Use `PARSE_JSON` or `OBJECT_CONSTRUCT` + `TO_VARIANT`:

```sql
INSERT INTO {AGENT}_EVAL (TEST_CATEGORY, INPUT_QUERY, GROUND_TRUTH)
SELECT
    'customer_lookup',
    'Show me the full profile for customer Alex Johnson',
    PARSE_JSON('{
        "ground_truth_output": "Alex Johnson (CUS-0001) is in the West region with 3 products. Total monthly value is $194.99. Risk tier is MEDIUM."
    }');
```

Alternative using OBJECT_CONSTRUCT:

```sql
INSERT INTO {AGENT}_EVAL (TEST_CATEGORY, INPUT_QUERY, GROUND_TRUTH)
SELECT
    'customer_lookup',
    'Show me the full profile for customer Alex Johnson',
    TO_VARIANT(OBJECT_CONSTRUCT(
        'ground_truth_output', 'Alex Johnson (CUS-0001) is in the West region with 3 products. Total monthly value is $194.99. Risk tier is MEDIUM.'
    ));
```

## Key Rules

1. **`ground_truth_output` is required** — the LLM judge uses this to score `answer_correctness`. Missing values produce score 0 and silently corrupt aggregates.

2. **VARIANT type is mandatory** — `OBJECT_CONSTRUCT` and `ARRAY_CONSTRUCT` return non-VARIANT results. Wrap with `TO_VARIANT()` or use `PARSE_JSON()` to guarantee the type.

3. **Reference-free metrics don't need ground truth** — `logical_consistency` works without any ground truth. If running only reference-free metrics, the GROUND_TRUTH column can be NULL.

4. **Natural language ground truth is powerful** — the LLM judge treats ground truth as context in its prompt. Use natural language to describe expected behavior, not just exact match strings. Example: "The response should mention at least 3 products and include a dollar amount for monthly value."

## DEV/TEST Split Views

After populating and splitting (45% DEV / 55% TEST):

```sql
CREATE OR REPLACE VIEW {DATABASE}.{SCHEMA}.{AGENT}_EVAL_DEV AS
SELECT * FROM {DATABASE}.{SCHEMA}.{AGENT}_EVAL WHERE SPLIT = 'TRAIN';

CREATE OR REPLACE VIEW {DATABASE}.{SCHEMA}.{AGENT}_EVAL_TEST AS
SELECT * FROM {DATABASE}.{SCHEMA}.{AGENT}_EVAL WHERE SPLIT = 'VALIDATION';
```

Split values are configurable. Defaults: `TRAIN` (DEV) / `VALIDATION` (TEST).

## Question Categories

Use `TEST_CATEGORY` for stratified analysis. Recommended categories:

| Category | Description |
|---|---|
| `single_tool` | Questions requiring exactly one semantic view tool |
| `multi_tool` | Questions spanning 2+ semantic views |
| `edge_case` | Boundary conditions, empty results, ambiguous queries |
| `aggregation` | Questions requiring SUM, AVG, COUNT, GROUP BY |
| `filter` | Questions with specific WHERE conditions (dates, names, statuses) |
| `domain_specific` | Industry/customer-specific terminology |

Aim for 25-50 questions total, with at least 3 per category per split.

## Validation Query

Verify completeness before running evals:

```sql
SELECT
    SPLIT,
    COUNT(*) AS TOTAL,
    COUNT_IF(GROUND_TRUTH IS NULL) AS NULL_GT,
    COUNT_IF(GROUND_TRUTH IS NOT NULL
             AND GROUND_TRUTH:ground_truth_output::STRING IS NULL) AS MISSING_OUTPUT,
    COUNT_IF(GROUND_TRUTH IS NOT NULL
             AND GROUND_TRUTH:ground_truth_output::STRING IS NOT NULL
             AND LEN(TRIM(GROUND_TRUTH:ground_truth_output::STRING)) = 0) AS BLANK_OUTPUT,
    TOTAL - NULL_GT - MISSING_OUTPUT - BLANK_OUTPUT AS VALID
FROM {DATABASE}.{SCHEMA}.{AGENT}_EVAL
GROUP BY SPLIT
ORDER BY SPLIT;
```

**Gate:** `VALID = TOTAL` for all splits before proceeding. Any gaps = HARD STOP.
