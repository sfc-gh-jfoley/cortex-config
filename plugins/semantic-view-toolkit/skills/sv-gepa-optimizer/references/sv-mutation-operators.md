# SV Mutation Operators (GEPA)

Detailed operator reference with LLM prompt templates for evolutionary semantic view DDL mutations. Used by the sv-gepa-optimizer to generate candidate mutations during population evolution.

Each operator targets a specific part of the SV DDL and is selected based on evaluation failure signals and tournament-adjusted weights.

---

## Operator Index

| # | Operator | Target DDL Section | Failure Signal |
|---|----------|-------------------|----------------|
| 1 | `add_synonym` | Column definitions (facts/dimensions) | User phrasing doesn't match column names |
| 2 | `improve_description` | Any column/metric description | Analyst picks wrong column (ambiguity) |
| 3 | `add_filter` | FILTER section | Repeated WHERE patterns in failures |
| 4 | `add_vqr` | VERIFIED_QUERIES section | Low overall accuracy, untaught patterns |
| 5 | `add_metric` | METRIC definitions | Wrong aggregation in generated SQL |
| 6 | `refine_metric_expr` | Existing METRIC expression | Metric produces wrong numbers |
| 7 | `add_metric_description` | Existing METRIC description/synonyms | Analyst doesn't select right metric |
| 8 | `change_relationship` | RELATIONSHIPS section | Wrong joins in generated SQL |
| 9 | `add_time_dimension` | Column IS_TIME_DIMENSION flag | Time-based queries fail |
| 10 | `remove_column` | Column list (facts/dimensions) | Too many similar columns, noise |
| 11 | `sync_metric_definitions_across_tables` | METRIC definitions (multi-table) | Same metric name with different filter on two tables |
| 12 | `extract_metric_filter_to_fact` | FACTS section | Repeated CASE WHEN filter on same column |
| 13 | `detect_contaminated_vqr_baseline` | AI_VERIFIED_QUERIES (read-only) | Pre-check: VQR health scan for missing metric filters |

---

## 1. add_synonym

**Target:** Dimension and Fact column definitions within table sections.

**When to use:**
- VQR evaluation shows Analyst selecting wrong column because user phrasing doesn't match column name
- Column has a technical name (e.g., `CUST_NBR`) that users call differently
- Score pattern: correct table, correct query structure, but wrong column picked

**Anti-patterns (when NOT to use):**
- Column already has 3+ synonyms (more isn't better, creates overlap)
- Column name is already natural language (e.g., `CUSTOMER_NAME`)
- Adding generic synonyms that overlap with other columns in the SV
- Issue is description-based (description unclear), not naming-based

**DDL Section Modified:**
```sql
-- Within a TABLE definition, column SYNONYM list
COLUMN customer_number
  SYNONYM 'customer number'
  SYNONYM 'account number'
  SYNONYM 'cust id'
  DESCRIPTION '...'
```

**LLM Prompt Template:**
```
You are mutating a semantic view DDL to improve Cortex Analyst accuracy.

TASK: Add 2-3 natural language synonyms to the following column that business users would naturally use when asking questions about this data.

COLUMN: {column_name}
TABLE: {table_alias}
CURRENT DESCRIPTION: {description}
EXISTING SYNONYMS: {existing_synonyms}
FAILED VQR QUESTION: {failed_question}
(The user asked the above question and Analyst picked the wrong column instead of this one)

CONSTRAINTS:
- Synonyms must be meaningfully different from the column name AND from each other
- Do NOT add synonyms that overlap with these other columns in the same SV: {other_column_names}
- Keep synonyms short (1-3 words each)
- Include the existing synonyms in your response (append, don't replace)

OUTPUT FORMAT (JSON only, no explanation):
{"synonyms": ["existing_syn1", "new_syn1", "new_syn2"]}
```

**Example Before/After:**
```sql
-- BEFORE
COLUMN cust_nbr
  DESCRIPTION 'Unique customer identifier'

-- AFTER
COLUMN cust_nbr
  SYNONYM 'customer number'
  SYNONYM 'account number'
  SYNONYM 'customer id'
  DESCRIPTION 'Unique customer identifier'
```

**Validation Rules:**
- New synonyms must not duplicate existing synonyms (case-insensitive)
- New synonyms must not match column names of other columns in the same table
- Maximum 5 synonyms per column (reject if adding would exceed)
- Each synonym must be 1-4 words

---

## 2. improve_description

**Target:** Any column (fact, dimension, metric) with a missing, vague, or ambiguous description.

**When to use:**
- Analyst picks wrong column when multiple similar columns exist
- Column description is empty or generic (e.g., "Status field", "Amount")
- Eval shows confusion between columns with similar names but different meanings

**Anti-patterns (when NOT to use):**
- Column already has a detailed, accurate description (>50 words)
- The column name is self-explanatory AND no ambiguity exists
- Issue is wrong relationships, not column confusion
- Description changes won't help because there's only one candidate column

**DDL Section Modified:**
```sql
COLUMN revenue
  DESCRIPTION 'Net revenue after all discounts, refunds, and credits. Represents final P&L amount in USD. Differs from GROSS_REVENUE which is pre-discount.'
```

**LLM Prompt Template:**
```
You are mutating a semantic view DDL to improve Cortex Analyst accuracy.

TASK: Rewrite this column description to help a text-to-SQL model correctly distinguish it from similar columns.

COLUMN: {column_name}
TABLE: {table_alias}
DATA TYPE: {data_type}
CURRENT DESCRIPTION: {current_description}
SIMILAR COLUMNS IN THIS SV (potential confusion sources):
{similar_columns_with_descriptions}

FAILED VQR: {failed_question}
WRONG COLUMN PICKED: {wrong_column_name}

REQUIREMENTS:
1. Explain what business concept this column represents (not just technical definition)
2. State expected value format or range if applicable
3. Explicitly differentiate from the similar columns listed above
4. Maximum 80 words
5. Do NOT use generic filler ("This field stores...")

OUTPUT FORMAT (JSON only, no explanation):
{"description": "Your new description here"}
```

**Example Before/After:**
```sql
-- BEFORE
COLUMN revenue
  DESCRIPTION 'Revenue amount'

-- AFTER
COLUMN revenue
  DESCRIPTION 'Net revenue in USD after discounts and refunds are applied. Use for P&L and margin calculations. For pre-discount amounts, use GROSS_REVENUE instead.'
```

**Validation Rules:**
- Description must be non-empty
- Description must be <= 100 words
- Description must not be identical to the original (no-op mutation)
- Description must reference at least one differentiating fact vs similar columns

---

## 3. add_filter

**Target:** SV-level FILTER definitions section.

**When to use:**
- Multiple VQRs share the same filter logic (e.g., `WHERE status = 'ACTIVE'`)
- Users frequently ask about a specific subset
- Eval shows Analyst generating correct queries but missing standard filters
- Score pattern: correct structure and columns but wrong or missing WHERE clause

**Anti-patterns (when NOT to use):**
- Filter is too specific to be reusable (one-off condition)
- Filter references columns not in the semantic view
- Adding filters that conflict with existing named filters
- Filter logic is complex enough to be a separate derived table

**DDL Section Modified:**
```sql
FILTER active_customers AS (
  customers.status = 'ACTIVE'
  DESCRIPTION 'Only include customers with active status. Use when question mentions active, current, or existing customers.'
)
```

**LLM Prompt Template:**
```
You are mutating a semantic view DDL to improve Cortex Analyst accuracy.

TASK: Create a named filter that captures a common WHERE condition implied by failed VQR questions.

COLUMN: {column_name}
TABLE: {table_alias}
DATA TYPE: {data_type}
SAMPLE VALUES: {sample_values}
EXISTING FILTERS IN SV: {existing_filters}

FAILED VQR QUESTIONS THAT NEEDED THIS FILTER:
{failed_questions_needing_filter}

REFERENCE SQL FILTER PATTERN: {reference_where_clause}

REQUIREMENTS:
- Filter name should be descriptive (snake_case, max 30 chars)
- Expression must reference only columns defined in this SV
- Description must explain when users would invoke this filter (what question phrasing triggers it)
- Do NOT duplicate existing filters

OUTPUT FORMAT (JSON only, no explanation):
{"name": "filter_name", "table_alias": "t", "expression": "t.column = 'VALUE'", "description": "When to apply this filter"}
```

**Example Before/After:**
```sql
-- BEFORE (no filter defined)
-- Users ask "show active customers" → Analyst doesn't filter

-- AFTER
FILTER active_customers AS (
  customers.status = 'ACTIVE'
  DESCRIPTION 'Apply when user asks about active, current, or live customers. Excludes churned, suspended, and deleted accounts.'
)
```

**Validation Rules:**
- Filter name must not conflict with existing filter names
- Filter expression must parse as valid SQL WHERE condition
- All referenced columns must exist in the SV
- Filter must not be a tautology (always true) or contradiction (always false)

---

## 4. add_vqr

**Target:** SV-level VERIFIED_QUERIES section.

**When to use:**
- Overall sql_correctness score is low (< 0.70)
- Existing VQRs don't cover certain join paths or aggregation patterns
- Analyst struggles with a specific type of question (e.g., multi-table, time-series)
- A VQR category has zero representation

**Anti-patterns (when NOT to use):**
- Already have 20+ VQRs (diminishing returns, increases eval time)
- New VQR is very similar to an existing one (teaches nothing new)
- New VQR tests functionality outside the SV's table scope
- VQR SQL would require columns not in the SV

**DDL Section Modified:**
```sql
VERIFIED_QUERIES (
  VERIFIED_QUERY vqr_monthly_revenue (
    QUESTION 'What is the monthly revenue trend for the past year?'
    VERIFIED_QUERY_SQL 'SELECT DATE_TRUNC(''month'', o.order_date) AS month, SUM(o.amount) AS revenue FROM orders o WHERE o.order_date >= DATEADD(''year'', -1, CURRENT_DATE()) GROUP BY 1 ORDER BY 1'
  )
)
```

**LLM Prompt Template:**
```
You are mutating a semantic view DDL to improve Cortex Analyst accuracy.

TASK: Generate a new verified query (VQR) that tests a capability NOT well-covered by existing VQRs.

SV TABLES AND COLUMNS:
{table_column_list}

DEFINED RELATIONSHIPS:
{relationships}

EXISTING VQR QUESTIONS (do NOT duplicate these):
{existing_vqr_questions}

FAILURE PATTERNS OBSERVED:
{failure_categories_and_counts}

REQUIREMENTS:
1. Question must be natural language that a business user would ask
2. SQL must ONLY use tables and columns defined in this semantic view
3. SQL must be syntactically valid Snowflake SQL
4. Target an uncovered capability: {suggested_capability}
   (Options: multi-table join, date filtering, aggregation with GROUP BY, HAVING, subquery, window function)
5. SQL must respect the defined relationships (correct join paths)
6. VQR name must be snake_case, unique, max 40 chars

OUTPUT FORMAT (JSON only, no explanation):
{"name": "vqr_name", "question": "natural language question", "sql": "SELECT ..."}
```

**Example Before/After:**
```sql
-- BEFORE: No VQRs test multi-table aggregation with date filter

-- AFTER
VERIFIED_QUERY vqr_quarterly_revenue_by_region (
  QUESTION 'What is the total revenue by region for the last quarter?'
  VERIFIED_QUERY_SQL 'SELECT r.region_name, SUM(o.amount) AS total_revenue FROM orders o JOIN customers c ON o.customer_id = c.id JOIN regions r ON c.region_id = r.id WHERE o.order_date >= DATEADD(''quarter'', -1, DATE_TRUNC(''quarter'', CURRENT_DATE())) AND o.order_date < DATE_TRUNC(''quarter'', CURRENT_DATE()) GROUP BY 1 ORDER BY 2 DESC'
)
```

**Validation Rules:**
- VQR name must be unique across all existing VQRs
- SQL must reference only tables defined in the SV
- SQL must reference only columns defined in the SV
- SQL must be parseable (no syntax errors)
- Question must not be semantically identical to an existing VQR question
- SQL should use relationship-defined join paths (not arbitrary joins)

---

## 5. add_metric

**Target:** SV-level or table-level METRIC definitions.

**When to use:**
- User asks for an aggregation and Analyst picks wrong column or aggregation function
- A common calculation requires a pre-built definition for consistency
- Eval shows correct table selection but wrong aggregation logic
- Multiple failures involve the same business concept (e.g., "revenue")

**Anti-patterns (when NOT to use):**
- Metric is a trivial SUM/COUNT that Analyst handles well without explicit definition
- Metric duplicates an existing one with slightly different naming
- Metric expression references columns not in the SV
- Adding too many metrics (>15) creates selection ambiguity

**DDL Section Modified:**
```sql
METRIC avg_order_value AS (
  SUM(order_amount) / NULLIF(COUNT(DISTINCT order_id), 0)
  DESCRIPTION 'Average dollar value per order. Calculated as total revenue divided by number of distinct orders.'
  DEFAULT_AGGREGATION AVG
  SYNONYMS ('AOV', 'average order size', 'mean order value')
)
```

**LLM Prompt Template:**
```
You are mutating a semantic view DDL to improve Cortex Analyst accuracy.

TASK: Define a new aggregate metric that the semantic view is currently missing.

AVAILABLE TABLES AND COLUMNS:
{table_column_list}

EXISTING METRICS (do NOT duplicate):
{existing_metrics}

FAILED VQR THAT NEEDED THIS METRIC:
  Question: {failed_question}
  Expected SQL: {reference_sql}
  Generated SQL: {generated_sql}
  Issue: Analyst used wrong aggregation/column

REQUIREMENTS:
1. Metric name: UPPER_SNAKE_CASE, max 30 chars
2. Expression must use only columns defined in the SV
3. Handle NULLs and division-by-zero (use NULLIF, COALESCE as needed)
4. Include a clear description explaining what business question it answers
5. Set default_aggregation to the most common usage (SUM, AVG, COUNT, MIN, MAX)
6. Add 2-3 synonyms (alternative names users might say)
7. Do NOT duplicate an existing metric's logic

OUTPUT FORMAT (JSON only, no explanation):
{"name": "METRIC_NAME", "expr": "aggregate expression", "description": "what it measures", "default_aggregation": "SUM|AVG|COUNT|MIN|MAX", "synonyms": ["alt1", "alt2"]}
```

**Example Before/After:**
```sql
-- BEFORE: User asks "average order value" → Analyst does AVG(amount) instead of SUM/COUNT

-- AFTER
METRIC avg_order_value AS (
  SUM(orders.amount) / NULLIF(COUNT(DISTINCT orders.order_id), 0)
  DESCRIPTION 'Average revenue per order. Total revenue divided by distinct order count.'
  DEFAULT_AGGREGATION AVG
  SYNONYM 'AOV'
  SYNONYM 'average order size'
)
```

**Validation Rules:**
- Metric name must not conflict with existing metric names
- Expression must reference only SV-defined columns (table_alias.column_name)
- Expression must not contain bare aggregates without column reference
- default_aggregation must be one of: SUM, AVG, COUNT, MIN, MAX
- Description must be non-empty and <= 80 words

---

## 6. refine_metric_expr

**Target:** An existing METRIC's expression or default_aggregation.

**When to use:**
- Metric produces wrong numbers compared to known correct answers
- VQR evaluation shows the metric being used but producing incorrect output
- Double-counting detected (SUM without DISTINCT on joined data)
- Wrong aggregation function applied

**Anti-patterns (when NOT to use):**
- The metric expression is correct but the question interpretation is wrong
- Issue is in relationships (wrong joins produce wrong input to metric)
- Metric is rarely used (better to remove than refine)
- The "wrong numbers" are due to stale data, not metric logic

**DDL Section Modified:**
```sql
-- Change the expression and/or default_aggregation of an existing metric
METRIC total_customers AS (
  COUNT(DISTINCT customers.customer_id)  -- was COUNT(*) before (double-counting from joins)
  ...
)
```

**LLM Prompt Template:**
```
You are mutating a semantic view DDL to improve Cortex Analyst accuracy.

TASK: Fix this metric expression. It currently produces incorrect results.

METRIC NAME: {metric_name}
CURRENT EXPRESSION: {current_expr}
CURRENT DEFAULT_AGGREGATION: {default_agg}

EVIDENCE OF FAILURE:
  VQR Question: {failed_question}
  Expected Result (from reference SQL): {expected_value}
  Actual Result (from metric): {actual_value}
  Reference SQL: {reference_sql}

AVAILABLE COLUMNS IN SCOPE:
{columns_in_scope}

COMMON ISSUES TO CHECK:
- Double-counting from joins (need COUNT(DISTINCT ...) or SUM(DISTINCT ...))
- Wrong NULL handling (need COALESCE or NULLIF)
- Wrong column reference (similar column names)
- Wrong aggregation function (SUM when should be COUNT, etc.)

REQUIREMENTS:
1. Fix must produce results matching the reference SQL
2. Must still use only SV-defined columns
3. Must handle edge cases (NULLs, division by zero)
4. Preserve the metric's semantic meaning

OUTPUT FORMAT (JSON only, no explanation):
{"expr": "fixed expression", "default_aggregation": "correct agg function"}
```

**Example Before/After:**
```sql
-- BEFORE (double-counts due to one-to-many join)
METRIC total_revenue AS (
  SUM(orders.amount)
  DEFAULT_AGGREGATION SUM
)

-- AFTER
METRIC total_revenue AS (
  SUM(DISTINCT orders.amount)  -- or restructure query to pre-aggregate
  DEFAULT_AGGREGATION SUM
)
```

**Validation Rules:**
- Expression must parse as valid SQL aggregate expression
- Must reference only columns in the SV
- default_aggregation must be valid (SUM, AVG, COUNT, MIN, MAX)
- New expression must differ from original (no no-op mutations)

---

## 7. add_metric_description

**Target:** Existing METRIC's DESCRIPTION and SYNONYM fields.

**When to use:**
- Analyst doesn't select the right metric for user questions that clearly ask for it
- Metric name is technical (e.g., `GMV`, `NRR`) and users say something else
- Multiple metrics exist and Analyst can't distinguish between them
- Metric has empty or overly terse description

**Anti-patterns (when NOT to use):**
- Metric already has clear description AND matching synonyms (3+)
- Issue is the metric expression, not discoverability (use refine_metric_expr)
- Adding synonyms that overlap with other metrics (creates ambiguity)

**DDL Section Modified:**
```sql
METRIC gmv AS (
  SUM(orders.gross_amount)
  DESCRIPTION 'Gross Merchandise Value - total dollar value of all merchandise sold before returns and discounts. Primary top-line revenue metric for marketplace reporting.'
  SYNONYM 'gross merchandise value'
  SYNONYM 'total sales volume'
  SYNONYM 'gross sales'
)
```

**LLM Prompt Template:**
```
You are mutating a semantic view DDL to improve Cortex Analyst accuracy.

TASK: Add a clear description and 2-3 synonyms to this metric so Cortex Analyst correctly selects it.

METRIC NAME: {metric_name}
EXPRESSION: {expr}
DEFAULT AGGREGATION: {default_agg}
CURRENT DESCRIPTION: {current_description}
CURRENT SYNONYMS: {current_synonyms}

OTHER METRICS IN SV (avoid synonym overlap):
{other_metrics_with_descriptions}

FAILED VQR (Analyst didn't use this metric when it should have):
  Question: {failed_question}
  User phrasing that should have triggered this metric: {trigger_phrase}

REQUIREMENTS:
1. Description: explain what business question this metric answers, in what units
2. Differentiate from other metrics explicitly if similar ones exist
3. Synonyms: 2-3 alternative ways users ask for this (natural language)
4. Synonyms must NOT overlap with other metric names or synonyms
5. Max 60 words for description

OUTPUT FORMAT (JSON only, no explanation):
{"description": "clear explanation", "synonyms": ["alt1", "alt2", "alt3"]}
```

**Example Before/After:**
```sql
-- BEFORE
METRIC nrr AS (
  ... expression ...
  DESCRIPTION 'NRR'
)

-- AFTER
METRIC nrr AS (
  ... expression ...
  DESCRIPTION 'Net Revenue Retention rate as a percentage. Measures revenue kept from existing customers including expansions and contractions, excluding new customers. Values > 100% indicate net expansion.'
  SYNONYM 'net revenue retention'
  SYNONYM 'dollar retention rate'
  SYNONYM 'revenue retention'
)
```

**Validation Rules:**
- Description must be non-empty and differ from original
- Synonyms must not duplicate other metric synonyms (case-insensitive check)
- Combined synonyms (existing + new) must not exceed 5
- Description must be <= 80 words

---

## 8. change_relationship

**Target:** RELATIONSHIPS section of the SV DDL.

**When to use:**
- Generated SQL uses wrong joins (INNER when LEFT needed, missing intermediate table)
- Two tables used together in reference SQL but no relationship defined
- Relationship uses wrong column pair (generates wrong matches or cartesian products)
- Eval shows correct tables selected but wrong join produces wrong row count

**Anti-patterns (when NOT to use):**
- The join is correct but the filter is wrong (that's add_filter)
- Adding a relationship between tables that shouldn't be joined directly
- Changing to LEFT JOIN when INNER is semantically correct (intentional row filtering)
- Problem is column selection, not join logic

**DDL Section Modified:**
```sql
RELATIONSHIPS (
  orders_to_customers AS (
    orders REFERENCES customers (customer_id REFERENCES id)
    RELATIONSHIP_TYPE MANY_TO_ONE
    JOIN_TYPE LEFT OUTER
  )
)
```

**LLM Prompt Template:**
```
You are mutating a semantic view DDL to improve Cortex Analyst accuracy.

TASK: Fix or add a relationship between tables to correct join behavior.

CURRENT RELATIONSHIPS:
{current_relationships_ddl}

PROBLEM OBSERVED:
  VQR Question: {failed_question}
  Generated SQL joins: {generated_joins}
  Reference SQL joins: {reference_joins}
  Issue: {problem_description}

TABLES IN SV:
{table_list_with_columns}

AVAILABLE JOIN COLUMNS (potential keys):
Table A ({table_a}): {key_columns_a}
Table B ({table_b}): {key_columns_b}

REQUIREMENTS:
1. Specify: from_table, to_table, from_column, to_column, join_type, relationship_type
2. join_type: LEFT OUTER (default, preserves all rows from left) or INNER (only matching rows)
3. relationship_type: MANY_TO_ONE, ONE_TO_MANY, MANY_TO_MANY
4. If a bridge table is needed, create two relationships instead of one
5. Do NOT create circular relationships
6. Do NOT duplicate an existing relationship

OUTPUT FORMAT (JSON only, no explanation):
For single relationship:
{"action": "add|modify|remove", "from_table": "alias_a", "to_table": "alias_b", "from_column": "col_a", "to_column": "col_b", "join_type": "LEFT OUTER", "relationship_type": "MANY_TO_ONE"}

For bridge (two relationships):
{"action": "add_bridge", "relationships": [
  {"from_table": "a", "to_table": "bridge", "from_column": "id", "to_column": "a_id", "join_type": "LEFT OUTER", "relationship_type": "ONE_TO_MANY"},
  {"from_table": "bridge", "to_table": "b", "from_column": "b_id", "to_column": "id", "join_type": "LEFT OUTER", "relationship_type": "MANY_TO_ONE"}
]}
```

**Example Before/After:**
```sql
-- BEFORE: Direct orders→products (wrong, needs line_items bridge)
RELATIONSHIPS (
  orders_to_products AS (
    orders REFERENCES products (product_id REFERENCES id)
  )
)

-- AFTER: Correct bridge through line_items
RELATIONSHIPS (
  orders_to_line_items AS (
    line_items REFERENCES orders (order_id REFERENCES id)
    RELATIONSHIP_TYPE MANY_TO_ONE
    JOIN_TYPE LEFT OUTER
  ),
  line_items_to_products AS (
    line_items REFERENCES products (product_id REFERENCES id)
    RELATIONSHIP_TYPE MANY_TO_ONE
    JOIN_TYPE LEFT OUTER
  )
)
```

**Validation Rules:**
- Both tables must exist in the SV
- Referenced columns must exist in their respective tables
- join_type must be LEFT OUTER or INNER
- No circular relationship chains (A→B→C→A)
- No duplicate relationships (same table pair and column pair)
- Relationship name must be unique

---

## 9. add_time_dimension

**Target:** DATE/TIMESTAMP columns promoted to `IS_TIME_DIMENSION => TRUE`.

**When to use:**
- Time-based queries fail or produce unexpected results
- Users ask "show me X over time" but Analyst doesn't recognize the temporal axis
- Multiple date columns exist and Analyst picks the wrong one for time-series
- No time_dimension is currently defined for a table with date columns

**Anti-patterns (when NOT to use):**
- Column is not actually a primary time axis (e.g., `updated_at` is metadata, not analytical)
- Table already has a designated time dimension (only one per table)
- Column is rarely used for time-series analysis (it's just a timestamp for auditing)
- Adding time_dimension won't fix the actual issue (wrong filter, wrong aggregation)

**DDL Section Modified:**
```sql
COLUMN order_date
  DATA_TYPE DATE
  IS_TIME_DIMENSION TRUE
  DESCRIPTION 'Primary date for order timing. The canonical time axis for all revenue and order trend analysis.'
```

**LLM Prompt Template:**
```
You are mutating a semantic view DDL to improve Cortex Analyst accuracy.

TASK: Identify and promote the correct DATE/TIMESTAMP column to time dimension status.

TABLE: {table_alias}
DATE/TIMESTAMP COLUMNS IN THIS TABLE:
{date_columns_with_descriptions}

FAILED TIME-BASED VQR:
  Question: {failed_question}
  Reference SQL date column: {reference_date_column}
  Generated SQL date column: {generated_date_column} (or "none - no time handling")

COLUMN USAGE FREQUENCY (from ACCESS_HISTORY, last 90 days):
{usage_frequency_data}

REQUIREMENTS:
1. Only ONE column per table can be IS_TIME_DIMENSION = TRUE
2. Choose the column that represents the primary analytical time axis
3. Must be DATE or TIMESTAMP type
4. Should be the column users most often GROUP BY for trends
5. If the table already has a time dimension set, return "no_change"

OUTPUT FORMAT (JSON only, no explanation):
{"column": "column_name", "reason": "why this is the primary time axis"}
or
{"column": "no_change", "reason": "existing time dimension is correct"}
```

**Example Before/After:**
```sql
-- BEFORE: No time dimension, Analyst doesn't know which date to use for trends
COLUMN created_at
  DATA_TYPE TIMESTAMP_NTZ
  DESCRIPTION 'Record creation timestamp'

COLUMN order_date
  DATA_TYPE DATE
  DESCRIPTION 'Date the order was placed'

-- AFTER: order_date promoted to time dimension
COLUMN order_date
  DATA_TYPE DATE
  IS_TIME_DIMENSION TRUE
  DESCRIPTION 'Date the order was placed. Primary time axis for order trends, revenue over time, and seasonal analysis.'
```

**Validation Rules:**
- Selected column must be DATE, TIMESTAMP_NTZ, TIMESTAMP_LTZ, or TIMESTAMP_TZ
- Only one IS_TIME_DIMENSION per table (check existing)
- Column must exist in the specified table
- If table already has a time dimension, this is a "swap" operation (remove old, add new)

---

## 10. remove_column

**Target:** Fact or Dimension columns removed from the SV DDL entirely.

**When to use:**
- Analyst consistently picks the wrong column among similar options
- Column is never (or rarely) queried according to ACCESS_HISTORY
- Column name overlaps with another more important column
- Reducing column count improves Analyst's selection accuracy

**Anti-patterns (when NOT to use):**
- Column is the target of a RELATIONSHIP (removing breaks joins)
- Column is used in a METRIC expression
- Column is a primary key referenced in relationships
- Column is the only representative of important business information
- Column is used in FILTER expressions
- Column is referenced in VQR SQL

**DDL Section Modified:**
```sql
-- Column is entirely removed from the TABLE definition
-- (no trace remains in the DDL)
```

**LLM Prompt Template:**
```
You are mutating a semantic view DDL to improve Cortex Analyst accuracy by reducing noise.

TASK: Evaluate whether this column should be removed from the semantic view to reduce ambiguity.

COLUMN: {column_name}
TABLE: {table_alias}
DATA TYPE: {data_type}
DESCRIPTION: {description}
USAGE COUNT (last 90 days from ACCESS_HISTORY): {usage_count}

SIMILAR COLUMNS IN SV THAT CAUSE CONFUSION:
{similar_columns}

DEPENDENCIES (must be clear to remove):
- Referenced in relationships: {relationship_refs}
- Referenced in metrics: {metric_refs}
- Referenced in filters: {filter_refs}
- Referenced in VQR SQL: {vqr_refs}

EVAL EVIDENCE:
  VQRs where this column was incorrectly selected: {wrong_selection_vqrs}
  VQRs where the CORRECT column (that this overlaps with): {correct_column}

REQUIREMENTS:
1. Only recommend removal if dependencies list is empty (no refs)
2. Only recommend removal if usage is low (<5 queries in 90 days) OR confusion is high
3. If the column carries unique information not available elsewhere, do NOT remove
4. Removal is permanent for this candidate — be conservative

OUTPUT FORMAT (JSON only, no explanation):
{"remove": true, "reason": "explanation of why removal improves accuracy"}
or
{"remove": false, "reason": "explanation of why column should stay"}
```

**Example Before/After:**
```sql
-- BEFORE: Two status columns causing confusion
COLUMN order_status
  DESCRIPTION 'Current order fulfillment status'

COLUMN order_state    -- rarely used, overlaps with order_status
  DESCRIPTION 'Order state'

-- AFTER: order_state removed (order_status is canonical)
COLUMN order_status
  DESCRIPTION 'Current order fulfillment status (PENDING, SHIPPED, DELIVERED, CANCELLED)'
```

**Validation Rules:**
- Column must NOT be referenced in any RELATIONSHIP definition
- Column must NOT be referenced in any METRIC expression
- Column must NOT be referenced in any FILTER expression
- Column must NOT appear in any VQR SQL (would break verified queries)
- Column must NOT be the only column of its semantic type in the SV
- If validation fails, operator returns "cannot remove — has dependencies"

---

## 11. sync_metric_definitions_across_tables

**Target:** METRIC definitions across two fact tables with the same metric name

**When to use:** Pre-optimization Check 2 flags the same metric name with different EXPR on two tables, causing LLM to generate inconsistent SQL depending on which table it routes to.

**Anti-patterns:** Do not apply if the difference is intentional (EXT table semantics differ by design). Renaming may break existing VQRs — verify before applying.

**LLM Prompt Template:**
```
Two metrics share the same name but have different filter logic.
Metric: {metric_name}
Table A ({table_a}): {expr_a}
Table B ({table_b}): {expr_b}

Decide: (A) add missing filter to weaker definition, or (B) rename one metric.
Return JSON: {"action": "align_filter"|"rename", "table": "A"|"B", "value": "new_expr_or_name"}
```

**DDL Section Modified:** METRICS (multi-table)

**Validation:** After applying, run `DESCRIBE SEMANTIC VIEW <SV_FQN>` to confirm no compilation errors. For VQR changes, re-run `detect_contaminated_vqr_baseline` to confirm HEALTHY classification.

---

## 12. extract_metric_filter_to_fact

**Target:** FACTS section (new column) + METRICS section (simplified expr)

**When to use:** A metric uses `SUM(CASE WHEN col = val THEN col ELSE 0 END)` and the same filter pattern appears in multiple VQRs or metrics. Extracting to a named FACT makes the filter visible, reduces VQR authoring errors, and ensures correct results even when the model bypasses the metric name.

**Anti-patterns:** Do not apply when the filter is used in only one place, or when the filter condition is dynamic.

**LLM Prompt Template:**
```
Extract this CASE WHEN expression into a named FACT column.
Source column: {source_col}
Filter: {filter_condition}
Current metric: {metric_name} = {metric_expr}
Table alias: {table_alias}

Return JSON: {
  "fact_name": "...",
  "fact_expr": "CASE WHEN {filter_condition} THEN {source_col} ELSE 0 END",
  "metric_expr": "SUM({fact_name})",
  "description": "..."
}
```

**DDL Section Modified:** FACTS + METRICS

**Validation:** After applying, run `DESCRIBE SEMANTIC VIEW <SV_FQN>` to confirm no compilation errors. For VQR changes, re-run `detect_contaminated_vqr_baseline` to confirm HEALTHY classification.

---

## 13. detect_contaminated_vqr_baseline

**Target:** AI_VERIFIED_QUERIES reference SQL (read-only detection)

**When to use:** As pre-optimization Check 1 — run before first eval to classify all VQRs as HEALTHY / CONTAMINATED / REVIEW against the metric filter map. Output used for read-only analysis (exclude/flag contaminated VQRs; do not modify).

**Anti-patterns:** Do not use as a mutation operator during GEPA iterations — this is diagnostic only. Do not flag VQRs that intentionally query without the filter (refund analysis questions).

**Detection logic:**
```
For each metric M with CASE WHEN <filter_col> = <filter_val> in EXPR:
  For each VQR V that aggregates <agg_col> from M:
    If V.SQL lacks "CASE WHEN <filter_col>" AND lacks "WHERE <filter_col> = <filter_val>":
      → CONTAMINATED
    Else:
      → HEALTHY
```

**DDL Section Modified:** AI_VERIFIED_QUERIES (read-only)

**Validation:** After applying, run `DESCRIBE SEMANTIC VIEW <SV_FQN>` to confirm no compilation errors. For VQR changes, re-run `detect_contaminated_vqr_baseline` to confirm HEALTHY classification.

---

## Operator Selection Strategy

### Weight-Based Selection

GEPA uses adaptive weights to select operators. Initial weights are equal; they shift based on tournament results.

**Initial weights (generation 0):**
```json
{
  "add_synonym": 0.10,
  "improve_description": 0.13,
  "add_filter": 0.10,
  "add_vqr": 0.10,
  "add_metric": 0.10,
  "refine_metric_expr": 0.10,
  "add_metric_description": 0.05,
  "change_relationship": 0.13,
  "add_time_dimension": 0.05,
  "remove_column": 0.08,
  "sync_metric_definitions_across_tables": 0.06,
  "extract_metric_filter_to_fact": 0.05,
  "detect_contaminated_vqr_baseline": 0.03
}
```

Weights are adjusted by `scripts/tournament.py` after each generation based on which operators produced winning candidates.

### Failure-Signal Mapping

When eval results are available, prefer operators that match failure patterns:

| Failure Category (from failure-analysis.md) | Primary Operator | Secondary Operator |
|---|---|---|
| Wrong table/join | `change_relationship` | - |
| Wrong column | `improve_description` | `add_synonym` |
| Wrong aggregation | `add_metric` | `refine_metric_expr` |
| Wrong filter | `add_filter` | - |
| Wrong time handling | `add_time_dimension` | `improve_description` |
| SQL syntax error | Manual DDL fix (not operator) | - |
| Analyst refuses | `add_vqr` | - |
| Low overall score | `add_vqr` | `add_metric` |
| VQR filter contamination | **Read-only analysis** (exclude/flag; do not modify) | `detect_contaminated_vqr_baseline` |
| Cross-table metric inconsistency | `sync_metric_definitions_across_tables` | `extract_metric_filter_to_fact` |

### Multi-Mutation Candidates

A single candidate can receive 1-3 mutations per generation:
- **1 mutation:** Default (conservative exploration)
- **2 mutations:** When population is converging (diversity pressure)
- **3 mutations:** Rare, only when convergence_threshold nearly reached

Each mutation in a multi-mutation candidate uses a DIFFERENT operator to avoid compounding the same type of change.
