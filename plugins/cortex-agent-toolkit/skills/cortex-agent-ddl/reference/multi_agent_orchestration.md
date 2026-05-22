---
name: cortex-agent-ddl-multi-agent-orchestration
description: Infrastructure setup and UDF templates for multi-agent routing — a master agent dispatches queries to specialized sub-agents via custom tools backed by Python UDFs calling the Snowflake Agent REST API
last_verified: 2026-05-07
---

# Multi-Agent Orchestration Reference

## Overview

A **multi-agent orchestration** pattern uses a master routing agent that dispatches user queries to specialized sub-agents via custom tools. Each sub-agent is called through a Python UDF that invokes the Snowflake Agent REST API.

```
User → Master Agent (router)
         ├─ Tool: ASK_SALES_AGENT    → UDF → REST API → SALES_AGENT
         ├─ Tool: ASK_SUPPORT_AGENT  → UDF → REST API → SUPPORT_AGENT
         └─ Tool: ASK_FINANCE_AGENT  → UDF → REST API → FINANCE_AGENT
```

**When to use this pattern:**
- You have 2+ existing Cortex Agents covering different domains
- Users need a single entry point that auto-routes by intent
- Sub-agents are owned by different teams/schemas and you want loose coupling

**When NOT to use:**
- A single agent with multiple SV/CSS tools can handle the routing (simpler)
- You have <3 sub-agents and the tool descriptions are enough to route correctly
- Latency is critical — each hop adds ~2-5s overhead

---

## Infrastructure DDL

### Step 1: Network Rule (egress to Snowflake API)

```sql
CREATE OR REPLACE NETWORK RULE <DB>.<SCHEMA>.cortex_agent_egress_rule
  MODE = EGRESS
  TYPE = HOST_PORT
  VALUE_LIST = ('<YOUR_ACCOUNT>.snowflakecomputing.com');
```

> Replace `<YOUR_ACCOUNT>` with your Snowflake account identifier (e.g., `ABC12345`).

### Step 2: Store PAT Token as Secret

```sql
CREATE OR REPLACE SECRET <DB>.<SCHEMA>.cortex_agent_token_secret
  TYPE = GENERIC_STRING
  SECRET_STRING = '<YOUR_PAT_TOKEN>';
```

> ⚠️ **PAT tokens expire.** Generate from: User Menu → My Profile → Authentication → Generate Token. Track expiration and regenerate before it lapses.

### Step 3: External Access Integration

```sql
CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION cortex_agent_external_access
  ALLOWED_NETWORK_RULES = (<DB>.<SCHEMA>.cortex_agent_egress_rule)
  ALLOWED_AUTHENTICATION_SECRETS = ALL
  ENABLED = TRUE;
```

### Step 4: Grant Permissions

```sql
GRANT READ ON SECRET <DB>.<SCHEMA>.cortex_agent_token_secret TO ROLE <EXECUTION_ROLE>;
GRANT USAGE ON INTEGRATION cortex_agent_external_access TO ROLE <EXECUTION_ROLE>;
```

---

## Agent-Caller UDF Template

Create one UDF per sub-agent. Only the function name and agent URL change between them.

```sql
CREATE OR REPLACE FUNCTION <DB>.<SCHEMA>.ASK_<AGENT_NAME>(user_query VARCHAR)
RETURNS STRING
LANGUAGE PYTHON
RUNTIME_VERSION = '3.12'
PACKAGES = ('requests', 'snowflake-snowpark-python')
EXTERNAL_ACCESS_INTEGRATIONS = (cortex_agent_external_access)
SECRETS = ('agent_token' = <DB>.<SCHEMA>.cortex_agent_token_secret)
HANDLER = 'run_agent'
AS $$
import requests
import json
import _snowflake

def run_agent(user_query: str) -> str:
    token = _snowflake.get_generic_secret_string('agent_token')
    url = "https://<YOUR_ACCOUNT>.snowflakecomputing.com/api/v2/databases/<AGENT_DB>/schemas/<AGENT_SCHEMA>/agents/<AGENT_NAME>:run"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream"
    }

    payload = {
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": user_query}]
            }
        ],
        "stream": True
    }

    response = requests.post(url, headers=headers, json=payload, stream=True)
    response.raise_for_status()

    # Parse SSE stream — collect all text delta events
    collected_text = []
    for line in response.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        data_str = line[len("data:"):].strip()
        if data_str == "[DONE]":
            break
        try:
            event = json.loads(data_str)
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                collected_text.append(delta.get("text", ""))
        except json.JSONDecodeError:
            continue

    return "".join(collected_text) if collected_text else "No response from agent."
$$;
```

### Parameterization

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `<YOUR_ACCOUNT>` | Snowflake account identifier | `ABC12345` |
| `<DB>.<SCHEMA>` | Where the UDF + infra objects live | `MY_DB.AGENTS` |
| `<AGENT_DB>` | Database of the target sub-agent | `SALES_DB` |
| `<AGENT_SCHEMA>` | Schema of the target sub-agent | `ANALYTICS` |
| `<AGENT_NAME>` | Name of the target sub-agent | `SALES_PIPELINE_AGENT` |
| `<EXECUTION_ROLE>` | Role that will call the UDFs | `SYSADMIN` |

---

## Strict-Router Instruction Template

Use this as `instructions.orchestration` for the master agent:

```
You are an intelligent router. Analyze the user's inquiry to determine the correct domain and invoke the appropriate tool.

## Sub-agents

<TOOL_NAME_1>: Use this for questions regarding <domain 1 topics>.
<TOOL_NAME_2>: Use this for questions regarding <domain 2 topics>.
<TOOL_NAME_N>: Use this for questions regarding <domain N topics>.

## Rules
- You MUST invoke the appropriate tool to answer the user's question. Do NOT attempt to answer yourself.
- If the question clearly spans multiple domains, invoke each relevant tool and synthesize the responses.
- If no domain matches the question, respond with: "I can help with questions about <list domains>. Your question doesn't match any of these areas."
- Never fabricate data. Your only source of information is the sub-agent tools.
```

---

## Master Agent Spec Pattern (complete)

```json
{
  "models": {
    "orchestration": "claude-sonnet-4-5"
  },
  "experimental": {
    "EnableAgenticAnalyst": true,
    "EnableVQRFastPath": false
  },
  "orchestration": {
    "budget": {
      "seconds": 180,
      "tokens": 200000
    }
  },
  "instructions": {
    "orchestration": "<STRICT_ROUTER_INSTRUCTIONS>",
    "response": "Present the sub-agent's response directly. Do not add your own analysis unless synthesizing multiple responses.",
    "sample_questions": [
      { "question": "<example routed to agent 1>" },
      { "question": "<example routed to agent 2>" }
    ]
  },
  "tools": [
    {
      "tool_spec": {
        "type": "generic",
        "name": "AskSalesAgent",
        "description": "Routes questions to the Sales Pipeline Agent. Covers: revenue forecasts, deal stages, pipeline velocity, win/loss rates, quota attainment. When NOT to use: customer support tickets, product bugs, finance/billing."
      }
    },
    {
      "tool_spec": {
        "type": "generic",
        "name": "AskSupportAgent",
        "description": "Routes questions to the Customer Support Agent. Covers: ticket volumes, resolution times, CSAT scores, escalation rates, agent performance. When NOT to use: sales pipeline, revenue, product roadmap."
      }
    }
  ],
  "tool_resources": {
    "AskSalesAgent": {
      "function": "MY_DB.AGENTS.ASK_SALES_PIPELINE_AGENT"
    },
    "AskSupportAgent": {
      "function": "MY_DB.AGENTS.ASK_SUPPORT_AGENT"
    }
  }
}
```

> **Note**: `EnableVQRFastPath` is set to `false` for routers. The fast path skips full orchestration, which defeats the purpose of a routing agent that must always reason about which tool to invoke.

> **Note**: `budget.seconds` is set higher (180) because the master agent's clock includes sub-agent execution time.

---

## Troubleshooting

| Error | Cause | Solution |
|-------|-------|----------|
| `Could not read secret` | Missing grants on secret | `GRANT READ ON SECRET ... TO ROLE <role>` |
| HTTP 401 from API | Invalid or expired PAT token | Regenerate token, update secret: `ALTER SECRET ... SET SECRET_STRING = '...'` |
| HTTP 403 from API | Role lacks USAGE on the sub-agent | `GRANT USAGE ON AGENT <fqn> TO ROLE <role>` |
| Connection error / timeout | Network rule doesn't match account URL | Verify `VALUE_LIST` contains exact `<account>.snowflakecomputing.com` |
| "No response from agent" | Sub-agent returned no text (config issue) | Test sub-agent directly: `SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(...)` |
| Tool not invoked by master | Orchestration prompt too vague | Strengthen routing rules — explicit "MUST invoke" language |
| Wrong sub-agent called | Tool descriptions overlap | Add clear "When NOT to use" boundaries to each tool description |
| Slow response (>30s) | Sub-agent is itself multi-tool or budget is low | Increase master `budget.seconds`; optimize sub-agent |

---

## Security Considerations

- **PAT Token Expiration**: Set a calendar reminder. Expired tokens cause silent 401 failures.
- **Least Privilege**: Grant UDF USAGE only to the roles that need the master agent.
- **Network Rule Scope**: Only allow egress to your own account URL — never `*.snowflakecomputing.com`.
- **Secret Rotation**: When rotating PAT, use `ALTER SECRET ... SET SECRET_STRING = '<new_token>'` — no need to recreate the UDF.
- **Sub-agent Access**: The UDF calls the API as the PAT token owner. Ensure that user has USAGE on all sub-agents.

---

## Limitations & Future

- This pattern uses HTTP REST calls — adds ~2-5s latency per hop vs. native tool invocation.
- Sub-agent internal reasoning is NOT visible in the master agent's "Thinking" panel.
- Snowflake may add native multi-agent orchestration in the future, which would eliminate the UDF/PAT/EAI infrastructure.
- PAT tokens are user-scoped — if the token owner's access is revoked, all routing breaks.
