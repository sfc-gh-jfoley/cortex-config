# Candidate-Copy Contract

> **Rule:** No skill in this toolkit creates, replaces, alters or drops a production semantic view
> (SV) while experimenting. Work happens on a uniquely named **candidate copy** cloned from the
> full `GET_DDL`. Production changes only through the `SV-PROMOTE` gate.
>
> The helper `scripts/candidate.py` enforces naming, the production guard, DDL rewriting and
> exact-name cleanup. Use it instead of hand-building names or `LIKE` patterns.

## 1. Naming

| Producer | Candidate name |
|---|---|
| sv-gepa-optimizer | `<SV>__GEPA__<run>__G<gen>__C<n>` |
| sv-iterative-optimizer, sv-audit, vqr-generator, vqr-curator, sv-rearchitect, sv-ddl Phase 7, sv-watch remediation | `<SV>__CAND__<run>` |
| sv-materialize trial | `<SV>__MAT__<run>` |

- `<run>` is `R` plus six hex characters from `candidate.py new-run`. A date alone is not unique.
- Candidates live in the **same database and schema** as the source and are derived only from the
  production view, never from another candidate.
- Names are unquoted, upper-case identifiers, at most 255 characters.
- `__` is also the logical-table prefix in VQR SQL. Never match candidates with `LIKE '%__%'` or
  `LIKE '%_CAND_%'` (`_` is a wildcard). Cleanup uses exact names from the manifest only.

## 2. Create a candidate

```bash
RUN=$(python3 scripts/candidate.py new-run | jq -r .run)
CAND=$(python3 scripts/candidate.py name --source DB.SCH.SV --kind cand --run "$RUN" | jq -r .candidate)
```

```sql
SELECT GET_DDL('SEMANTIC_VIEW', 'DB.SCH.SV');   -- save the result to a file; do not hand-edit prod
```

```bash
python3 scripts/candidate.py rewrite-ddl --source DB.SCH.SV --candidate "$CAND" < prod.sql > cand.sql
python3 scripts/candidate.py register manifest.json --run "$RUN" --source DB.SCH.SV --candidate "$CAND" --ddl-file cand.sql
```

`rewrite-ddl` changes only the header name and emits plain `CREATE SEMANTIC VIEW`. It fails if the
header names a different view, so a candidate can never be created with `OR REPLACE` or `OR ALTER`.
Deploy `cand.sql`; if the name already exists, stop. Do not replace it.

Candidates do not inherit materializations. Evaluate without them unless the run is an
`sv-materialize` trial.

Before any write, call the guard:

```bash
python3 scripts/candidate.py guard --source DB.SCH.SV --target "$CAND"
```

It exits non-zero when the target is the production view, is not a toolkit candidate name, or is in
another schema.

## 3. Mutate and evaluate

All edits go to the candidate. Evaluate with the Analyst contract in
`skills/sv-evaluation/SKILL.md` (pinned `sql_correctness` version). Set status with
`candidate.py set-status` (`created` → `evaluated` → `winner` | `discarded` | `failed`).

A candidate never becomes production by renaming or re-running the DDL against the production name
outside the promotion gate below.

## 4. Promotion (gate `SV-PROMOTE`, always OPERATOR_REQUIRED)

Present, in this order:
1. Diff of `GET_DDL` (production) vs the candidate.
2. Evaluation evidence: question set, metric version, scores for production and candidate, repeats.
3. Consumers found (below), stated as **possibly incomplete**.
4. Production grants, tags, comment and materializations, captured with `SHOW GRANTS ON SEMANTIC VIEW`,
   `GET_DDL`, and `SHOW MATERIALIZATIONS`.

Verified queries: run `python3 scripts/candidate.py vqr-diff <production.sql> <candidate.sql>`. Existing
VQRs must be byte-for-byte equivalent (whitespace aside); a removed or changed VQR is gate
`SV-VQR-MUTATE` and blocks promotion. Added VQRs are listed and need gate `VQR-GEN-INSERT` before they
reach production.

Options:

| Option | When to offer | How |
|---|---|---|
| Retarget consumers | Every consumer is a permanent object the toolkit can update | Update those objects to the candidate FQN, then `candidate.py set-status <manifest> --candidate <FQN> --status promoted`. A promoted candidate is protected from every later write and cleanup, and later runs pass `--manifest` so it can be the source of new candidates. Production is untouched. |
| Replace production | Callers exist that cannot be traced, or the name must stay | Apply the **full** approved DDL with `CREATE OR ALTER SEMANTIC VIEW` after saving a rollback copy. Re-apply captured grants, tags and materializations. `CREATE OR ALTER` unsets any property the statement omits. |
| Keep candidate | Operator wants to compare further | Mark `winner`; do not drop it. |
| Discard | Operator rejects | Mark `discarded`. |

Never choose for the operator, in any mode. Never use `CREATE OR REPLACE`; it drops grants and
materializations.

Some changes are not DDL replacements: `ALTER SEMANTIC VIEW` for a comment, `MAX_STALENESS` or a
materialization, and tag or grant changes. They cannot be tried on a candidate and promoted, so they
still go through `SV-PROMOTE`: show the exact statement and the current value, save a rollback
statement (the inverse `ALTER`, or the saved `GET_DDL`), and wait for approval. Materialization
trials run on a `mat` candidate first.

### Consumer discovery

- `cortex lineage DB.SCH.SV --direction downstream` (agents that use the SV as an Analyst tool).
- `SNOWFLAKE.ACCOUNT_USAGE.SEMANTIC_VIEW_IMPORTS` (composed views).
- A 30-day usage scan: `CORTEX_ANALYST_USAGE_HISTORY`, `CORTEX_AGENT_USAGE_HISTORY` (excludes CoWork),
  `ACCESS_HISTORY`.

These do **not** see temporary agents, REST API callers that pass the SV name, application source
code, BI or dbt configuration, shared or listed copies in other accounts, or objects the role cannot
see. If usage history shows queries that no discovered object explains, recommend
**Replace production** rather than retargeting.

## 5. Cleanup (gate `SV-CANDIDATE-CLEANUP`)

```bash
python3 scripts/candidate.py cleanup-plan manifest.json --run "$RUN"
```

The plan lists exact `DROP SEMANTIC VIEW IF EXISTS <candidate>;` statements for candidates in
`created`, `evaluated`, `discarded` or `failed`, and keeps `winner` and `promoted`. It validates
every manifest entry against the guard first, so a tampered manifest cannot name a production view.
Run it only when the run is finished or abandoned, and show the plan to the operator first.

## 6. Manifest

JSON file with one entry per candidate: `run`, `source`, `candidate`, `parent`, `ddl_sha256`,
`status`. Store it next to the run's other state and mirror rows into
`_SV_TOOLKIT_META.PROMOTIONS` when that schema is in use.
