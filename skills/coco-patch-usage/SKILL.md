---
name: coco-patch-usage
description: "Generate paired CoCo (Cortex Code) usage reports for a named SE leader's patch — customer accounts on their own Snowflake accounts plus SE employees on internal Snowhouse inference — month-over-month. Use when: coco usage for <person>'s patch, accounts and SEs report for <leader>, month over month coco for <SE director>'s territory, how much coco are my accounts and SEs using, patch usage. Triggers: coco patch usage, drew's accounts and SEs, patch report, month over month coco, se director territory usage."
---

# CoCo Patch Usage

Produces two separate month-over-month CoCo usage reports for a named SE leader's
patch:

1. **Accounts report** — customer accounts in the patch, using the customers' own
   Snowflake accounts (credits, requests, active accounts, active user-days).
2. **SEs report** — SE employees in the leader's org, using internal Snowhouse
   inference (USD cost, tokens, prompts, blocks).

These are separate reports on purpose: customers consume CoCo on their own
Snowflake accounts (measured in token credits), while SEs consume on the internal
Snowhouse account (measured in USD cost). The units are not comparable, so never
present them in a single combined table.

## Step 0: Detect Connection

**Always do this before running any queries.**

1. Read `~/.snowflake/cortex/settings.json` and extract `cortexAgentConnectionName`.
   - CoCo usage analytics live in the **Snowhouse** account (`SFCOGSOPS-SNOWHOUSE`).
   - This is where `SNOWSCIENCE` (the data warehouse with CoCo fact tables + territory
     dims) is installed.

2. **If `cortexAgentConnectionName` = `snowhouse`** → confirm:
   > "CoCo usage analytics run on **snowhouse** (SFCOGSOPS-SNOWHOUSE). Run the queries there?"

   **⚠️ STOP**: Wait for Y/N.

3. **If not snowhouse** → ask the user which connection to use. The Snowhouse
   connection is required — if it's not configured, the tables below will not be
   accessible.

## Step 1: Resolve the Leader

The user will name a person (e.g., "Drew Holland"). Resolve that person in
`SNOWSCIENCE.SEMANTIC_VIEWS.DIM_ACCOUNT_OWNERS` across ALL role columns — the same
person can appear at different levels:

```sql
SELECT 'ACCOUNT_OWNER'   AS role_col, ACCOUNT_OWNER    AS person, COUNT(*) AS accounts
FROM SNOWSCIENCE.SEMANTIC_VIEWS.DIM_ACCOUNT_OWNERS WHERE ACCOUNT_OWNER    ILIKE '<name>'
UNION ALL
SELECT 'SALES_ENGINEER', SALES_ENGINEER, COUNT(*) FROM SNOWSCIENCE.SEMANTIC_VIEWS.DIM_ACCOUNT_OWNERS WHERE SALES_ENGINEER ILIKE '<name>'
UNION ALL
SELECT 'SE_MANAGER',     SE_MANAGER,     COUNT(*) FROM SNOWSCIENCE.SEMANTIC_VIEWS.DIM_ACCOUNT_OWNERS WHERE SE_MANAGER     ILIKE '<name>'
UNION ALL
SELECT 'SE_DIRECTOR',    SE_DIRECTOR,    COUNT(*) FROM SNOWSCIENCE.SEMANTIC_VIEWS.DIM_ACCOUNT_OWNERS WHERE SE_DIRECTOR    ILIKE '<name>'
UNION ALL
SELECT 'DM',            DM,             COUNT(*) FROM SNOWSCIENCE.SEMANTIC_VIEWS.DIM_ACCOUNT_OWNERS WHERE DM              ILIKE '<name>'
UNION ALL
SELECT 'RVP',           RVP,            COUNT(*) FROM SNOWSCIENCE.SEMANTIC_VIEWS.DIM_ACCOUNT_OWNERS WHERE RVP             ILIKE '<name>';
```

**Pick the role column** that returns a non-zero account count and represents the
leader's scope (usually `SE_DIRECTOR`, `RVP`, `DM`, or `SE_MANAGER`). Confirm the
resolved scope with the user:

> "Resolved <name> as <role_col> covering <N> accounts across <districts/patches>. Proceed?"

**⚠️ STOP**: Wait for Y/N. Store the `<role_col>` and `<name>` for Steps 3–4.

## Step 2: List the Team and Accounts

Before running usage, show the user the scope so they can sanity-check.

**SE team** (from `IT_DIM_EMPLOYEE` joined back to the leader's patch):

```sql
SELECT DISTINCT O.SALES_ENGINEER, E.BUSINESS_TITLE, E.PROFILE_NAME,
                E.SNOWHOUSE_USERNAME, O.DISTRICT_NAME, O.PATCH_NAME
FROM SNOWSCIENCE.SEMANTIC_VIEWS.DIM_ACCOUNT_OWNERS O
JOIN SNOWSCIENCE.ENGINEERING_SYSTEMS.IT_DIM_EMPLOYEE E
  ON O.SALES_ENGINEER = E.PREFERRED_NAME
WHERE O.<role_col> = '<name>'
  AND E.PROFILE_NAME IN ('Snowflake Sales Engineers','Snowflake Sales Engineering Manager')
ORDER BY O.DISTRICT_NAME, O.PATCH_NAME, O.SALES_ENGINEER;
```

**Accounts by patch**:

```sql
SELECT PATCH_NAME, DISTRICT_NAME, SALES_ENGINEER, SE_MANAGER, COUNT(*) AS accounts
FROM SNOWSCIENCE.SEMANTIC_VIEWS.DIM_ACCOUNT_OWNERS
WHERE <role_col> = '<name>'
GROUP BY PATCH_NAME, DISTRICT_NAME, SALES_ENGINEER, SE_MANAGER
ORDER BY PATCH_NAME, DISTRICT_NAME, SALES_ENGINEER;
```

Present both as tables. Confirm the SE team list with the user before proceeding —
this is the set whose Snowhouse usage will be measured in Step 4.

**⚠️ STOP**: Confirm team + account scope.

## Step 3: Accounts Report (Customer Accounts)

Customer accounts consume CoCo on their **own** Snowflake accounts. Source:
`SNOWSCIENCE.LLM.CORTEX_CODE_ACCOUNT_DAY_FACT`.

Replace `<role_col>`, `<name>`, `<months>` (default 3 = last 3 full calendar months).

```sql
SELECT
    DATE_TRUNC('month', F.DS)                          AS usage_month,
    COUNT(DISTINCT F.SALESFORCE_ACCOUNT_ID)            AS active_accounts,
    ROUND(SUM(F.TOTAL_TOKEN_CREDITS), 2)               AS total_credits,
    SUM(F.TOTAL_DAILY_REQUESTS)                        AS total_requests,
    SUM(F.TOTAL_ACTIVE_USERS)                          AS total_active_user_days
FROM SNOWSCIENCE.LLM.CORTEX_CODE_ACCOUNT_DAY_FACT F
JOIN SNOWSCIENCE.SEMANTIC_VIEWS.DIM_ACCOUNT_OWNERS O
  ON F.SALESFORCE_ACCOUNT_ID = O.SALESFORCE_ACCOUNT_ID
WHERE O.<role_col> = '<name>'
  AND F.DS >= DATE_TRUNC('month', DATEADD('month', -<months>, CURRENT_DATE()))
  AND F.DS <  DATE_TRUNC('month', CURRENT_DATE())
GROUP BY usage_month
ORDER BY usage_month;
```

**Optional**: add a per-account breakdown for the latest month by joining
`DIM_ACCOUNT_OWNERS` for the account name and patch.

## Step 4: SEs Report (Internal Snowhouse Inference)

SEs consume CoCo on the **internal Snowhouse** account. Source:
`SNOWSCIENCE.ENGINEERING_SYSTEMS.CORTEX_CODE_USAGE_DAILY` joined to
`IT_DIM_EMPLOYEE` on `EMPLOYEE_ID`.

Scope the SEs to the leader's org. The cleanest filter is the team list from Step 2
(PREFERRED_NAME of the SEs + the leader themselves). For a broader cut, filter
`IT_DIM_EMPLOYEE.PROFILE_NAME` to SE profiles and scope by the leader's org columns
(`MANAGER`, `SE_MANAGER`, etc.).

```sql
SELECT
    DATE_TRUNC('month', U."DATE")                       AS usage_month,
    COUNT(DISTINCT U.EMPLOYEE_ID)                        AS active_ses,
    ROUND(SUM(U.TOTAL_COST_USD), 2)                      AS total_cost_usd,
    SUM(U.TOTAL_TOKENS)                                  AS total_tokens,
    SUM(U.PROMPTS)                                       AS total_prompts,
    SUM(U.BLOCKS)                                        AS total_blocks
FROM SNOWSCIENCE.ENGINEERING_SYSTEMS.CORTEX_CODE_USAGE_DAILY U
JOIN SNOWSCIENCE.ENGINEERING_SYSTEMS.IT_DIM_EMPLOYEE E
  ON U.EMPLOYEE_ID = E.EMPLOYEE_ID
WHERE E.PROFILE_NAME IN ('Snowflake Sales Engineers','Snowflake Sales Engineering Manager')
  AND E.PREFERRED_NAME IN ( '<se1>', '<se2>', ... , '<leader_name>' )
  AND U."DATE" >= DATE_TRUNC('month', DATEADD('month', -<months>, CURRENT_DATE()))
  AND U."DATE" <  DATE_TRUNC('month', CURRENT_DATE())
GROUP BY usage_month
ORDER BY usage_month;
```

**Optional**: add a per-SE breakdown (GROUP BY E.PREFERRED_NAME, usage_month) so the
leader can see who on the team is driving usage.

## Step 5: Present the Reports

Present **two separate tables** — never one combined table. Always include:

- Month column (full month label, e.g., "Jun 2026")
- The metric columns from each query
- A **MoM delta line** under each table (credits/cost % change month to month,
  direction, and a one-sentence read)

Accounts report (credits = customer billing units):
| Month | Active Accounts | Credits | Requests | Active User-Days |
|---|---:|---:|---:|---:|

SEs report (USD = internal Snowhouse cost):
| Month | Active SEs | Cost (USD) | Total Tokens | Prompts | Blocks |
|---|---:|---:|---:|---:|---:|

Add a short narrative comparing the shape of the two trends (e.g., "Accounts
credits grew steadily; SE cost spiked in Jul then fell back").

**Notes to include in output:**
- Active accounts/SEs = those with ≥1 CoCo event that month (of the total in the patch).
- Accounts measured in token credits; SEs in USD — not comparable across the two tables.
- Up to ~45 min latency on usage views; the latest month is near-final.

## Schema Reference (Snowhouse / SNOWSCIENCE)

| Table | Role | Key columns |
|---|---|---|
| `SEMANTIC_VIEWS.DIM_ACCOUNT_OWNERS` | Account → territory map | `SALESFORCE_ACCOUNT_ID`, `SALESFORCE_NAME`, `ACCOUNT_OWNER`, `SALES_ENGINEER`, `SE_MANAGER`, `SE_DIRECTOR`, `DM`, `RVP`, `PATCH_NAME`, `DISTRICT_NAME`, `REGION_NAME` |
| `ENGINEERING_SYSTEMS.IT_DIM_EMPLOYEE` | Employee → title/profile | `EMPLOYEE_ID`, `PREFERRED_NAME`, `EMAIL`, `BUSINESS_TITLE`, `PROFILE_NAME`, `SNOWHOUSE_USERNAME` |
| `LLM.CORTEX_CODE_ACCOUNT_DAY_FACT` | Customer account CoCo usage | `DS`, `DEPLOYMENT`, `ACCOUNT_ID`, `SALESFORCE_ACCOUNT_ID`, `SALESFORCE_ACCOUNT_NAME`, `TOTAL_TOKEN_CREDITS`, `TOTAL_ACTIVE_USERS`, `TOTAL_DAILY_REQUESTS` |
| `ENGINEERING_SYSTEMS.CORTEX_CODE_USAGE_DAILY` | Internal SE CoCo usage | `EMPLOYEE_ID`, `USER_NAME`, `DATE`, `TOTAL_TOKENS`, `TOTAL_COST_USD`, `PROMPTS`, `BLOCKS` |

SE profile filter: `PROFILE_NAME IN ('Snowflake Sales Engineers','Snowflake Sales Engineering Manager')`.

## Stopping Points

- ✋ Step 0: Connection confirmed (snowhouse)
- ✋ Step 1: Leader + role column resolved and confirmed
- ✋ Step 2: Team + account scope confirmed
- ✋ Step 5: Both reports presented

## Output

Two separate month-over-month CoCo usage tables (accounts + SEs) for the resolved
leader's patch, each with a MoM delta read and a one-line narrative comparing the
trends. No combined table — the two streams use different units.
