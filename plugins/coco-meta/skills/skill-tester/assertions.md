---
name: skill-tester-assertions
description: Assertion evaluation library for skill test results — evaluates numeric, boolean, string, and rate assertions
---

# Assertions Library

## Purpose

After each test run returns a result JSON, evaluate assertions from the fixture.

---

## Assertion types

### Boolean assertions

```yaml
ddl_executes: true
ai_generation_instructions: true
ddl_or_replace: true
```

Evaluate: `result[key] == expected_value`

---

### Numeric comparison assertions

```yaml
describe_tables: ">= 3"
describe_facts: ">= 4"
describe_dimensions: ">= 6"
describe_relationships: ">= 1"
descriptions_populated: ">= 8"
```

Parse operator from string: `>=`, `<=`, `==`, `>`, `<`

Evaluate: `result[key] <op> threshold`

---

### Rate assertions

```yaml
self_test_pass_rate: ">= 0.5"
```

Same as numeric comparison — value is a float between 0 and 1.

---

### String content assertions

```yaml
ddl_contains: "AI_SQL_GENERATION"
ddl_contains: "RELATIONSHIPS"
```

Evaluate: `assertion_value in result['ddl']`

---

## Assertion evaluation output

For each assertion, produce:

```python
{
  "assertion": "describe_tables >= 3",
  "run_1": { "value": 5, "passed": True },
  "run_2": { "value": 5, "passed": True },
  "run_3": { "value": 5, "passed": True },
  "status": "PASS",   # PASS = all 3 pass, WARN = 1-2 pass, FAIL = 0 pass
  "note": ""
}
```

---

## DDL-specific assertions

### DDL executes

Run the DDL against the target connection:
```sql
<ddl_from_result>
```

Check: does it return `Semantic view ... successfully created`?
If error: capture error message, mark `ddl_executes: false`, include error in result.

### DESCRIBE counts

```sql
DESCRIBE SEMANTIC VIEW <sv_db>.<sv_schema>.<sv_name>;
```

Count rows by `object_kind`:
```sql
SELECT OBJECT_KIND, COUNT(*) AS cnt
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
GROUP BY OBJECT_KIND;
```

Map to assertion fields:
- `TABLE` → `describe_tables`
- `FACT` → `describe_facts`
- `DIMENSION` → `describe_dimensions`
- `METRIC` → `describe_metrics`
- `RELATIONSHIP` → `describe_relationships`

### Descriptions populated

Count columns in DESCRIBE where `property = 'COMMENT'` and `property_value IS NOT NULL AND property_value != ''`:
```sql
SELECT COUNT(*) AS described_cols
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE property = 'COMMENT'
  AND property_value IS NOT NULL
  AND property_value != '';
```

### Self-test pass rate

The subagent executes 3-5 sample questions via Cortex Analyst:
```sql
SELECT SNOWFLAKE.CORTEX.ANALYST(
  '<question>',
  OBJECT_CONSTRUCT('semantic_view', '<sv_fqn>')
) AS result;
```

Score: `passed_count / total_count`

---

## Consistency scoring algorithm

```python
# Compare across 3 runs
def consistency_score(run1, run2, run3):
    dims = {
        "tables": (weight=0.20, values=[r['describe_tables'] for r in runs]),
        "relationships": (weight=0.30, values=[r['describe_relationships'] for r in runs]),
        "facts": (weight=0.15, values=[r['describe_facts'] for r in runs]),
        "dimensions": (weight=0.15, values=[r['describe_dimensions'] for r in runs]),
        "metrics": (weight=0.10, values=[r['describe_metrics'] for r in runs]),
        "ai_generation": (weight=0.10, values=[r['ai_generation_present'] for r in runs])
    }

    for name, (weight, values) in dims.items():
        if all same → 100%
        elif max - min <= 1 → 80%
        elif max - min <= 2 → 50%
        else → 0%

    return weighted_average
```

---

## Common assertion failures and their meaning

| Assertion fails | Root cause in skill |
|----------------|---------------------|
| `ddl_executes` | Phase 5 self-check missed a syntax error; check alias=column rule |
| `describe_relationships < 1` | Phase 4 didn't detect relationships; FK naming pattern didn't match |
| `describe_facts < N` | Phase 3 classified numeric columns as SKIP; check heuristics |
| `descriptions_populated < N` | Phase 2 CORTEX.COMPLETE failed or was skipped; check model availability |
| `self_test_pass_rate < 0.5` | AI_SQL_GENERATION instructions too vague; column descriptions not helpful |
| Consistency < 75% | Phase 3 classification is non-deterministic for borderline columns |
