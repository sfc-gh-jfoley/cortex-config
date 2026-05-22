# semantic-view-ddl Test Suite

## What's tested

| Test | Fixture | Validates |
|------|---------|-----------|
| TPCH full SV | `fixtures/tpch_semantic_view.sql` | Complete 7-table DDL passes all 18 validator checks (no errors) |
| Single table | `fixtures/single_table.sql` | Minimal single-table SV passes validation (edge case) |
| Flawed audit | `fixtures/existing_sv_audit.sql` | Deliberately broken SV triggers 4 specific validator failures |
| Skill structure | — | All phase files, reference docs, and validator script exist |

## How to run

```bash
cd ~/.snowflake/cortex/skills/semantic-view-ddl
bash tests/run_tests.sh
```

Or make executable and run directly:

```bash
chmod +x tests/run_tests.sh
./tests/run_tests.sh
```

## Expected output

All tests should pass with green checkmarks. The flawed audit fixture intentionally triggers:
- `pk_on_referenced_tables` (ERROR) — customers table missing PRIMARY KEY
- `orphan_detection` (WARNING) — suppliers not in any relationship
- `synonym_overlap` (WARNING) — 'revenue' used on both fact and metric
- `alias_matches_physical` (ERROR) — `order_dt` doesn't match physical `O_ORDERDATE`

## Requirements

- Python 3.8+ (stdlib only — no pip install needed)
- No Snowflake connection required
