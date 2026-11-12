---
name: sv-coverage-checker
description: >
  Coverage checker for physical-table SQL against a semantic view. Runs EXPLAIN on each SQL
  statement in a table you supply, parses the semantic view's GET_DDL, and reports structural
  gaps plus per-question ANSWERABLE / NOT_ANSWERABLE verdicts. Independent of
  EXECUTE_AI_EVALUATION: it does not read the view's verified queries.
  Gap types: TABLE_NOT_REGISTERED, COLUMN_NOT_EXPOSED, RELATIONSHIP_MISSING.
triggers:
  - coverage check
  - SV coverage
  - GT SQL coverage
  - which GT questions are answerable
  - explain plan manifest
  - structural gap report
  - SV gap analysis
  - validate SV against eval set
  - answerable questions
  - check SV gaps
---

# sv-coverage-checker

Check whether a semantic view structurally covers a set of reference SQL statements, before or
alongside an evaluation. It is a structural diff, not an accuracy score.

**Input is not the evaluation input.** Analyst evaluation (`sv-evaluation`) uses the verified queries
stored in the view, whose SQL is written against logical names. This checker takes a separate table of
**physical-table SQL** (`QUESTION_ID VARCHAR, SQL_TEXT VARCHAR`, at most 500 rows) because it runs
`EXPLAIN USING TABULAR` on each statement. VQR SQL that uses logical tables or `__` prefixes will report
`EXPLAIN_FAILED`; translate it first (see the VQR dry-run in `../sv-evaluation/SKILL.md`).

## Execution Mode

Inherits the session mode from the toolkit router. The procedure is read-only apart from `EXPLAIN`, which
runs with the caller's rights (`EXECUTE AS CALLER`) on SQL text from the supplied table, so only point it
at tables you trust. Identifiers must be plain (`[A-Za-z0-9_$]` segments, up to three parts).

## Deploy (once per schema)

The stage must exist before the upload:

```bash
snow sql -c <conn> --database <DB> --schema <SCHEMA> -q "CREATE STAGE IF NOT EXISTS SV_TOOLKIT_STAGE"
snow sql -c <conn> --database <DB> --schema <SCHEMA> -q "PUT file://$PWD/sv_coverage_checker.py @SV_TOOLKIT_STAGE/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE"
snow sql -c <conn> --database <DB> --schema <SCHEMA> -f sv_coverage_checker_deploy.sql
```

## Run

```sql
CALL <DB>.<SCHEMA>.SV_COVERAGE_CHECKER('<DB>.<SCHEMA>.GT_SQL_TABLE', '<DB>.<SCHEMA>.<SV_NAME>');
```

Two arguments only. (An earlier `validate_data` option was removed: it could not be set through CALL,
and it executed full queries and returned raw data rows.)

## Output

A VARIANT with five keys:

- `checker_version`
- `gaps[]`: `{gap_type, physical_table, element, detail}`; `gap_type` is `TABLE_NOT_REGISTERED`, `COLUMN_NOT_EXPOSED` or `RELATIONSHIP_MISSING`.
- `verdicts[]`: `{question_id, status, failure_mode, gap_detail, warnings, confidence}`.
- `summary{}`: `total_questions`, `answerable`, `not_answerable`, `unknown`, `explain_failed`, `skipped`, `unique_gaps`.
- `warnings[]`: parser warnings (messages), including `SV_PARSE_WARNING` entries about DDL fragments it could not interpret.

Verdict `status` values:

| Status | Meaning |
|---|---|
| `ANSWERABLE` | No gaps and no blocking parse warning |
| `NOT_ANSWERABLE` | At least one gap for this question; `failure_mode` is the first gap type |
| `UNKNOWN` | A blocking parse warning (unhandled join type, unresolved alias, no tables extracted) means the result cannot be trusted |
| `EXPLAIN_FAILED` | `EXPLAIN` failed for the SQL (invalid SQL, missing object, logical names) |
| `SKIPPED` | `SQL_TEXT` is NULL or empty |

`gaps[]` is computed over all questions together and keyed by physical table, so two questions that use
the same alias for different tables do not interfere.

## Fix and iterate

Apply fixes to a **candidate** copy of the view (`../../references/candidate-promotion.md`), never to production:
- `TABLE_NOT_REGISTERED`: add the table to `TABLES`.
- `COLUMN_NOT_EXPOSED`: expose the column as a dimension, fact or metric.
- `RELATIONSHIP_MISSING`: add a `RELATIONSHIPS` entry.

Re-run against the candidate until `not_answerable = 0` and `unknown = 0`.

## Notes and limits

- Columns used inside dimension/fact/metric expressions count as covered; relationship key columns count as covered.
- Join types: inner, left/right/full outer, cross, semi, anti are parsed; lateral, natural, asof, range and positional joins produce an `UNKNOWN` verdict.
- `TABLES` entries may omit `PRIMARY KEY`. `REFERENCES <table>` without a column list resolves to the target's declared `PRIMARY KEY`; if none is declared the relationship is skipped with a warning.
- Not parsed: relationship forms other than `[name AS] t (cols) REFERENCES t [(cols)]`, and string literals containing unbalanced parentheses outside the quoted-comment cases the splitter handles.
- CTEs: `EXPLAIN` plans still list the physical `TableScan` rows, but if a plan has none the verdict is `UNKNOWN` (`ZERO_TABLES_EXTRACTED`).
