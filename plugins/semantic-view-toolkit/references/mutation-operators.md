# Mutation Operators

Catalog of 10 semantic view mutation operators for GEPA evolutionary optimization.

## Operator Summary

| Operator | Target | What it does | Signal (when to use) |
|----------|--------|--------------|----------------------|
| `add_synonym` | Dimensions, Facts | Add alternate names | VQR failures where user phrasing doesn't match column names |
| `improve_description` | Any column | Rewrite description with CORTEX.COMPLETE | Analyst picks wrong column (ambiguity) |
| `add_filter` | Dimensions | Add common WHERE patterns as named filters | Repeated filter logic in VQR SQL |
| `add_vqr` | SV-level | Synthesize new verified query | Low overall sql_correctness |
| `add_metric` | SV-level | Define new aggregate metric | User asks aggregation, Analyst picks wrong agg/column |
| `refine_metric_expr` | Existing metric | Fix metric expression or default_aggregation | Metric produces wrong numbers |
| `add_metric_description` | Existing metric | Add/improve description + synonyms | Analyst doesn't select right metric |
| `change_relationship` | Relationships | Change join type, add missing relationship | Wrong joins in generated SQL |
| `add_time_dimension` | Dimensions | Promote DATE/TIMESTAMP to time_dimension | Time-based queries fail |
| `remove_column` | Facts/Dims | Drop noisy/confusing columns | Analyst picks wrong column due to too many similar options |

---

## Detailed Operator Specifications

### 1. add_synonym

**Target:** Dimension and Fact column definitions

**Description:** Add 2-3 natural language synonyms that users might say when referring to a column. Synonyms help Cortex Analyst map user phrasing to the correct physical column.

**Signal (when to use):**
- VQR evaluation shows Analyst selecting wrong column because user phrasing doesn't match column name
- Column has a technical name (e.g., `CUST_NBR`) that users call differently ("customer number", "account number")

**Anti-patterns (when NOT to use):**
- Column already has 3+ synonyms — more isn't better
- The column name is already natural language (e.g., `CUSTOMER_NAME`)
- Adding generic synonyms that overlap with other columns

**LLM Prompt Template:**
```
Review the following column definition and add 2-3 natural language synonyms that business users would use to refer to this data. Only add synonyms that are meaningfully different from the column name and existing synonyms.

Column: {column_name}
Table: {table_alias}
Current description: {description}
Current synonyms: {existing_synonyms}

Return ONLY the new synonyms list (including existing ones) as a JSON array of strings.
```

---

### 2. improve_description

**Target:** Any column (fact, dimension, or metric) with a missing or vague description

**Description:** Rewrite the column description to be more specific about business meaning, expected values, and common usage patterns.

**Signal (when to use):**
- Analyst picks wrong column when multiple similar columns exist
- Column description is empty or generic (e.g., "Status field")
- Eval shows confusion between columns with similar names but different meanings

**Anti-patterns (when NOT to use):**
- Column already has a detailed, accurate description
- The column name is self-explanatory AND no ambiguity exists
- Description changes won't help because the issue is wrong relationships

**LLM Prompt Template:**
```
Rewrite this column description to help a text-to-SQL model pick the correct column. The description should explain:
1. What business concept this column represents
2. Expected value format or range (if applicable)
3. How this column differs from similar columns

Column: {column_name}
Table: {table_alias}
Data type: {data_type}
Current description: {current_description}
Similar columns in SV: {similar_columns}

Return ONLY the new description as a plain string (max 100 words).
```

---

### 3. add_filter

**Target:** Dimension columns that have common WHERE clause patterns

**Description:** Add named filters that encapsulate frequent WHERE conditions, making it easier for Analyst to apply standard data subsets.

**Signal (when to use):**
- Multiple VQRs share the same filter logic (e.g., `WHERE status = 'ACTIVE'`)
- Users frequently ask about a specific subset (e.g., "show me only this year's data")
- Eval shows Analyst generating correct queries but missing standard filters

**Anti-patterns (when NOT to use):**
- Filter is too specific to be reusable (one-off condition)
- Filter references columns not in the semantic view
- Adding filters that conflict with each other

**LLM Prompt Template:**
```
Based on this column's typical usage patterns, suggest a named filter that captures a common WHERE condition.

Column: {column_name}
Table: {table_alias}
Data type: {data_type}
Sample values: {sample_values}
Common VQR patterns involving this column: {vqr_patterns}

Return a JSON object with: {"name": "filter_name", "expression": "SQL condition", "description": "what it filters"}
```

---

### 4. add_vqr

**Target:** Semantic view level (verified_queries section)

**Description:** Synthesize a new verified query that tests a specific analytical capability not well-covered by existing VQRs.

**Signal (when to use):**
- Overall sql_correctness score is low (< 0.70)
- Existing VQRs don't cover certain join paths or aggregation patterns
- Analyst struggles with a specific type of question

**Anti-patterns (when NOT to use):**
- Already have 20+ VQRs (diminishing returns)
- New VQR is very similar to an existing one
- New VQR tests functionality outside the SV's scope

**LLM Prompt Template:**
```
Generate a verified query (VQR) that tests a capability NOT well-covered by existing VQRs.

Current SV tables: {table_list}
Current relationships: {relationships}
Existing VQR questions: {existing_questions}

The new VQR should test one of: multi-table joins, date filtering, aggregation with GROUP BY, HAVING clause, or subqueries.

Return a JSON object with: {"question": "natural language question", "sql": "correct SQL", "verified": true}
The SQL must ONLY use tables and columns defined in this semantic view.
```

---

### 5. add_metric

**Target:** Semantic view metrics section

**Description:** Define a new aggregate metric that answers a common business question. Metrics provide pre-built calculations that Analyst can reference directly.

**Signal (when to use):**
- User asks for an aggregation and Analyst picks the wrong column or aggregation function
- A common calculation requires joining multiple tables and would benefit from pre-definition
- Eval shows correct table selection but wrong aggregation logic

**Anti-patterns (when NOT to use):**
- Metric is a simple SUM/COUNT that Analyst handles well without explicit definition
- Metric duplicates an existing one with slightly different naming
- Metric expression references columns not in the SV

**LLM Prompt Template:**
```
Define a new metric for this semantic view that answers a common business question.

Available tables: {table_list}
Available columns: {column_list}
Existing metrics: {existing_metrics}
Failed eval question (if applicable): {failed_question}

Return a JSON object with: {"name": "METRIC_NAME", "expr": "aggregate expression", "description": "what it measures", "default_aggregation": "SUM|AVG|COUNT|MIN|MAX"}
```

---

### 6. refine_metric_expr

**Target:** An existing metric with incorrect expression or default_aggregation

**Description:** Fix a metric that produces wrong numbers due to aggregation errors, NULL handling issues, or double-counting from joins.

**Signal (when to use):**
- Metric produces wrong results compared to known correct answers
- VQR evaluation shows the metric being used but producing incorrect output
- Double-counting detected (SUM without DISTINCT on joined data)

**Anti-patterns (when NOT to use):**
- The metric expression is correct but the question interpretation is wrong
- Issue is in relationships (wrong joins), not the metric itself
- Metric is rarely used (better to remove than refine)

**LLM Prompt Template:**
```
Fix this metric expression. It currently produces incorrect results.

Metric name: {metric_name}
Current expression: {current_expr}
Current default_aggregation: {default_agg}
Expected result for test query: {expected}
Actual result: {actual}
Likely cause: {diagnosis}

Common issues: double-counting from joins (need DISTINCT), wrong NULL handling, incorrect column reference.

Return a JSON object with: {"expr": "fixed expression", "default_aggregation": "correct agg function"}
```

---

### 7. add_metric_description

**Target:** Metrics with missing or unclear descriptions/synonyms

**Description:** Add or improve metric description and synonyms so Analyst can correctly identify when users are asking for this metric.

**Signal (when to use):**
- Analyst doesn't select the right metric for user questions that clearly ask for it
- Metric name is technical (e.g., `GMV`) and users say "gross sales" or "total merchandise"
- Multiple metrics exist and Analyst can't distinguish between them

**Anti-patterns (when NOT to use):**
- Metric already has clear description and matching synonyms
- The issue is the metric expression, not discoverability
- Adding synonyms that overlap with other metrics (creates ambiguity)

**LLM Prompt Template:**
```
Add a clear description and 2-3 synonyms to this metric.

Metric name: {metric_name}
Expression: {expr}
Default aggregation: {default_agg}
Current description: {current_description}
Other metrics in SV: {other_metrics}

The description should explain what business question this metric answers and in what units.
Synonyms should be alternative ways users might ask for this metric.

Return a JSON object with: {"description": "clear explanation", "synonyms": ["alt1", "alt2"]}
```

---

### 8. change_relationship

**Target:** RELATIONSHIPS section

**Description:** Change join type, fix join keys, or add a missing relationship between tables.

**Signal (when to use):**
- Generated SQL uses wrong joins (e.g., INNER when LEFT is needed, losing rows)
- Two tables are used together but no relationship is defined
- Relationship uses wrong column pair (generating cartesian products or wrong matches)

**Anti-patterns (when NOT to use):**
- The join is correct but the filter is wrong (that's a filter issue)
- Adding a relationship between tables that shouldn't be joined directly
- Changing to LEFT JOIN when INNER is semantically correct (and losing rows is desired)

**LLM Prompt Template:**
```
Fix or add a relationship between these tables.

Current relationships: {current_relationships}
Problem observed: {problem_description}
Tables involved: {table_a}, {table_b}
Available join columns in {table_a}: {cols_a}
Available join columns in {table_b}: {cols_b}

Return a JSON object with: {"from_table": "alias_a", "to_table": "alias_b", "from_column": "col_a", "to_column": "col_b", "join_type": "LEFT OUTER|INNER|FULL OUTER"}
```

---

### 9. add_time_dimension

**Target:** DATE/TIMESTAMP columns not yet marked as time dimensions

**Description:** Promote a date column to `IS_TIME_DIMENSION => TRUE`, enabling time-series analysis support.

**Signal (when to use):**
- Time-based queries fail or produce unexpected results
- Users ask "show me revenue over time" but Analyst doesn't recognize the date column as temporal
- Multiple date columns exist and Analyst picks the wrong one for time-series

**Anti-patterns (when NOT to use):**
- Column is not actually a primary time axis (e.g., `updated_at` vs `order_date`)
- Table already has a designated time dimension
- Column is rarely used for time-series (it's just metadata)

**LLM Prompt Template:**
```
Identify which DATE/TIMESTAMP column should be marked as the time dimension for this table.

Table: {table_alias}
Date/timestamp columns: {date_columns}
Column descriptions: {descriptions}
Usage frequency: {usage_data}

The time dimension should be the primary temporal axis that users analyze trends over.

Return the column name to mark as IS_TIME_DIMENSION.
```

---

### 10. remove_column

**Target:** Fact or Dimension columns causing ambiguity

**Description:** Remove a column that confuses Cortex Analyst due to too many similar options or overlapping meaning with other columns.

**Signal (when to use):**
- Analyst consistently picks the wrong column among similar options
- Column is never (or rarely) queried according to ACCESS_HISTORY
- Column name overlaps with another (e.g., two different `STATUS` columns)

**Anti-patterns (when NOT to use):**
- Column is the target of a relationship (removing breaks joins)
- Column is used in a metric expression
- Column is a primary key
- Column is the only representative of important information

**LLM Prompt Template:**
```
Evaluate whether this column should be removed from the semantic view.

Column: {column_name}
Table: {table_alias}
Description: {description}
Usage count (90 days): {usage_count}
Similar columns in SV: {similar_columns}

Criteria for removal:
- Rarely accessed (< 5 queries in 90 days)
- Name overlaps with higher-priority column
- Not referenced in relationships or metrics

Return: {"remove": true/false, "reason": "explanation"}
```
