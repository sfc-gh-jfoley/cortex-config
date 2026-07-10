# Track 3: CoWork Plugin Expansion

## Overview
New plugin `plugins/cowork/` supporting two GA CoWork features released Jun 17 – Jul 7:
- **Artifacts** (Jun 17 GA): persistent live chart/table references from agent responses; permission-aware sharing
- **Deep Research** (Jul 7 GA): multi-step AI investigation across structured + unstructured data, source-traced

## Architecture

### Sub-Skills
- `cowork-artifacts`: Create, manage, and share persistent artifact references; permission model
- `cowork-deep-research`: Multi-step investigation workflows; source tracing; combining structured queries with unstructured analysis

### Plugin Structure
```
plugins/cowork/
├── SKILL.md (router)
├── .cortex-plugin/
│   └── activation.md
├── README.md
├── PREREQUISITES.md
├── skills/
│   ├── cowork-artifacts/
│   │   └── SKILL.md
│   └── cowork-deep-research/
│       └── SKILL.md
```

**Total new files: 6**

## What to Build

### Root SKILL.md (Router)
- Decision matrix: when to use Artifacts vs. Deep Research
- Cross-reference: CoWork as CONSUMER of Cortex Agents (not a replacement)
- Links to both sub-skills

### activation.md
- Entry conditions: CoWork feature flag enabled in account
- Phase 0 checks: verify artifacts API availability, deep research licensing

### README.md
- Overview of CoWork as end-user investigation layer
- Positioning: agents → responses → artifacts/deep-research workflows
- Feature matrix for Artifacts and Deep Research

### PREREQUISITES.md
- CoWork account activation
- Permission model: creator can share artifacts with role-based access
- Deep Research requires Cortex search service accessible

### cowork-artifacts/SKILL.md
- Creating live artifact references from agent responses
- Managing artifact lifecycle (update, archive, share)
- Permission delegation: data access remains consumer's responsibility
- Phase 1: Discovery and authentication
- Phase 2: Create artifact reference
- Phase 3: Share and permission delegation
- Phase 4: Monitor artifact usage and lifecycle

### cowork-deep-research/SKILL.md
- Initiating multi-step investigation across structured + unstructured
- Source tracing and lineage of findings
- Phase 1: Define research scope
- Phase 2: Plan multi-step workflow (queries, search, analysis)
- Phase 3: Execute and trace sources
- Phase 4: Compile findings with source attribution

## Risks & Mitigations

### Risk: Conflation with Cortex Agents
**Impact**: Users try to use CoWork to _create_ agents, rather than to use agents to launch investigations.  
**Mitigation**: 
- Bidirectional cross-reference in `cortex-agent-toolkit/SKILL.md`: "For end-user investigation workflows, see cowork plugin"
- Clear positioning in root SKILL.md: CoWork is built on top of agents, not a replacement

### Risk: Missing Permission Model Documentation
**Impact**: Users share artifacts with insufficient understanding of scope; data leakage or access denials.  
**Mitigation**: PREREQUISITES.md explicitly documents permission model; cowork-artifacts Phase 3 includes permission-delegation walkthrough

### Risk: Source Tracing Opacity in Deep Research
**Impact**: Users cannot verify which source(s) produced a finding; reduces trust in investigation results.  
**Mitigation**: cowork-deep-research Phase 4 focuses on source attribution; every finding linked to structured query, search result, or analysis step that produced it

## Breaking Changes
**None for existing skills.** New plugin is standalone and does not modify existing code paths.

## Cross-Manifest Dependencies
- **Outbound**: references Cortex Agents (positions relative to agents)
- **Inbound**: `cortex-agent-toolkit/SKILL.md` gains one bidirectional cross-reference line

## Verification Checklist (Tethering Contract)
- [ ] Plugin directory exists: `plugins/cowork/`
- [ ] Root SKILL.md present and routes to two sub-skills
- [ ] `activation.md` documents entry conditions
- [ ] Both sub-skill SKILL.md files exist and define distinct workflows
- [ ] README.md explains CoWork positioning relative to agents
- [ ] PREREQUISITES.md documents permission model
- [ ] Bidirectional cross-ref in `cortex-agent-toolkit/SKILL.md` created
- [ ] No modification to skill-loader yet (batch step 7)

## Files to Create
1. `plugins/cowork/SKILL.md` (router)
2. `plugins/cowork/.cortex-plugin/activation.md`
3. `plugins/cowork/README.md`
4. `plugins/cowork/PREREQUISITES.md`
5. `plugins/cowork/skills/cowork-artifacts/SKILL.md`
6. `plugins/cowork/skills/cowork-deep-research/SKILL.md`

## Files to Modify
1. `plugins/cortex-agent-toolkit/SKILL.md` — add cross-reference line to cowork plugin
