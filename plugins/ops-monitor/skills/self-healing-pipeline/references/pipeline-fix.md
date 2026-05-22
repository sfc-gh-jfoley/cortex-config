---
name: self-healing-pipeline-fix
description: Diagnose and repair failing self-healing pipeline agents or the pipelines they monitor.
---

# Fix Pipeline

Diagnose and repair issues with a self-healing pipeline agent or the pipelines it monitors. Covers both "the agent isn't working" and "the pipeline is failing and the agent can't fix it."

## Workflow

### Step 1: Identify the Problem

**Ask** user:
1. What is happening? (agent not detecting failures, wrong fixes, not executing, DT cascade issues, etc.)
2. Target database.schema where agent is deployed
3. Is the problem with tasks, dynamic tables, or the agent itself?

### Step 2: Health Check

**Execute** diagnostics in order:

**Agent status:**
```sql
SHOW TASKS LIKE 'SELF_HEALING%' IN {DB}.{SCHEMA};
```

**Recent failures by type:**
```sql
SELECT OBJECT_TYPE, STATUS, COUNT(*) FROM {DB}.{SCHEMA}.PIPELINE_FAILURES
WHERE DETECTED_AT > DATEADD('day', -7, CURRENT_TIMESTAMP())
GROUP BY 1, 2 ORDER BY 1;
```

**Recent audit trail:**
```sql
SELECT * FROM {DB}.{SCHEMA}.HEALING_AUDIT_LOG ORDER BY CREATED_AT DESC LIMIT 20;
```

**Guardrail blocks:**
```sql
SELECT * FROM {DB}.{SCHEMA}.HEALING_AUDIT_LOG
WHERE GUARDRAIL_RESULT LIKE 'BLOCK%' ORDER BY CREATED_AT DESC LIMIT 10;
```

**Task DAG verification results:**
```sql
SELECT * FROM {DB}.{SCHEMA}.HEALING_AUDIT_LOG
WHERE ACTION_TYPE IN ('VERIFY_TASK', 'VERIFY_DOWNSTREAM_TASK')
ORDER BY CREATED_AT DESC LIMIT 10;
```

**DT failures and graph health:**
```sql
SELECT * FROM {DB}.{SCHEMA}.PIPELINE_FAILURES
WHERE OBJECT_TYPE = 'DYNAMIC_TABLE' ORDER BY DETECTED_AT DESC LIMIT 10;

SELECT * FROM {DB}.{SCHEMA}.HEALING_AUDIT_LOG
WHERE ACTION_TYPE IN ('VERIFY_DT', 'VERIFY_DOWNSTREAM_DT')
ORDER BY CREATED_AT DESC LIMIT 10;

SELECT NAME, SCHEDULING_STATE FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_GRAPH_HISTORY());
```

**Present** findings as a diagnostic summary.

### Step 3: Common Issues

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| No failures detected | Task suspended, wrong schema monitored, dedup too aggressive | Check task state, verify monitored schemas |
| Failures detected but no fixes | Guardrails blocking everything | Review guardrail config, check BLOCK entries in audit |
| Fixes generated but wrong | LLM hallucinating, insufficient context | Add to runbook, improve prompt, use larger model |
| Fixes applied but task still fails | Fix was partial or wrong | Check audit log for the generated SQL, verify manually |
| Agent task itself failing | Procedure error, permission issue | Check task history error messages |
| Duplicate fix attempts | Dedup window too short, status not updated | Check SP_DETECT_FAILURES dedup logic |
| DT UPSTREAM_FAILED not resolved | Root cause DT not identified, graph walk failed | Check DYNAMIC_TABLE_GRAPH_HISTORY for the DT chain |
| DT fixed but downstream still failing | Downstream DTs not refreshed after fix | Check VERIFY_DOWNSTREAM_DT entries; may need manual `ALTER DT ... REFRESH` |
| DT cascade: fix applied to wrong DT | Agent fixed the symptom, not the root cause | Verify root_cause_dt in audit log; check upstream graph |
| Task DAG: fix applied but children fail | Child tasks have their own independent issues | Check VERIFY_DOWNSTREAM_TASK entries; may need separate fixes |
| Circuit breaker tripped | Too many escalations or fix loops | Check thresholds, review recent failures, resume when ready |

### Step 4: Apply Fix

Based on diagnosis, either:
- Modify a procedure (present the change for approval)
- Update runbook entries
- Adjust guardrail configuration
- Fix permissions
- Manually refresh a DT: `ALTER DYNAMIC TABLE ... REFRESH`
- Manually retry a task DAG: `EXECUTE TASK <root_task> RETRY LAST`
- Resume a suspended agent: `ALTER TASK {DB}.{SCHEMA}.SELF_HEALING_AGENT RESUME`

**STOP**: Get approval before applying any changes.

### Step 5: Verify

Re-run the agent manually and check results:

```sql
CALL {DB}.{SCHEMA}.SP_DETECT_FAILURES();
```

Then check:
- **Tasks**: `SELECT * FROM HEALING_AUDIT_LOG WHERE ACTION_TYPE IN ('VERIFY_TASK', 'VERIFY_DOWNSTREAM_TASK') ORDER BY CREATED_AT DESC LIMIT 5`
- **DTs**: `SELECT * FROM HEALING_AUDIT_LOG WHERE ACTION_TYPE IN ('VERIFY_DT', 'VERIFY_DOWNSTREAM_DT') ORDER BY CREATED_AT DESC LIMIT 5`

## Fix-Readiness Test (Used by Build Compound)

When running as the final step of a Build compound request, simulate a failure to verify the full pipeline:

**Test Task path:**
1. Create a task referencing a non-existent table
2. Execute the test task (it will fail)
3. Manually trigger `CALL SP_DETECT_FAILURES()` to test the full pipeline
4. Query HEALING_AUDIT_LOG — check for VERIFY_TASK and VERIFY_DOWNSTREAM_TASK entries
5. Check alerts were sent

**Test DT path (if monitoring DTs):**
1. Create a DT with a bad query
2. Wait for refresh to fail
3. Manually trigger `CALL SP_DETECT_FAILURES()`
4. Query HEALING_AUDIT_LOG — check for VERIFY_DT entries

**Test guardrail → HITL path:**
1. Create a failure that produces an ALTER statement (e.g., missing column)
2. Confirm it lands in PENDING_REVIEWS
3. Approve via `CALL SP_APPROVE_FIX('...')`
4. Confirm downstream DAG verification runs

**Test circuit breaker:**
1. Create multiple failures that exceed the threshold
2. Confirm agent self-suspends
3. Confirm alert is sent

**STOP**: Review test results with user.

## Stopping Points

- Step 2: After presenting diagnostics
- Step 4: Before applying fixes
- Fix-readiness: After test results
