# Optimizer Pattern Mining

Cross-run and cross-agent analysis of optimization history. All three optimizers
(GEPA, iterative, instruction-TPE) write to these tables. Queries here surface
recurring instruction fixes and dirty-data signals.

---

## Schema

### Per-Agent Tables (co-located with agent in same DB.SCHEMA)

```sql
-- One row per optimization session
CREATE TABLE IF NOT EXISTS <DATABASE>.<SCHEMA>.<AGENT_NAME>_OPT_RUNS (
    run_id           VARCHAR NOT NULL DEFAULT UUID_STRING(),
    optimizer_type   VARCHAR NOT NULL,  -- 'ITERATIVE' | 'GEPA' | 'INSTRUCTION_TPE'
    agent_fqn        VARCHAR NOT NULL,
    sv_fqn           VARCHAR,           -- primary semantic view the agent uses
    baseline_score   FLOAT,
    final_score      FLOAT,
    delta            FLOAT,
    winner_operator  VARCHAR,           -- dominant operator in winning candidate
    generations_run  INTEGER,
    status           VARCHAR,           -- 'CONVERGED' | 'BUDGET_EXHAUSTED' | 'FAILED' | 'IN_PROGRESS'
    started_at       TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    ended_at         TIMESTAMP_NTZ,
    PRIMARY KEY (run_id)
);

-- One row per candidate / trial evaluated
CREATE TABLE IF NOT EXISTS <DATABASE>.<SCHEMA>.<AGENT_NAME>_OPT_CANDIDATES (
    candidate_id      VARCHAR NOT NULL,
    run_id            VARCHAR NOT NULL,
    generation        INTEGER NOT NULL,  -- generation (GEPA) or trial number (TPE)
    operator          VARCHAR,
    target_file       VARCHAR,
    mean_score        FLOAT,
    delta_vs_baseline FLOAT,
    regression_count  INTEGER DEFAULT 0,
    accepted          BOOLEAN DEFAULT FALSE,
    recorded_at       TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (candidate_id, run_id)
);
```

`<AGENT_NAME>_QUESTION_MANIFEST` is defined in `references/question-manifest.md`.
All three optimizers must write to it — it is not optional.

---

### Shared Cross-Agent Table

```sql
-- Created once in a designated meta schema, written to by all optimizer runs
-- across all agents. Enables cross-agent pattern queries.
CREATE TABLE IF NOT EXISTS <META_DATABASE>.<META_SCHEMA>.OPT_QUESTION_HISTORY (
    history_id       NUMBER AUTOINCREMENT,
    agent_fqn        VARCHAR NOT NULL,
    sv_fqn           VARCHAR,
    optimizer_type   VARCHAR NOT NULL,
    run_id           VARCHAR NOT NULL,
    generation       INTEGER,
    operator         VARCHAR,           -- operator active when this score was recorded
    input_id         VARCHAR NOT NULL,
    input_text       VARCHAR,
    metric_name      VARCHAR NOT NULL,
    score            FLOAT NOT NULL,
    delta_vs_baseline FLOAT,
    source           VARCHAR NOT NULL,  -- 'gepa_gen' | 'iterative_dev' | 'iterative_test' | 'tpe_trial' | 'baseline'
    run_label        VARCHAR,           -- e.g. 'gepa_gen3_cand2' or 'iter5_dev_r1'
    test_category    VARCHAR,
    recorded_at      TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (history_id)
);
```

**Where to create it:** Ask the user once per account, store the FQN in `metadata.yaml`
as `opt_history_fqn`. Default: `<DATABASE>._AGENT_TOOLKIT_META.OPT_QUESTION_HISTORY`.

---

## Writing to the Tables

### Session start (all optimizers)

```sql
INSERT INTO <DATABASE>.<SCHEMA>.<AGENT_NAME>_OPT_RUNS
    (run_id, optimizer_type, agent_fqn, sv_fqn, baseline_score, status, started_at)
VALUES
    ('<run_id>', '<OPTIMIZER_TYPE>', '<AGENT_FQN>', '<SV_FQN>',
     <baseline_score>, 'IN_PROGRESS', CURRENT_TIMESTAMP());
```

Store `<run_id>` (a UUID) in local state for the duration of the session.

### Per candidate / trial (all optimizers)

```sql
INSERT INTO <DATABASE>.<SCHEMA>.<AGENT_NAME>_OPT_CANDIDATES
    (candidate_id, run_id, generation, operator, target_file,
     mean_score, delta_vs_baseline, regression_count, accepted)
VALUES
    ('<candidate_id>', '<run_id>', <generation>, '<operator>', '<target_file>',
     <mean_score>, <delta_vs_baseline>, <regression_count>, <accepted>);
```

### Per question, per eval run (all optimizers — mandatory)

After extracting results from `GET_AI_EVALUATION_DATA`, insert into both
`QUESTION_MANIFEST` (per the pattern in `references/question-manifest.md`) and
`OPT_QUESTION_HISTORY`:

```sql
INSERT INTO <META_DATABASE>.<META_SCHEMA>.OPT_QUESTION_HISTORY
    (agent_fqn, sv_fqn, optimizer_type, run_id, generation, operator,
     input_id, input_text, metric_name, score, delta_vs_baseline,
     source, run_label, test_category)
SELECT
    '<AGENT_FQN>',
    '<SV_FQN>',
    '<OPTIMIZER_TYPE>',
    '<run_id>',
    <generation>,
    '<operator>',
    INPUT_ID,
    INPUT,
    METRIC_NAME,
    EVAL_AGG_SCORE,
    EVAL_AGG_SCORE - <baseline_score>,
    '<source>',
    '<run_label>',
    TEST_CATEGORY
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
    '<DATABASE>', '<SCHEMA>', '<CANDIDATE_AGENT_NAME>',
    'CORTEX AGENT', '<run_name>'))
WHERE METRIC_NAME IS NOT NULL;
```

### Session end (all optimizers)

```sql
UPDATE <DATABASE>.<SCHEMA>.<AGENT_NAME>_OPT_RUNS
SET final_score    = <final_score>,
    delta          = <final_score> - baseline_score,
    winner_operator = '<winner_operator>',
    generations_run = <generations_run>,
    status         = '<CONVERGED|BUDGET_EXHAUSTED|FAILED>',
    ended_at       = CURRENT_TIMESTAMP()
WHERE run_id = '<run_id>';
```

---

## Pattern Queries

### 1. Recurring instruction fix — "What operator reliably helps across agents?"

```sql
SELECT
    operator,
    test_category,
    COUNT(DISTINCT agent_fqn)         AS agents_affected,
    COUNT(DISTINCT run_id)            AS runs_applied,
    ROUND(AVG(delta_vs_baseline), 3)  AS avg_lift,
    ROUND(MIN(delta_vs_baseline), 3)  AS min_lift,
    ROUND(MAX(delta_vs_baseline), 3)  AS max_lift
FROM <META_DATABASE>.<META_SCHEMA>.OPT_QUESTION_HISTORY
WHERE operator IS NOT NULL
  AND metric_name = 'answer_correctness'
  AND source NOT IN ('baseline')
GROUP BY operator, test_category
HAVING agents_affected >= 2
   AND avg_lift > 0.08
ORDER BY avg_lift DESC;
```

**Signal:** `add_routing_rule` lifts 4 agents by 12pp on average → the SV routing
descriptions may be the root cause. Fix the SV tool description instead of
re-applying the operator per agent.

---

### 2. Governance signal — "What questions resist all optimization?"

When a question fails across multiple agents, multiple runs, and multiple operators,
instruction optimization is not the problem. The root cause is somewhere in the
governance stack — which is broad. This query surfaces the candidates; the
escalation table below guides where to look.

```sql
SELECT
    sv_fqn,
    input_text,
    COUNT(DISTINCT agent_fqn)    AS agents_failed,
    COUNT(DISTINCT run_id)       AS runs_failed,
    COUNT(DISTINCT operator)     AS operators_tried,
    ROUND(AVG(score), 3)         AS avg_score,
    MAX(score)                   AS best_ever
FROM <META_DATABASE>.<META_SCHEMA>.OPT_QUESTION_HISTORY
WHERE metric_name = 'answer_correctness'
GROUP BY sv_fqn, input_text
HAVING agents_failed >= 2
   AND operators_tried >= 4
   AND avg_score < 0.4
ORDER BY agents_failed DESC, avg_score ASC;
```

**Signal:** Instruction optimization cannot fix this. The problem is upstream.
See Escalation Rules below for a triage taxonomy.

---

### 3. Score trajectory — "Is this agent improving across optimizer runs?"

```sql
SELECT
    optimizer_type,
    started_at::DATE      AS run_date,
    baseline_score,
    final_score,
    delta,
    winner_operator,
    status
FROM <DATABASE>.<SCHEMA>.<AGENT_NAME>_OPT_RUNS
ORDER BY started_at;
```

---

### 4. Operator ROI — "Which operators are worth the eval budget?"

```sql
SELECT
    c.operator,
    COUNT(*)                               AS times_tried,
    SUM(CASE WHEN c.accepted THEN 1 END)   AS times_accepted,
    ROUND(AVG(c.delta_vs_baseline), 3)     AS avg_delta,
    ROUND(AVG(c.mean_score), 3)            AS avg_score
FROM <DATABASE>.<SCHEMA>.<AGENT_NAME>_OPT_CANDIDATES c
GROUP BY c.operator
ORDER BY avg_delta DESC;
```

---

### 5. Hard questions — "What never gets fixed for this agent?"

```sql
SELECT
    input_id,
    MAX(input_text)                    AS question,
    COUNT(DISTINCT run_label)          AS total_evals,
    ROUND(AVG(score), 3)               AS avg_score,
    MAX(score)                         AS best_ever,
    COUNT(DISTINCT operator)           AS operators_tried,
    MIN(recorded_at)::DATE             AS first_seen,
    MAX(recorded_at)::DATE             AS last_seen
FROM <DATABASE>.<SCHEMA>.<AGENT_NAME>_QUESTION_MANIFEST
WHERE metric_name = 'answer_correctness'
GROUP BY input_id
HAVING avg_score < 0.5
   AND total_evals >= 3
ORDER BY avg_score ASC, total_evals DESC;
```

---

## Escalation Rules

When Pattern Query 2 surfaces a question, the failure is a governance signal —
not an instruction problem. The root cause could be anywhere in the data layer.
The taxonomy below is intentionally broad: the point is to pattern-hunt, not
to pre-narrow the search.

### Triage taxonomy

**1. View chain complexity**
The SV's source tables are themselves views, and those views join other views.
By the time the SV resolves the question, the lineage is a spider web —
columns get renamed, aggregated, or filtered at multiple layers in ways the
agent cannot reason about from the SV definition alone.

→ Run `cortex lineage <sv_fqn> --direction upstream --tree`
→ Look for depth > 3 hops or fanout joins in intermediate views
→ Fix: materialize the intermediate views as base tables or dynamic tables,
  or flatten the SV to reference base tables directly

---

**2. Type casting and implicit conversion**
A column that looks numeric is stored as VARCHAR. Dates stored as strings.
VARIANT columns that need TRY_PARSE_JSON. The SV exposes the raw type and the
agent generates SQL that either fails silently or returns wrong results.

→ Check `INFORMATION_SCHEMA.COLUMNS` for columns where DATA_TYPE doesn't match
  the question domain (e.g., a "revenue" column that is VARCHAR)
→ Check if any SV dimension or metric uses CAST() or TRY_TO_*() — these are
  signals that the source column has the wrong type
→ Fix: add explicit CAST in the SV expression, or fix upstream column type

---

**3. Column naming — ambiguous, inconsistent, or opaque**
Column names that are abbreviations, system-generated codes, or conflict with
natural-language question terms. The agent cannot map "what is the ARR" to
`NET_ANNUAL_RECURRING_REVENUE_EXCL_DISCOUNTS` without a description. The SV has
no description field filled in, or the description doesn't match how users phrase
the concept.

→ Run sv-audit — check description coverage and clarity scores
→ Look for columns with no description, or descriptions that don't include
  business aliases (ARR, MRR, churn, etc.)
→ Fix: add aliases and business-language descriptions to the SV DDL

---

**4. Stale or missing data**
The question asks about a time period or entity for which the source table has
no rows, stale snapshots, or incomplete incremental loads. The agent returns
a correct SQL query, but the result is empty or wrong because the data isn't there.

→ Check source table freshness: `MAX(load_timestamp)` or equivalent
→ Check whether the question's time range falls within the data's coverage
→ Fix: pipeline issue — not fixable by agent or SV changes. Flag as known
  limitation until data is current.

---

**5. Access and permission gaps**
The agent's role cannot see certain tables, schemas, or columns that the
question requires. The SV definition references objects the agent role can
describe but not query at runtime.

→ Run `SHOW GRANTS ON TABLE <source_table>` for each SV source
→ Confirm the agent's role has SELECT on all sources, not just the SV itself
→ Fix: data-governance — grant access or use a masking policy

---

**6. Semantic model gaps (SV definition)**
The SV is structurally correct but missing a relationship, metric, or dimension
the question needs. The agent can't answer because the SV literally does not
expose the concept — it's an sv-ddl problem, not a data problem.

→ Run sv-coverage-checker against the failing question
→ If verdict is NOT_ANSWERABLE with failure mode TABLE_NOT_REGISTERED or
  COLUMN_NOT_EXPOSED → SV gap, not governance
→ Fix: sv-ddl to add the missing table or column

---

**7. Business logic embedded in data**
The "correct" answer to the question depends on business rules that are
applied inconsistently upstream — e.g., revenue recognition rules applied
differently across fiscal quarters, or customer segmentation logic that
changed mid-dataset. No instruction or SV change can fix this because the
ground truth itself is ambiguous.

→ Signal: `best_ever < 0.3` across 5+ operators AND multiple agents
→ Also: ground truth answers are inconsistent when you re-generate them
→ Fix: governance — define the canonical business rule, apply it uniformly
  upstream, then regenerate ground truth

---

### Summary routing

| Primary signal | Most likely cause | First step |
|---|---|---|
| Same question fails on same `sv_fqn` across 2+ agents | SV definition gap or naming | sv-coverage-checker → sv-audit |
| Same question fails across agents using DIFFERENT `sv_fqn` | Question formulation or business logic | Review ground truth; check eval dataset |
| Question involves numeric/date column, score near zero | Type casting | `INFORMATION_SCHEMA.COLUMNS` on source tables |
| Question works sometimes, fails sometimes (score 0.2–0.5) | Stale data or access gap | Freshness check; `SHOW GRANTS` |
| `best_ever < 0.2` across all agents and operators | Business logic ambiguity OR eval ground truth error | Re-review ground truth; escalate to data owner |
| SV has >3 upstream view hops | View chain complexity | `cortex lineage --tree` |
