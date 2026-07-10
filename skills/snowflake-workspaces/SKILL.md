---
name: snowflake-workspaces
description: >
  Work with Snowflake Workspaces (GA Jun 18, 2026). Write Python files in the Workspaces UI,
  schedule them via NPO (Native Python Objects) + Tasks, understand when to use Workspaces
  vs. Notebooks, and optimize execution for data exploration and scheduling.
---

# Snowflake Workspaces Skill

Write and schedule Python code in Snowflake Workspaces. Understand when to use Workspaces vs. Notebooks and how to orchestrate Python jobs with Tasks.

## Overview

Snowflake Workspaces (GA Jun 18, 2026) enable you to:
- **Write Python files directly in the Workspaces UI** — no external IDE required
- **Use Native Python Objects (NPO)** — call Python functions as first-class SQL objects
- **Schedule Python via Tasks** — orchestrate Python jobs alongside SQL pipelines
- **Integrate with Snowpark** — use Snowpark DataFrames and libraries
- **Persist functions** — reuse Python functions across queries and workflows

This skill guides you through:
1. **Phase 0**: Prerequisites and setup
2. **Phase 1**: Understand Workspaces vs. Notebooks vs. Notebooks in Notebooks
3. **Phase 2**: Write and run Python in Workspaces
4. **Phase 3**: Create Native Python Objects (NPO)
5. **Phase 4**: Schedule Python with Tasks
6. **Phase 5**: Troubleshoot and optimize

---

## Phase 0: Prerequisites and Setup

Before using Workspaces, verify:

- ✅ Snowflake account on any edition (feature is GA)
- ✅ Current role has `USE WAREHOUSE` and `CREATE PYTHON FUNCTION` privilege
- ✅ A Snowflake warehouse is running (or will be auto-resumed)
- ✅ You have access to a workspace (ask your admin if needed)

**Check your setup:**

```sql
-- 1. Verify current role
SELECT CURRENT_ROLE();

-- 2. Verify warehouse exists
SHOW WAREHOUSES;

-- 3. Check if you have PYTHON FUNCTION creation privilege
SHOW GRANTS ON DATABASE <DB>;
-- Look for CREATE PYTHON FUNCTION in the results

-- 4. Verify Python is enabled in your region/edition
SHOW PARAMETERS LIKE 'ENABLE_PYTHON' IN ACCOUNT;
```

If you lack `CREATE PYTHON FUNCTION` privilege, ask your account admin to grant it:
```sql
GRANT CREATE PYTHON FUNCTION ON DATABASE <DB> TO ROLE <YOUR_ROLE>;
```

---

## Phase 1: Understand the Landscape

### Workspaces vs. Notebooks vs. Notebooks in Notebooks

| Aspect | **Workspaces** | **Notebooks (Old)** | **Notebooks in Notebooks** |
|--------|---|---|---|
| **Interface** | Native Snowflake UI (code editor + terminal) | Legacy Snowsight notebook | Notebook cells in Workspace |
| **Language** | Python (GA Jun 2026), SQL, Markdown | Python, SQL, Markdown | Python, SQL, Markdown |
| **Persistence** | Files saved to Workspace (version controlled) | Cells stored in database | Cells stored in Workspace |
| **Best for** | Production code, CI/CD integration, complex logic | Exploratory analysis, quick prototyping | Iterative data exploration |
| **Scheduling** | Tasks + Native Python Objects | Limited task support | Via Workspace files + Tasks |
| **IDE Features** | Terminal, file tree, search, debug | Web UI only | Web UI + cell-based |
| **Reusability** | Functions become NPOs → callable from SQL | Manual copy-paste | Via Python imports |

### When to Use Each

- **Workspace Python**: You're writing production code, scheduling jobs, or need version control
- **Legacy Notebook**: Quick analysis, no need for persistence or reuse
- **Notebook in Workspace**: Exploring data iteratively before committing to Workspace files

---

## Phase 2: Write Python in Workspaces UI

### Access Your Workspace

1. Open Snowsight
2. Navigate to **Workspaces** tab (left sidebar)
3. Click **Create Workspace** or open an existing workspace
4. Inside the workspace, click **+ New File** → select **Python**

### Write Your First Python Script

```python
# file: my_analysis.py
from snowflake.snowpark import Session
import pandas as pd

# Get Snowpark session (automatically bound in Workspaces)
session = Session.builder.config("connection", "default").create()

# Query a table
df = session.table("my_db.my_schema.my_table")

# Perform analysis
summary = df.select("*").limit(10).to_pandas()
print(summary)

# Save results
summary.to_csv("results.csv")
session.close()
```

### Run the Script

1. In the Workspace UI, click **Run** or press `Shift+Enter`
2. Output appears in the **Terminal** panel below
3. Files are automatically saved to your workspace

---

## Phase 3: Create Native Python Objects (NPO)

Native Python Objects (NPO) are Python functions registered as first-class SQL objects. Once created, you can call them from SQL queries.

### Create a Simple NPO

```sql
-- Define a Python function as an NPO
CREATE PYTHON FUNCTION <DB>.<SCHEMA>.analyze_text(text STRING)
  RETURNS STRING
  LANGUAGE PYTHON
  RUNTIME_VERSION = '3.11'
  PACKAGES = ('nltk', 'pandas')
  HANDLER = 'analyze_impl'
AS $$
import nltk
from nltk.sentiment import SentimentIntensityAnalyzer

def analyze_impl(text):
    sia = SentimentIntensityAnalyzer()
    scores = sia.polarity_scores(text)
    return f"Sentiment: {scores['compound']:.2f}"
$$;
```

### Use the NPO in SQL

```sql
-- Call the Python function from SQL
SELECT
  text_column,
  <DB>.<SCHEMA>.analyze_text(text_column) AS sentiment
FROM <DB>.<SCHEMA>.text_data
LIMIT 10;
```

### Write and Test NPO in Workspace

**File: `sentiment_analyzer.py`**
```python
from snowflake.snowpark import Session
from nltk.sentiment import SentimentIntensityAnalyzer

def analyze_impl(text):
    sia = SentimentIntensityAnalyzer()
    scores = sia.polarity_scores(text)
    return f"Sentiment: {scores['compound']:.2f}"

# Test locally
if __name__ == "__main__":
    test_text = "This product is amazing!"
    result = analyze_impl(test_text)
    print(result)
```

**Register as NPO:**
```sql
CREATE PYTHON FUNCTION my_db.my_schema.analyze_text(text STRING)
  RETURNS STRING
  LANGUAGE PYTHON
  RUNTIME_VERSION = '3.11'
  PACKAGES = ('nltk', 'pandas')
  HANDLER = 'sentiment_analyzer.analyze_impl'
AS (
  -- Reference your Workspace file or paste the function body
  SELECT '<function_code_here>'
);
```

---

## Phase 4: Schedule Python with Tasks

### Create a Task to Run Python

```sql
-- Create a task that executes a Python function
CREATE TASK <DB>.<SCHEMA>.daily_sentiment_analysis
  WAREHOUSE = <WAREHOUSE_NAME>
  SCHEDULE = 'USING CRON 0 2 * * * UTC'  -- Daily at 2 AM UTC
AS
BEGIN
  INSERT INTO <DB>.<SCHEMA>.sentiment_results
  SELECT
    text_column,
    <DB>.<SCHEMA>.analyze_text(text_column) AS sentiment,
    CURRENT_TIMESTAMP() AS analyzed_at
  FROM <DB>.<SCHEMA>.text_data
  WHERE analyzed_at IS NULL;
END;
```

### Resume and Monitor the Task

```sql
-- Resume the task to enable scheduling
ALTER TASK <DB>.<SCHEMA>.daily_sentiment_analysis RESUME;

-- View task execution history
SELECT
  SCHEDULED_TIME,
  QUERY_START_TIME,
  STATE,
  ERROR_CODE,
  ERROR_MESSAGE
FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(TASK_NAME => 'daily_sentiment_analysis'))
ORDER BY SCHEDULED_TIME DESC
LIMIT 20;
```

### Organize Python Jobs with Workspaces + Tasks

**Workflow:**
1. Write Python functions in Workspace files (`my_functions.py`)
2. Create NPOs from those functions via SQL
3. Schedule NPO calls via Tasks
4. Monitor task execution from SQL

**Example structure:**
```
my_workspace/
  ├── sentiment_analyzer.py      # Core Python logic
  ├── data_loader.py             # Load data functions
  ├── utils.py                   # Shared utilities
  └── orchestrate.sql            # Task definitions + NPO calls
```

---

## Phase 5: Troubleshoot and Optimize

### Troubleshoot: Python Script Fails in Workspace

**Symptom:** Script runs in IDE but fails in Workspace

**Root causes:**
1. **Missing packages:** Workspace doesn't have required library
2. **Connection issue:** Snowpark session can't connect
3. **File path error:** Trying to read a file that doesn't exist in Workspace

**Fix:**
```python
# Verify session and packages
from snowflake.snowpark import Session

session = Session.builder.config("connection", "default").create()
print(f"Connected to: {session.sql('SELECT CURRENT_DATABASE()').collect()}")

# Check installed packages
import sys
print(sys.path)
```

### Troubleshoot: NPO Not Callable from SQL

**Symptom:** `Function <db>.<schema>.<func> does not exist`

**Root causes:**
1. **Function not created:** CREATE PYTHON FUNCTION didn't execute
2. **Schema mismatch:** Function created in wrong schema
3. **Runtime version mismatch:** Handler expects different Python version

**Fix:**
```sql
-- List all functions in schema
SHOW FUNCTIONS IN SCHEMA <DB>.<SCHEMA>;

-- Describe the function to verify
DESC FUNCTION <DB>.<SCHEMA>.<FUNC_NAME>(STRING);

-- Recreate with correct schema and runtime
DROP FUNCTION IF EXISTS <DB>.<SCHEMA>.<FUNC_NAME>(STRING);

CREATE PYTHON FUNCTION <DB>.<SCHEMA>.<FUNC_NAME>(text STRING)
  RETURNS STRING
  LANGUAGE PYTHON
  RUNTIME_VERSION = '3.11'
  HANDLER = 'my_module.my_function'
AS 'function_body_here';
```

### Optimize: Speed Up Python Execution

**Batch operations instead of row-by-row:**
```sql
-- BAD: Calls function for each row (slow)
SELECT col1, <DB>.<SCHEMA>.my_func(col2) FROM large_table;

-- GOOD: Use VECTORIZED UDF for parallel execution
CREATE FUNCTION <DB>.<SCHEMA>.my_func_vectorized(col2 ARRAY)
  RETURNS ARRAY
  LANGUAGE PYTHON
  VECTORIZED_INPUT = TRUE
AS $$
  import numpy as np
  return np.apply_along_axis(lambda x: my_logic(x), 0, col2)
$$;
```

**Use appropriate runtime and packages:**
```sql
-- Specify minimal packages to reduce cold-start time
CREATE PYTHON FUNCTION <DB>.<SCHEMA>.light_func()
  RETURNS STRING
  LANGUAGE PYTHON
  RUNTIME_VERSION = '3.11'
  PACKAGES = ()  -- No external packages → faster startup
AS 'return "hello"';
```

---

## Common Patterns

### Pattern 1: Data Exploration Workspace

```python
# file: exploration.py
from snowflake.snowpark import Session
import pandas as pd

session = Session.builder.config("connection", "default").create()

# Load data
df = session.table("my_db.my_schema.transactions")

# Explore
print("Shape:", df.count(), "rows")
print("\nSample:")
print(df.limit(5).to_pandas())

# Save findings
findings = df.select("*").where(col("amount") > 1000).count()
print(f"\nHigh-value transactions: {findings}")

session.close()
```

### Pattern 2: Scheduled Data Pipeline

```sql
-- 1. Create Python function in Workspace
CREATE PYTHON FUNCTION prod_db.analytics.clean_customer_data(customer_id INT)
  RETURNS TABLE(customer_id INT, clean_email STRING, verified BOOLEAN)
  LANGUAGE PYTHON
  RUNTIME_VERSION = '3.11'
AS 'function_body';

-- 2. Create task to schedule it
CREATE TASK prod_db.analytics.daily_customer_clean
  WAREHOUSE = compute_wh
  SCHEDULE = 'USING CRON 0 1 * * * UTC'
AS
INSERT INTO prod_db.analytics.cleaned_customers
SELECT * FROM TABLE(prod_db.analytics.clean_customer_data(customer_id))
FROM prod_db.raw.customers;

-- 3. Resume and monitor
ALTER TASK daily_customer_clean RESUME;
```

### Pattern 3: Interactive Development with Notebooks

1. Open **Notebook in Workspace** for exploration
2. Iterate on Python code in notebook cells
3. When stable, promote code to a Workspace `.py` file
4. Register as NPO
5. Schedule with Task

---

## Next Steps

- **Need to share Python functions with teammates?** Export as NPO and grant USAGE privilege
- **Need to version control your Workspace files?** Integrate with Git (see Workspace settings)
- **Need more examples?** See [Snowflake Workspaces documentation](https://docs.snowflake.com/workspaces)
- **Ready to schedule production jobs?** Create Tasks that invoke your NPOs
