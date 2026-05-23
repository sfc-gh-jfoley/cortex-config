# Module 01 — <Topic One>

**Duration:** ~N minutes
**Path:** CoCo (A) · Snowsight manual (B)

---

## Overview

<1-2 sentence explanation of why this module exists and what capability it builds>

---

## Exercise 1.1 — <First Exercise>

> **Goal:** <specific, measurable outcome>

**Path A (CoCo CLI):** Open a CoCo session, make sure your connection points to the lab database, and paste:

```
I'm working in Snowflake database <LAB_DB>, schema <LAB_SCHEMA>, warehouse COMPUTE_WH.
I have these tables:
- TABLE_A — <description>
- TABLE_B — <description>

<Specific bounded ask>
```

> **What to watch for:** <key observation — what CoCo should infer or demonstrate>

**Path B (Snowsight):** Open a new SQL worksheet and run:

```sql
-- <comment explaining what this does>
SELECT ...
FROM <LAB_DB>.<LAB_SCHEMA>.TABLE_A;
```

**Verify:**
```sql
SELECT COUNT(*) FROM <LAB_DB>.<LAB_SCHEMA>.<result_object>;
-- Expected: > 0 rows
```

---

## Exercise 1.2 — <Second Exercise>

> **Goal:** <specific outcome>

**Path A (CoCo CLI):**

```
Now <next step>. Keep everything in <LAB_DB>.<LAB_SCHEMA>.
```

**Path B (Snowsight):**

```sql
<SQL here>
```

> **Failure moment:** <describe what goes wrong here — this is intentional>  
> In the next exercise we will fix this by <foreshadow the solution>.

---

## Module Checkpoint

Before continuing:
- [ ] <condition 1 verified>
- [ ] <condition 2 verified>

If stuck, see [hints](../hints/01_hints.md). Proceed to [Module 02](02_topic_two.md).
