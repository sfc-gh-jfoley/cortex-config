This plugin provides the **semantic-view-discovery** skill for discovering optimal semantic view groupings from a Snowflake account.

- **semantic-view-discovery** — Scan ACCOUNT_USAGE + INFORMATION_SCHEMA to recommend SV domain groupings (Discover mode) or audit existing SVs for improvements (Audit mode)

To enable: `cortex plugin enable semantic-view-discovery`

Start with: `$semantic-view-discovery` and describe the database you want to analyze or the SV you want to audit.

Triggers: semantic view discovery, discover semantic views, which tables should be in my semantic view, recommend SV groupings, audit semantic view, SV audit, semantic view coverage, find tables for semantic view, SV domain clusters, what tables are queried together.
