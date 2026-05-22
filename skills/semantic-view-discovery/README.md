# semantic-view-discovery

Discover optimal semantic view domain groupings from a Snowflake account, or audit existing semantic views against actual query usage patterns.

## Install

```bash
cortex plugin install sfc-gh-jfoley/semantic-view-discovery
```

Or copy manually:

```bash
cp -r semantic-view-discovery ~/.snowflake/cortex/skills/
```

## Prerequisites

- Snowflake role with `IMPORTED PRIVILEGES` on the `SNOWFLAKE` database (for ACCOUNT_USAGE access)
- Or `ACCOUNTADMIN` role
- At least 30 days of query history for meaningful co-occurrence analysis
- Active connection configured in Cortex Code

## Usage

### Discover Mode

Scan a database to recommend semantic view groupings:

```
$semantic-view-discovery
"Help me discover semantic views for MY_DATABASE"
```

### Audit Mode

Audit an existing semantic view for improvements:

```
$semantic-view-discovery
"Audit MY_DB.MY_SCHEMA.MY_SEMANTIC_VIEW"
```

## What It Does

### Discover Mode

1. Scans `INFORMATION_SCHEMA` for declared FK/PK constraints
2. Infers relationships via column name matching (`_ID`, `_KEY` suffixes)
3. Analyzes `QUERY_HISTORY` for table co-occurrence patterns
4. Checks `ACCESS_HISTORY` for column-level usage frequency
5. Clusters tables into domain groupings with confidence scores
6. Presents recommendations for user approval
7. Outputs table lists formatted for `semantic-view-ddl` Phase 1

### Audit Mode

1. Describes the existing semantic view structure
2. Analyzes query patterns against the SV's tables
3. Checks column access frequency vs SV coverage
4. Identifies: missing tables, unused columns, missing columns, relationship gaps
5. Presents prioritized improvement recommendations

## Data Sources

All queries run on your own Snowflake account. No external access required.

| Source | Purpose |
|--------|---------|
| `INFORMATION_SCHEMA.TABLE_CONSTRAINTS` | Declared PK/FK relationships |
| `INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS` | FK references between tables |
| `INFORMATION_SCHEMA.COLUMNS` | Column names for FK inference |
| `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` | Table co-occurrence patterns |
| `SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY` | Column-level usage frequency |

## Handoff

Discover mode output is designed to paste directly into the `semantic-view-ddl` skill as Phase 1 context. Each recommended domain includes:

- Table list with FQNs
- Detected join keys
- Top queried columns
- Usage context (query count, user count, common patterns)

## Limitations

- `QUERY_HISTORY` has up to 45-minute latency
- `ACCESS_HISTORY` has up to 3-hour latency and may not be available on all editions
- Co-occurrence analysis is based on query text parsing (may miss dynamic SQL)
- Minimum 30 days of history recommended for meaningful results
