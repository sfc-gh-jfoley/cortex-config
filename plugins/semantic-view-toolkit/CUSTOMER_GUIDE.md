# Customer Guide: Semantic View Toolkit

## Overview

This toolkit helps you build, evaluate, and maintain Snowflake Semantic Views — the metadata layer that powers Cortex Analyst's natural language to SQL capabilities.

**You can enter anywhere in the lifecycle.** Don't have a SV? Start at discovery. Already have one? Jump to audit or evaluation.

---

## Before You Start

### Minimum Requirements

1. A Snowflake account with data you want to query via natural language
2. A role with `CORTEX_USER` database role (granted by default)
3. `IMPORTED PRIVILEGES` on `SNOWFLAKE` database (for ACCOUNT_USAGE — strongly recommended)

### Check Your Access

```sql
-- Verify ACCOUNT_USAGE
SELECT COUNT(*) FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE START_TIME >= DATEADD('day', -1, CURRENT_TIMESTAMP()) LIMIT 1;

-- Verify you can create SVs
SHOW GRANTS TO ROLE IDENTIFIER(CURRENT_ROLE());
```

---

## Path 1: Starting from Scratch

### Step 1: Discover (sv-discovery)

```
$semantic-view-toolkit
"Help me discover what semantic views I should build for MY_DATABASE"
```

The toolkit will:
- Scan FK/PK constraints, column name patterns, and query co-occurrence
- Cluster tables into recommended domain groupings
- Score confidence based on evidence strength
- Present recommendations for your approval

**Time:** scales with table count and column cardinality.

### Step 2: Create (sv-ddl)

```
"Create the Orders domain SV from the discovery recommendations"
```

The toolkit will:
- Profile each table and auto-generate column descriptions via CORTEX.COMPLETE
- Classify columns as FACT / DIMENSION / TIME_DIMENSION / METRIC
- Detect and validate relationships
- Generate DDL with 23 self-checks
- Execute and validate with sample questions

**Time:** depends on warehouse size and number of questions.

### Step 3: Bootstrap VQRs (vqr-generator)

```
"Generate verified queries for my new SV"
```

The toolkit will:
- Mine QUERY_HISTORY for real questions users have asked
- Synthesize VQR candidates with correct SQL
- Validate each candidate executes correctly
- Present for your approval before adding to the SV

**Time:** time varies by warehouse size and data volume.

### Step 4: Evaluate (sv-evaluation)

```
"Evaluate my SV — what's my baseline accuracy?"
```

The toolkit will:
- Generate eval config YAML
- Call `ANALYST_PREVIEW` against a stage-hosted YAML config to launch evaluation against your VQRs
- Poll status until complete, then retrieve normalized results
- Report accuracy %, regressions, and per-query results
- Identify which VQRs fail and suggest why

> ⚠️ **Eval path note (error 392700).** As of July 2026, `EXECUTE_AI_EVALUATION` is broken for `analyst_type='SEMANTIC VIEW'` (returns `STATUS='FAILED'`, error 392700). The toolkit's `sv-evaluation` skill uses `ANALYST_PREVIEW` + stage YAML as the working path instead. Do not attempt `EXECUTE_AI_EVALUATION` for SV evals until the procedure is fixed. See `references/eval-polling.md` for the verified `ANALYST_PREVIEW` path.

**Time:** depends on warehouse size and number of questions.

### Step 5: Optimize (sv-optimization)

```
"Optimize my SV — help me get from 60% to 90% accuracy"
```

The toolkit will:
- Analyze failures → select mutation operator → apply change
- Deploy updated SV → re-evaluate → compare scores
- Accept/reject gate — only keep changes that improve accuracy without regressions
- Repeat until accuracy goal reached or plateau detected

**Time:** depends on VQR count and eval dataset size.

---

## Path 2: I Already Have a SV

### Audit First

```
$semantic-view-toolkit
"Audit my SV: ANALYTICS_DB.PUBLIC.REVENUE_SV"
```

Gets you: missing tables, unused columns, relationship gaps, metric opportunities.

### Then Evaluate

```
"Evaluate ANALYTICS_DB.PUBLIC.REVENUE_SV"
```

Gets you: accuracy score, failing VQRs, root cause analysis.

### Then Optimize

```
"Optimize — fix the failures you found"
```

---

## Path 3: Production Maintenance

### Set Up Monitoring

```
$semantic-view-toolkit
"Watch my SVs for drift"
```

The toolkit will:
- Detect new/dropped columns in source tables
- Detect new tables in SV schemas that aren't covered
- Detect VQR staleness (time-relative queries drifting)
- Alert with recommended actions

### Periodic Audit

Re-run sv-audit quarterly to catch:
- New query patterns not served by the SV
- Tables with growing usage that should be added
- Columns that have become unused

---

## Tips for Best Results

1. **Start with 30+ days of query history** — the more usage data, the better the recommendations
2. **10-20 VQRs is the sweet spot** — enough for meaningful eval without excessive eval time
3. **Use absolute dates in VQRs** — "Q1 2025" not "last quarter" (avoids staleness)
4. **Iterate in small steps** — one mutation at a time, measure, accept/reject
5. **Don't optimize in circles** — if 3 consecutive iterations are rejected, try GEPA or accept the current accuracy as the local optimum

---

## Costs

| Operation | Cost Source |
|---|---|
| Discovery | Free (INFORMATION_SCHEMA + ACCOUNT_USAGE queries) |
| DDL creation (descriptions) | CORTEX.COMPLETE credits (~$0.01/column) |
| Evaluation | Warehouse + AI_COMPLETE judge credits per VQR |
| Optimization | Eval cost × iterations |
| GEPA | Eval cost × population_size × generations |
| Watch | Free (metadata queries only) |

---

## Glossary

| Term | Meaning |
|---|---|
| **SV** | Semantic View — schema-level Snowflake object defining business meaning |
| **VQR** | Verified Query Repository — question + expected SQL pairs for eval ground truth |
| **GEPA** | Genetic/Evolutionary Population-based Agent optimizer (adapted for SVs) |
| **Mutation operator** | A specific type of SV change (add synonym, improve description, add metric, etc.) |
| **Cohesion** | How strongly tables within a domain are queried together |
| **Isolation** | How self-contained a domain is (internal vs external co-queries) |
| **Drift** | Schema changes in source tables not reflected in the SV |
