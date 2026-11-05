# Optional cookbook corroboration

Pinned source: [Snowflake-Solutions/cortex-ai-cookbook](https://github.com/Snowflake-Solutions/cortex-ai-cookbook/tree/6ce0df47ac22d3e6bca1da5d09ae96c838f5912e). Read only when relevant; recipes are examples, not executable release authority. Upstream verification dates are upstream claims, not toolkit runtime verification.

- [Mixed grain and verified queries](https://github.com/Snowflake-Solutions/cortex-ai-cookbook/tree/6ce0df47ac22d3e6bca1da5d09ae96c838f5912e/recipes/semantic-views/mixed-grain-and-verified-queries): corroborates grain separation and independent AVG/totals checks; toolkit entry: semantic-view-toolkit Phase 6, existing validator.
- [Description quality](https://github.com/Snowflake-Solutions/cortex-ai-cookbook/tree/6ce0df47ac22d3e6bca1da5d09ae96c838f5912e/recipes/semantic-views/description-quality): rubric is triage, not factual scoring. Proprietary meanings must remain UNKNOWN without evidence; toolkit entry: profiling metadata review and description lint.
- Agent recipes `refinement-loop-from-agent-logs`, `agent-feedback-to-evals`, and `diagnose-agent-requests`: locate in the pinned repository catalog before reading. Corroborate ordinary answered-turn spot checks, existing-conversation corrections, and deterministic span review; toolkit entry: feedback analyzer, feedback pipeline, optimizer debug handoff. Observed event names/attributes are not stable schema contracts.

Reviewed pinned catalog paths: 2026-11-05. Optional paths below are relative to the pinned repository URL above; catalog existence is verified, runtime support is not.

| Optional topic | Exact pinned recipe directory | Use boundary |
|---|---|---|
| Scoping | `recipes/cortex-agents/scoping-agentic-implementations` | Discovery aid only |
| dbt CI/CD | `recipes/cortex-agents/agent-ci-cd-with-dbt` | Compare existing CI patterns; exact-candidate release gate still applies |
| Versioning | `recipes/cortex-agents/agent-versioning-and-promotion` | Verify current account syntax before use |
| OAuth and tenancy | `recipes/cortex-agents/oauth-token-passthrough`; `recipes/cortex-agents/multi-tenant-agents` | No automatic identity/access changes |
| Document and embedded context | `recipes/cortex-agents/document-context`; `recipes/cortex-agents/embedded-app-context` | Explicit application scope required |
| MCP and multi-agent | `recipes/snowflake-mcp/long-running-agents-over-mcp`; `recipes/snowflake-mcp/mcp-or-agent-rest-api`; `recipes/cortex-agents/multi-agent-orchestration` | Optional architecture references, not new toolkit workflows |
| Causal grounding | `recipes/cortex-agents/agent-causal-grounding` | Claims require independent causal evidence |
| Trace refinement | `recipes/semantic-views/refinement-loop-from-agent-logs` | Heuristic review, not correctness proof |
| Feedback and debugging | `recipes/ai-observability/agent-feedback-to-evals`; `recipes/ai-observability/diagnose-agent-requests` | Existing pipeline/debug routes; schema observations are not stable contracts |

Excluded from this integration: gateway governance, cost/budget attribution, PII deployment, and agentic schema mapping. No wholesale import or new deployment surface.

Shared contract: candidate → independently validated → approved. Operator approval is not factual validation; unknown version stays unknown. Do not import recipes wholesale, deploy, grant privileges, or change production automatically. Verify current account syntax and schema before authorized runtime use. Release identity controls come from the toolkit lifecycle, not these recipes.
