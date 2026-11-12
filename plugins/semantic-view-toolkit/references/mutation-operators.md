# SV Mutation Operators

Operators 1-10 are the GEPA operators. Their list and prompt templates live in `scripts/mutate.py` (`OPERATORS`, `PROMPT_TEMPLATES`); this file does not repeat the prompts. Operators 11-13 are used only by sv-iterative-optimizer and are not in `mutate.py`.

Every GEPA prompt has a `{failures}` block (failed questions, expected vs generated SQL, failure class) and a `{prior_wins}` block (short summary of winning changes, "do not undo these"), and asks for the complete modified DDL only; `candidate.py rewrite-ddl` sets the header. Syntax for every clause: `skills/sv-ddl/reference/ddl_syntax.md`.

## GEPA operators (from `mutate.py`)

| # | Operator | DDL part changed | Use when | Avoid when |
|---|---|---|---|---|
| 1 | `add_synonym` | `WITH SYNONYMS = (...)` on facts/dimensions | User wording differs from column names | Column already has 3+ synonyms, or the synonym would also fit another column |
| 2 | `improve_description` | `COMMENT = '...'` on columns | Analyst picks the wrong column | Naming, not description, is the problem |
| 3 | `add_filter` | BOOLEAN fact with `LABELS = (FILTER)` | Failures repeat the same WHERE pattern | The condition is dynamic |
| 4 | `add_vqr` | `AI_VERIFIED_QUERIES` entry | Untaught question patterns | SQL cannot be checked against the tables |
| 5 | `add_metric` | `METRICS` | Generated SQL aggregates wrongly for a common question | A metric already answers it |
| 6 | `refine_metric_expr` | One metric expression | A metric returns wrong numbers (aggregation, NULLs, ratio denominator, join fan-out) | Metrics would be removed |
| 7 | `add_metric_description` | Metric `COMMENT` and synonyms | Analyst picks the wrong metric | Expression or aggregation is the problem |
| 8 | `change_relationship` | `RELATIONSHIPS` | Wrong or missing joins in generated SQL | Join keys cannot be verified |
| 9 | `add_time_dimension` | DATE/TIMESTAMP columns in `DIMENSIONS` (the DDL has no separate time-dimension kind) | Time questions fail | Column is an ID that merely holds dates |
| 10 | `remove_column` | Drops 2-3 noisy columns | Many near-duplicate columns confuse the analyst | Column is a key, used in a metric, or used in a verified query |

Operator names are matched exactly when crediting weights (`add_metric_description` never credits `add_metric`).

## Iterative-optimizer-only operators

These are not selectable by GEPA.

- **11. `sync_metric_definitions_across_tables`**: the same metric name has different expressions on two tables. Either align the weaker one or rename one. Skip when the difference is intentional. Renaming can break verified queries.
- **12. `extract_metric_filter_to_fact`**: the same `CASE WHEN` filter appears in several metrics or verified queries. Move it into a named fact and simplify the metric. Skip for a single use or a dynamic condition.
- **13. `detect_contaminated_vqr_baseline`** (read-only check, not a mutation): classify verified queries as HEALTHY or CONTAMINATED when a metric's filter is missing from the query SQL, and flag rather than edit them. Do not flag queries that intentionally omit the filter.

After applying 11-12, confirm the candidate compiles with `DESCRIBE SEMANTIC VIEW` on the candidate.

## Operator choice from failure signals

| Failure | Primary | Secondary |
|---|---|---|
| Wrong table or join | `change_relationship` | none |
| Wrong column | `improve_description` | `add_synonym` |
| Wrong aggregation | `add_metric` | `refine_metric_expr` |
| Wrong filter | `add_filter` | none |
| Wrong time handling | `add_time_dimension` | `improve_description` |
| SQL syntax error | fix the DDL by hand | none |
| Analyst refuses | `add_vqr` | none |
| Low overall score | `add_vqr` | `add_metric` |

GEPA picks operators by weight (`mutate.py select-operator`); weights start even and move with score deltas (`references/tournament-rules.md`). A candidate gets one mutation by default; combine two only with different operators.
