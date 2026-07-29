# CoWork Plugin

Snowflake CoWork: investigation and sharing workflows for Cortex Agents. Combine agent responses with multi-step workflows, persistent artifacts, and full source tracing.

## Install

```bash
cortex plugin install cowork
```

## What is CoWork?

CoWork provides two capabilities:

### Artifacts (GA Jun 17, 2026)
Create persistent, shareable references to agent-generated results:
- Chart and table artifacts
- Permission-aware access control
- Version history and archival
- Team sharing and collaboration

**Use when**: You want to turn an agent response into a discoverable, shareable asset.

### Deep Research (GA Jul 7, 2026)
Run multi-step investigations combining structured queries, unstructured search, and analysis:
- Multi-step workflow planning
- Source tracing for every finding
- Combines SQL + Cortex Search results
- Compliance and audit trail support

**Use when**: One query isn't enough — you need a coordinated investigation across multiple data sources with full lineage.

## Architecture

```
Cortex Agents (create from $cortex-agent-toolkit)
    ↓
CoWork Artifacts (create persistent references)
CoWork Deep Research (run multi-step investigations)
    ↓
Team collaboration, auditing, compliance
```

## Entry Points

### Router (skill-loader)

```bash
$cowork
```

Ask CoWork where to route you:
- "I want to share my result as an artifact" → artifacts sub-skill
- "I need to investigate across multiple sources" → deep research sub-skill

### Direct Sub-Skills

```bash
$cowork:cowork-artifacts
# Create and manage persistent result references
```

```bash
$cowork:cowork-deep-research
# Run multi-step investigations with source tracing
```

## Skills

| Skill | Purpose | When to Use |
|-------|---------|-------------|
| `cowork-artifacts` | Create, manage, and share artifact references from agent responses | Building reusable result assets, team sharing, audit trails |
| `cowork-deep-research` | Multi-step investigations with source tracing across structured and unstructured data | Competitive research, customer analysis, incident investigation, complex discovery |

## Relationship to Other Skills

- **cortex-agent-toolkit**: CoWork is a consumer of agents. Create agents first in `$cortex-agent-toolkit`, then use CoWork to scale investigations or share results.
- **semantic-view-toolkit**: Both agents and CoWork consume semantic views. Optimize your SVs in `$semantic-view-toolkit` to improve data quality for both.

## Recommended Workflows

### Workflow 1: Artifact Sharing
```
Create agent ($cortex-agent-toolkit)
  ├─ Run agent query
  ├─ Examine result (chart, table, summary)
  └─ Create artifact ($cowork:cowork-artifacts)
       ├─ Grant access to team
       └─ Team discovers and uses artifact
```

### Workflow 2: Deep Research Investigation
```
Define research question
  ├─ Plan multi-step workflow ($cowork:cowork-deep-research)
  │   ├─ Step 1: SQL query on database A
  │   ├─ Step 2: Cortex Search on content repository
  │   ├─ Step 3: Analyze + combine findings
  │   └─ Step 4: Compile report with source attribution
  └─ Output: findings with full source tracing
```

### Workflow 3: Compliance / Audit Trail
```
Investigation result → Create artifact
  ├─ Trace lineage to original sources
  ├─ Document permissions and access
  └─ Archive for audit
```

## Key Concepts

### Artifacts
- **Reference-based**: Artifacts reference existing data; they don't copy or move it
- **Permission-aware**: Artifact access is separate from data access (data ACLs still apply)
- **Versioning**: Track changes over time; archival and rollback support
- **Sharing**: Grant read, read+update, or read+share permissions per team member

### Deep Research
- **Source tracing**: Every finding links to the query, search result, or analysis step that produced it
- **Multi-step**: Orchestrate SQL queries, searches, and analysis in sequence
- **Auditable**: Full workflow history and data lineage
- **Compliance-ready**: suitable for regulatory or internal audit requirements

## Prerequisites

See `PREREQUISITES.md` for:
- Account setup and feature enablement
- Permission model for artifacts
- Role grants for deep research
- Cortex Search configuration

## Common Questions

**Q: Do artifacts grant data access?**  
A: No. Artifacts reference existing data — your teammate still needs their own data permissions. See `PREREQUISITES.md` → Permission Model.

**Q: Can I modify an artifact after sharing?**  
A: Yes. Artifacts support versioning. You can update, archive, or restore versions. Sharing access is maintained across versions.

**Q: What data sources does Deep Research support?**  
A: Any Snowflake table/view (via SQL) plus Cortex Search results (from indexed documents). You can also integrate Cortex Analytics results.

**Q: How do I trace findings back to sources?**  
A: Deep Research automatically tracks every step. Use Phase 4 (Compile Findings) to generate attribution reports.

**Q: Is CoWork available in my region?**  
A: Yes — CoWork is GA in all Snowflake regions. No region-gating.

## Support

For issues or questions, refer to the individual sub-skill documentation or contact your Snowflake support team.
