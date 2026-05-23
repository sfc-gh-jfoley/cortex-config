# Module 00 — Setup

**Duration:** ~5 minutes
**Goal:** Verify prerequisites and load the lab data into your account.

---

## Pre-Work

Complete the following steps **before the lab session begins**:

### 1. Network Access
> **VPN Note:** Disable your VPN before connecting to Snowflake. Many corporate VPNs block Snowflake's endpoints and will cause connection failures during the lab.

### 2. Snowflake Access
- [ ] Confirm you can log in to the Snowflake account provided by your facilitator
- [ ] Verify your role assignment: run `SELECT CURRENT_ROLE();` — you should see `<LAB_ROLE>`

### 3. Tool Setup
<!-- Choose the applicable option based on your lab format -->

**Option A — Snowsight (browser, no install required):**
- [ ] Log in to Snowsight at `https://<ACCOUNT>.snowflakecomputing.com`
- [ ] Navigate to Worksheets and create a new worksheet

**Option B — SnowSQL CLI:**
- [ ] Download SnowSQL: https://docs.snowflake.com/en/user-guide/snowsql-install-config
- [ ] Configure your connection: `snowsql -a <ACCOUNT> -u <USERNAME>`
- [ ] Test: `snowsql -q "SELECT CURRENT_USER()"`

### 4. Verify Setup
Run the following to confirm everything is ready:
```sql
SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_DATABASE();
```
All four values should be populated (non-null).

---

## Step 1 — Confirm Your Environment

Open Snowsight. Confirm:
- Role: `<ROLE_NAME>` (or higher)
- Warehouse: `COMPUTE_WH` (or equivalent XS+)
- Database: will be created in the next step

---

## Step 2 — Run Setup SQL

Open a new SQL worksheet. Open `../sql/setup.sql`, paste the full contents, and run it.

The script creates the `<LAB_DB>.<LAB_SCHEMA>` schema and loads the following tables:

| Table | Rows | Description |
|-------|------|-------------|
| `TABLE_A` | N | Description |
| `TABLE_B` | N | Description |

The script ends with a verification query. Confirm these counts before continuing:

```
table_a = N  ·  table_b = N
```

If counts do not match, re-run `setup.sql` — it is idempotent (`CREATE OR REPLACE`).

---

## Step 3 — (CoCo Path) Open a Session

If you are using the **CoCo-guided path**, open a terminal and launch Cortex Code CLI:

```bash
cortex code
```

Confirm you are connected to the correct account with `cortex connections list`.

---

## Module Checkpoint

You should have:
- [ ] `<LAB_DB>.<LAB_SCHEMA>` created with N tables
- [ ] All row counts verified
- [ ] CoCo session open (if using Path A)

Proceed to [Module 01](01_topic_one.md).
