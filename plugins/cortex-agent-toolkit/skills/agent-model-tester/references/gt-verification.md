# Ground Truth Verification

## Purpose

Verify that each INPUT_QUERY in the eval dataset can actually be answered by the
agent's underlying semantic views. Catches:
- Questions referencing nonexistent entities (typos in subscriber names, dates, etc.)
- Questions about data not present in the semantic view's tables
- Semantic views with broken underlying tables or views
- Mismatch between ground truth and what the data actually returns

## Approach: Query Semantic Views Directly

For each semantic view referenced in the agent's `tool_resources`, use Cortex Analyst
to run the INPUT_QUERY and check for non-empty results. This is cheaper and faster
than running through the full agent (no orchestration overhead, no credits for agent
reasoning).

## Step 1: Extract Semantic Views from Agent Spec

```sql
DESCRIBE AGENT {DATABASE}.{SCHEMA}.{AGENT};
```

Parse the spec JSON to find all `tool_resources` entries. Each `cortex_analyst_text_to_sql`
tool maps to a semantic view:

```
spec.tool_resources.{tool_name}.semantic_view → fully qualified semantic view name
```

Collect all unique semantic view FQNs.

## Step 2: Validate Semantic Views Exist

For each semantic view:

```sql
DESCRIBE SEMANTIC VIEW {SEMANTIC_VIEW_FQN};
```

This confirms the view exists and returns its dimensions/facts. If it fails, the
entire eval will fail — stop and report.

## Step 3: Run Verification Queries

For each INPUT_QUERY in the eval table, use `cortex analyst query` (CLI) or the
Cortex Analyst SQL API to run the question against each semantic view:

```bash
cortex analyst query "{INPUT_QUERY}" --view={SEMANTIC_VIEW_FQN}
```

Or via SQL (compile-only to check the generated SQL is valid):

```sql
-- Use CORTEX.ANALYST to generate SQL from the question
-- Then check if the generated query returns rows
```

### Interpretation

| Result | Action |
|---|---|
| Returns 1+ rows | PASS — question is answerable |
| Returns 0 rows | WARN — question may reference nonexistent data. Check if ground truth expects "no results" |
| Error / invalid SQL | FAIL — semantic view cannot process this question |
| Analyst refuses | WARN — question may be out of scope for this semantic view |

## Step 4: Report

Generate a verification report:

```
Ground Truth Verification Report
================================
Total questions: {TOTAL}
Verified (1+ rows): {PASS_COUNT}
Zero rows (check GT): {WARN_COUNT}
Errors: {FAIL_COUNT}
Analyst refused: {REFUSE_COUNT}

FAILURES:
  TEST_ID  | INPUT_QUERY (truncated)          | ERROR
  ---------|----------------------------------|------------------
  {id}     | {query[:60]}                     | {error_message}

WARNINGS (zero rows):
  TEST_ID  | INPUT_QUERY (truncated)          | GT expects no results?
  ---------|----------------------------------|----------------------
  {id}     | {query[:60]}                     | {yes/no/unknown}
```

## Gate Decision

| Condition | Action |
|---|---|
| **0 FAIL + 0 WARN** | PASS — proceed to eval |
| **FAIL > 0** | HARD STOP — fix broken questions before eval |
| **WARN > 0, FAIL = 0** | Soft gate — review warnings. If GT explicitly says "no results found", these are valid edge-case tests. Otherwise fix. |

## Performance Notes

- Verification runs one Cortex Analyst call per question per semantic view
- For a 40-question dataset with 1 semantic view: ~40 calls, ~2-3 minutes
- For multi-tool agents with 3 semantic views: route each question to the most likely view (based on TEST_CATEGORY or keyword matching), not all views
- To speed up: batch 5 questions per analyst call by combining them (less accurate but 8x faster)

## When to Re-verify

- After adding new questions to the eval table
- After modifying semantic view definitions
- After changing underlying table data
- Before every major eval sweep (quick sanity check)
