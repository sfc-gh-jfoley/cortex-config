# Tests for semantic-view-discovery

## Test Strategy

Since this is a prompt-only skill (no Python scripts), testing validates:
1. **Structural completeness** — all referenced phase files exist
2. **SQL correctness** — queries in phase files use valid Snowflake syntax
3. **Workflow continuity** — each phase references the correct next phase
4. **Fixture scenarios** — example runs produce expected output patterns

## Running Tests

```bash
bash tests/run_tests.sh
```

## Fixtures

| Fixture | Mode | Purpose |
|---------|------|---------|
| `tpch_discover.md` | Discover | Expected output for SNOWFLAKE_SAMPLE_DATA.TPCH_SF1 |
| `existing_sv_audit.md` | Audit | Expected findings for a pre-built SV with known gaps |

## Manual Validation

For prompt-only skills, the authoritative test is invoking the skill against a real account:

1. **Discover mode**: `$semantic-view-discovery` → "Discover semantic views for SNOWFLAKE_SAMPLE_DATA"
2. **Audit mode**: `$semantic-view-discovery` → "Audit <your_test_sv_fqn>"

Expected: skill completes all phases without error, produces actionable recommendations.
