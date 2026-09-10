# Phase 4: Activation (optional — requires AGENT_FQN)

Skip entirely if:
- `AGENT_FQN` was not provided
- `FASTPATH_ENABLED = false` (flagged in Phase 1)

Live-test whether each VQR actually triggers fast-path when the exact question is asked
through the agent. Uses DATA_AGENT_RUN — each call consumes agent budget.

## Step 4.1 — Confirm with user

```
Phase 4 will invoke the agent once per VQR (<N> calls).
Each call consumes your agent token budget.
Proceed? (yes / skip Phase 4)
```

**STOP** — wait for confirmation.

## Step 4.2 — VQR fast-path detection method

Detection uses SQL signature comparison (no direct access to confidence field via SQL):

For each VQR:
1. Invoke agent with exact VQR question via `SNOWFLAKE.CORTEX.DATA_AGENT_RUN`
2. Extract the SQL from the `TelemetryAnalytics` (or relevant tool) tool_result
3. Compare returned SQL to registered VQR SQL:
   - If SQL matches VQR SQL (same structure, column aliases, table refs) → `FAST_PATH_HIT`
   - If SQL uses `SELECT * FROM SEMANTIC_VIEW(...)` → `LLM_SV` (LLM generated, SV syntax)
   - If SQL uses different structure → `LLM_CTE` (LLM generated, CTE syntax)

> Note: The REST API `/agents/{name}:run` exposes `confidence.type = "verified_query"` directly.
> If REST access is available, prefer that over SQL pattern matching.

```
[FAST_PATH_HIT]  VQR "<name>" — question triggers VQR fast-path ✓
[LLM_SV]         VQR "<name>" — LLM generated (SEMANTIC_VIEW syntax)
[LLM_CTE]        VQR "<name>" — LLM generated (CTE syntax, may be correct)
[NO_TOOL_CALL]   VQR "<name>" — agent did not call the SV tool at all
```

## Step 4.3 — Interpret misses

For VQRs that did NOT trigger fast-path:

| SQL type returned | Likely cause | Recommendation |
|-------------------|-------------|----------------|
| LLM_SV or LLM_CTE with CORRECT SQL | Question phrasing too far from VQR | Update VQR question text to match user phrasing |
| LLM_SV or LLM_CTE with WRONG SQL | VQR miss AND LLM error | High-value VQR — fix phrasing AND keep as eval ground truth |
| NO_TOOL_CALL | Agent routing problem — unrelated to VQR | Check orchestration instructions (Agent Check A) |

Record `activation_result` per VQR.
