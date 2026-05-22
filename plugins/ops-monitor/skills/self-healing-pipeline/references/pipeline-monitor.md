---
name: self-healing-pipeline-monitor
description: Set up alerting, human-in-the-loop review, and Streamlit dashboard for a self-healing pipeline agent.
---

# Monitor Pipeline

Wire up alerting channels, human-in-the-loop (HITL) review queue, and an optional Streamlit dashboard. Can be used standalone on an existing agent or as part of a Build compound.

## Workflow

### Step 1: Gather Monitoring Preferences

**Ask** user:

1. **Alerting channels** (select all that apply):
   - Email via SYSTEM$SEND_EMAIL
   - Webhook/Slack via notification integration
   - Snowflake ALERT objects (for self-monitor, lag drift, cost anomalies)
2. **Notification recipients** (email addresses and/or webhook URLs)
3. **HITL preferences**:
   - Auto-escalation timeout (default: 24 hours)
   - Deploy Streamlit review dashboard? (default: Yes)
4. **Monitoring thresholds**:
   - Max LLM calls per hour before cost alert (default: 50)
   - Circuit breaker threshold: escalations per hour before agent self-suspends (default: 10)

**STOP**: Confirm preferences.

### Step 2: Set Up Alerting

**Load** `references/monitoring-templates.md` for ALERT object SQL.

Based on user's channel selection:

#### Email

```sql
-- Create email notification integration (ACCOUNTADMIN)
CREATE OR REPLACE NOTIFICATION INTEGRATION {DB}_{SCHEMA}_EMAIL_INT
  TYPE = EMAIL
  ENABLED = TRUE
  ALLOWED_RECIPIENTS = ('{ALERT_EMAIL}');

-- Procedure to send alert emails
CREATE OR REPLACE PROCEDURE {DB}.{SCHEMA}.SP_SEND_ALERT(
    P_SUBJECT VARCHAR,
    P_BODY VARCHAR
)
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
BEGIN
    CALL SYSTEM$SEND_EMAIL(
        '{DB}_{SCHEMA}_EMAIL_INT',
        '{ALERT_EMAIL}',
        :P_SUBJECT,
        :P_BODY,
        'text/html'
    );
    RETURN 'Email sent';
END;
$$;
```

#### Webhook/Slack

```sql
-- Create webhook notification integration (ACCOUNTADMIN)
CREATE OR REPLACE NOTIFICATION INTEGRATION {DB}_{SCHEMA}_WEBHOOK_INT
  TYPE = WEBHOOK
  ENABLED = TRUE
  WEBHOOK_URL = '{WEBHOOK_URL}'
  WEBHOOK_BODY_TEMPLATE = '{"text": "SNOWFLAKE_WEBHOOK_MESSAGE"}'
  WEBHOOK_HEADERS = ('Content-Type'='application/json');

-- Procedure to send webhook alerts
CREATE OR REPLACE PROCEDURE {DB}.{SCHEMA}.SP_SEND_WEBHOOK_ALERT(
    P_MESSAGE VARCHAR
)
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
BEGIN
    CALL SYSTEM$SEND_SNOWFLAKE_NOTIFICATION(
        SNOWFLAKE.NOTIFICATION.TEXT_PLAIN(:P_MESSAGE),
        '{"' || '{DB}_{SCHEMA}_WEBHOOK_INT' || '": {}}'
    );
    RETURN 'Webhook sent';
END;
$$;
```

#### Snowflake ALERT Objects

Create these ALERT objects:

1. **ALERT_AGENT_HEALTH** — monitors the agent task itself (every 10 min)
2. **ALERT_ESCALATIONS** — notifies on new ESCALATED/PENDING_REVIEW items (every 5 min)
3. **ALERT_DT_LAG_DRIFT** — detects DTs exceeding 2x target lag (every 15 min)
4. **ALERT_COST_ANOMALY** — alerts when LLM calls exceed threshold per hour (every 30 min)

**Load** `references/monitoring-templates.md` for full ALERT SQL.

Resume all ALERTs:
```sql
ALTER ALERT {DB}.{SCHEMA}.ALERT_AGENT_HEALTH RESUME;
ALTER ALERT {DB}.{SCHEMA}.ALERT_ESCALATIONS RESUME;
ALTER ALERT {DB}.{SCHEMA}.ALERT_DT_LAG_DRIFT RESUME;
ALTER ALERT {DB}.{SCHEMA}.ALERT_COST_ANOMALY RESUME;
```

#### Wire Alerting into Procedures

Insert alert calls into existing procedures at these points:
- SP_DETECT_FAILURES → alert on circuit breaker trip
- SP_DIAGNOSE_FAILURE/SP_DIAGNOSE_DT_FAILURE → alert on ESCALATED
- SP_CHECK_GUARDRAILS → alert on PENDING_REVIEW (via SP_CREATE_REVIEW)
- SP_VERIFY_TASK_DAG/SP_VERIFY_DT_FIX → optional success alert

**Alert message templates:**

On ESCALATED:
```sql
CALL {DB}.{SCHEMA}.SP_SEND_ALERT(
    'Pipeline Escalation: ' || rec.OBJECT_NAME,
    '<b>Object:</b> ' || rec.OBJECT_TYPE || ' ' || rec.OBJECT_NAME
    || '<br><b>Error:</b> ' || rec.ERROR_MESSAGE
    || '<br><b>Fix Attempts:</b> ' || rec.FIX_ATTEMPTS
    || '<br><b>Reason:</b> Agent could not resolve this automatically.'
    || '<br><br>Review in the Self-Healing Dashboard or query PIPELINE_FAILURES.'
);
```

On PENDING_REVIEW:
```sql
CALL {DB}.{SCHEMA}.SP_SEND_ALERT(
    'Pipeline Review Required: ' || rec.OBJECT_NAME,
    '<b>Object:</b> ' || rec.OBJECT_TYPE || ' ' || rec.OBJECT_NAME
    || '<br><b>Error:</b> ' || rec.ERROR_MESSAGE
    || '<br><b>Proposed Fix:</b><pre>' || generated_sql || '</pre>'
    || '<br><b>Confidence:</b> ' || confidence
    || '<br><b>Guardrail Result:</b> ' || guardrail_result
    || '<br><br>Approve or reject in the Self-Healing Dashboard or call SP_APPROVE_FIX / SP_REJECT_FIX.'
);
```

**STOP**: Confirm alerting channels are working (send a test alert).

### Step 3: Set Up Human-in-the-Loop

Create HITL procedures:

1. **SP_CREATE_REVIEW** — called when guardrails return REVIEW. Generates context-aware remediation steps.
2. **SP_APPROVE_FIX** — human approves, executes fix, verifies DAG
3. **SP_REJECT_FIX** — human rejects with reason, escalates
4. **SP_MARK_RESOLVED** — human fixes manually, captures SQL for runbook learning
5. **SP_AUTO_ESCALATE_EXPIRED** — auto-escalates PENDING items after timeout
6. **SP_LEARN_FROM_MANUAL_FIXES** — analyzes manual fixes, creates new runbook entries

**Load** `references/sql-templates.md` for SP_CREATE_REVIEW, SP_APPROVE_FIX, SP_REJECT_FIX, SP_MARK_RESOLVED, SP_LEARN_FROM_MANUAL_FIXES full SQL. These are also available in the HITL section of monitoring-templates.md.

Create auto-escalation task:
```sql
CREATE OR REPLACE TASK {DB}.{SCHEMA}.AUTO_ESCALATE_REVIEWS
  WAREHOUSE = {WAREHOUSE}
  SCHEDULE = '60 MINUTE'
AS
  CALL {DB}.{SCHEMA}.SP_AUTO_ESCALATE_EXPIRED();

ALTER TASK {DB}.{SCHEMA}.AUTO_ESCALATE_REVIEWS RESUME;
```

### Step 4: Deploy Streamlit Dashboard (Optional)

If user wants the Streamlit review dashboard:

**3-page app**: Dashboard, Pending Reviews, Audit Log

**Page 1: Dashboard** — KPIs (total failures, auto-resolved, escalated, pending), success rate trend, failures by object type, recent auto-fixes.

**Page 2: Pending Reviews** — expandable cards for each pending review with Approve/Reject/Manual Fix buttons.

**Page 3: Audit Log** — filterable log of all agent actions with LLM usage cost tracking.

Deployment:
```sql
CREATE STAGE IF NOT EXISTS {DB}.{SCHEMA}.STREAMLIT_STAGE;

-- Write Python files to stage (skill creates the files)

CREATE OR REPLACE STREAMLIT {DB}.{SCHEMA}.SELF_HEALING_DASHBOARD
  ROOT_LOCATION = '@{DB}.{SCHEMA}.STREAMLIT_STAGE/streamlit/'
  MAIN_FILE = 'app.py'
  QUERY_WAREHOUSE = '{WAREHOUSE}';
```

For full Streamlit app code, the skill should generate:
- `app.py` — Dashboard page (metrics, charts, recent auto-fixes)
- `pages/pending_reviews.py` — Review queue with approve/reject/manual fix
- `pages/audit_log.py` — Filterable audit log with LLM cost tracking

Share the dashboard URL with the user.

## Stopping Points

- Step 1: Preferences confirmed
- Step 2: Alerting confirmed working
- Step 4: Dashboard deployed
