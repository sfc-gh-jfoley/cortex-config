# Cortex AI Semantic Layer Bundle

## Three skills that take you from "I have tables" to "I have a working AI agent"

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  semantic-view-     │     │  semantic-view-      │     │  cortex-agent-       │
│  discovery          │ ──▶ │  ddl                 │ ──▶ │  ddl                 │
│                     │     │                      │     │                      │
│  "Which tables      │     │  "Build the          │     │  "Create an agent    │
│   should be in      │     │   semantic view"     │     │   that uses it"      │
│   my semantic       │     │                      │     │                      │
│   views?"           │     │                      │     │                      │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
       DISCOVER                    BUILD                      DEPLOY
```

---

## Skill 1: semantic-view-discovery

**TLDR:** Scans your database and tells you which tables to group into semantic views.

**When to use:**
- You have a database with dozens/hundreds of tables and don't know where to start
- You want data-driven recommendations (not guessing) based on actual FK relationships and query patterns
- You have an existing SV and want to know if it's missing tables or has unused columns

**Two modes:**

| Mode | Input | Output |
|------|-------|--------|
| **Discover** | A database name | Domain groupings: "Orders = these 4 tables, Supply Chain = these 3 tables" |
| **Audit** | An existing SV FQN | Improvement report: missing tables, unused columns, relationship gaps |

**How to invoke:**
```
$semantic-view-discovery
"Discover semantic views for ANALYTICS_DB"
```

**What happens:**
1. Scans FK/PK constraints (instant, highest trust)
2. Infers joins from column names (_ID, _KEY matching)
3. Analyzes QUERY_HISTORY for which tables are queried together
4. Clusters tables into domains with confidence scores
5. You approve the groupings
6. Outputs structured handoff ready for the next skill

**Hands off to:** `$semantic-view-ddl`

---

## Skill 2: semantic-view-ddl

**TLDR:** Takes a list of tables and builds a production-quality semantic view with AI-generated descriptions and 23 self-checks.

**When to use:**
- You know which tables go together (from discovery or your own knowledge)
- You want Cortex Analyst / Snowflake Intelligence to understand your data
- You need a pure-SQL DDL approach (workshop/HOL friendly, no YAML)
- You want to add verified queries, tune descriptions, or check drift on an existing SV

**How to invoke:**
```
$semantic-view-ddl
"Create a semantic view for ANALYTICS_DB.PUBLIC.ORDERS and ANALYTICS_DB.PUBLIC.CUSTOMERS"
```

**What happens:**
1. You provide tables + business context
2. AI profiles every column and generates descriptions/synonyms
3. Columns classified as FACT / DIMENSION / METRIC / TIME_DIMENSION
4. Relationships detected and validated (FK pattern + cardinality check)
5. DDL generated with 23-point self-check (catches orphans, fan traps, cardinality lies, dup synonyms)
6. Deployed to Snowflake, tested with sample questions
7. Enriched with verified queries, CSS linking, governance tags

**Output:** A deployed `CREATE OR REPLACE SEMANTIC VIEW` in your Snowflake account.

**Hands off to:** `$cortex-agent-ddl`

---

## Skill 3: cortex-agent-ddl

**TLDR:** Creates a Cortex Agent that uses your semantic view(s) to answer business questions in natural language.

**When to use:**
- You have one or more semantic views and want an AI agent to query them
- You want the agent deployed to Snowflake Intelligence (the chat UI)
- You need multi-agent routing (master agent dispatches to domain sub-agents)
- You want auto-generated tool descriptions from SV metadata

**How to invoke:**
```
$cortex-agent-ddl
"Create an agent for our analytics team"
```

**What happens:**
1. You name the agent and pick a schema
2. Skill auto-discovers your semantic views (SHOW SEMANTIC VIEWS)
3. For each SV, CORTEX.COMPLETE generates a rich tool description
4. Orchestration instructions drafted with best practices
5. 17-rule spec validation catches common errors
6. Agent deployed via CREATE AGENT DDL
7. Smoke tested via DATA_AGENT_RUN with a real question

**Output:** A deployed Cortex Agent accessible in Snowflake Intelligence.

---

## The Full Chain (5 minutes to read, 30 minutes to run)

```
Step 1:  $semantic-view-discovery
         "Discover semantic views for MY_DATABASE"
         → Approve 2-3 domain groupings
         
Step 2:  $semantic-view-ddl  (repeat per domain)
         Paste the discovery handoff as context
         → Approve DDL, deploy SV
         
Step 3:  $cortex-agent-ddl
         "Create an agent for MY_DATABASE"
         → Agent auto-discovers your new SVs
         → Deploy, test, done
```

### When to skip steps

| Scenario | Start at |
|----------|----------|
| "I have hundreds of tables, where do I start?" | Step 1 (discovery) |
| "I know my tables, just build the SV" | Step 2 (ddl) |
| "I already have a semantic view, make an agent" | Step 3 (agent) |
| "My SV exists but it's not great" | Step 1 Audit mode, then Step 2 to rebuild |

---

## Prerequisites

| Requirement | Needed for |
|-------------|-----------|
| Role with IMPORTED PRIVILEGES on SNOWFLAKE db | Discovery (ACCOUNT_USAGE access) |
| CREATE SEMANTIC VIEW on target schema | DDL skill |
| CREATE AGENT on target schema | Agent skill |
| SELECT on source tables | All three |
| A warehouse | All three |
| 30+ days of query history | Discovery (co-occurrence analysis) |

---

## Install

All three skills are standalone — install whichever you need:

```bash
# Copy all three
cp -r semantic-view-discovery ~/.snowflake/cortex/skills/
cp -r semantic-view-ddl ~/.snowflake/cortex/skills/
cp -r cortex-agent-toolkit ~/.snowflake/cortex/plugins/
```

Or install from GitHub:
```bash
cortex plugin install sfc-gh-jfoley/semantic-view-discovery
cortex plugin install sfc-gh-jfoley/semantic-view-ddl
cortex plugin install sfc-gh-jfoley/cortex-agent-toolkit
```

---

## Key Design Principles

1. **No Snowhouse** — everything runs on the customer's own account
2. **No Python scripts** — discovery and ddl are prompt-only skills; agent-ddl is prompt-only
3. **No customer data in skill files** — examples use TPCH or generic retail
4. **Mandatory approval gates** — nothing deploys without explicit user confirmation
5. **Self-checking** — 23 checks on SVs, 17 rules on agents, scaling guards on discovery
6. **Graceful degradation** — works without ACCOUNT_USAGE (less accurate but functional)

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Insufficient privileges" on ACCOUNT_USAGE | Grant IMPORTED PRIVILEGES on SNOWFLAKE database to your role |
| Discovery finds no relationships | Tables may lack _ID/_KEY naming conventions. Try broadening the time window or use manual grouping |
| SV DDL fails on execution | Check Phase 5 self-check output — usually a duplicate column name or missing PK |
| Agent can't answer cross-table questions | Verify RELATIONSHIPS are defined in the SV (DESCRIBE SEMANTIC VIEW to check) |
| Agent returns wrong numbers | Add AI_VERIFIED_QUERIES for the failing question pattern (DDL Phase 7) |
| Discovery is slow on large databases | Use schema-level scoping (the skill will prompt you at >200 tables) |
