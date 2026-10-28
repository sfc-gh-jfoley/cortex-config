# Observe pillar: AI-Ops & Governance

**Templates:** O8 (observability/evaluation failures), O1 filtered to access-control codes (003001, 002003, 002043).

## Collect
1. **AI observability / evaluation health** (O8):
   - `Cortex Agent ? does not exist or not authorized` when reading observability events: users can't see agents they're trying to monitor
   - `Insufficient privileges ... GET_AI_OBSERVABILITY_EVENTS / GET_AI_EVALUATION_DATA`: missing grants
   - `AI_EVALUATION` / `AI_OBSERVABILITY_RUN` failures: evaluation not operational
   - hand-built feedback analysis (`AI_CLASSIFY` over thread or rating logs): DIY eval loop
   Better pattern: a central AI-ops role, standardized `EXECUTE_AI_EVALUATION` (metrics pinned with name/version, e.g. v3),
   a governed feedback table.
2. **Privilege-gap clusters**: group access errors by *role pattern* (strip the business-unit prefix to a template like
   `BU_*_S_ROLE`) and by object type (external volume, schema, database, function). Record the pattern, users affected and volume.
3. **Sensitive-data signals**: role or schema tokens like CPNI / PII / PHI / PCI. Record the *class* only. This informs
   lab governance modules (masking, row access policies) and tightens the firewall.

## Emit `findings.json.ai_ops_governance`
Same schema. Sensitive-data classes go in `sensitivity: ["CPNI-like"]`.
