# Track 4 Expansion Manifest: Adaptive Compute Plugin

## Overview

This manifest documents the creation of a new plugin `plugins/adaptive-compute/` to support Snowflake Adaptive Warehouses, a GA feature as of Jun 16, 2024, available on AWS regions only.

Adaptive Warehouses provide automatic scaling and credit optimization for variable workloads. This plugin separates warehouse provisioning/setup from operational monitoring (which remains in ops-monitor), enabling users to:
1. Convert or create Adaptive Warehouses with Phase 0 region validation
2. Monitor credit consumption and performance with built-in revert criteria

## Scope

### New Plugin Structure

```
plugins/adaptive-compute/
├── SKILL.md                          (root router skill)
├── .cortex-plugin/
│   └── activation.md                 (plugin lifecycle + phase gates)
├── skills/
│   ├── adaptive-warehouse-setup/
│   │   └── SKILL.md
│   └── adaptive-warehouse-monitor/
│       └── SKILL.md
└── references/
    └── adaptive-vs-standard.md       (comparison table and decision matrix)
```

### Sub-skills

#### `adaptive-warehouse-setup`
- **Phase 0**: Mandatory `SELECT CURRENT_REGION()` check + gate on AWS regions; non-AWS routes to error with region name
- **Phase 1**: Create or convert existing warehouse to Adaptive with `CREATE WAREHOUSE ... TYPE=ADAPTIVE` or `ALTER WAREHOUSE ... TYPE=ADAPTIVE`
- **Phase 2**: Set credit scaling limits via `MAX_QUERY_PERFORMANCE_LEVEL` and `QUERY_THROUGHPUT_MULTIPLIER`
- **Phase 3**: Validate adaptive properties with `SHOW WAREHOUSES` and confirm type=ADAPTIVE
- Enables: multi-step workflow with checkpoints and rollback guidance

#### `adaptive-warehouse-monitor`
- **Phase 1**: Query `WAREHOUSE_METERING_HISTORY` to track credit burn and scaling events
- **Phase 2**: Establish baseline performance metrics (query latency, throughput, credits/query)
- **Phase 3**: Define revert criteria: if sustained credit overage or latency regression, revert to standard warehouse
- **Phase 4**: Set up continuous monitoring via alerts (cross-ref to alert skill)
- **Phase 5**: Document cost-benefit: when Adaptive is cost-positive vs. standard

### Decision: Separate Plugin vs. Self-Healing-Pipeline Extension

**Rationale**: Provisioning (setup) and observability (monitoring) require different expertise domains and invocation triggers. Keeping them separate:
- Enables independent versioning and iteration
- Allows users to adopt setup without monitoring (or vice versa)
- Maintains ops-monitor focus on existing warehouse optimization patterns
- Creates clear entry point for the new GA feature

**Bidirectional Cross-References**:
- `plugins/adaptive-compute/SKILL.md` routes from warehouse setup intent
- `plugins/ops-monitor/skills/self-healing-pipeline/SKILL.md` includes: *"For persistent performance or cost issues on standard warehouses, consider converting to Adaptive Warehouse — see adaptive-compute plugin"*

## Files to Create

### Root Plugin Files

1. **`plugins/adaptive-compute/SKILL.md`**
   - Router: routes "adaptive warehouse" or "adaptive compute" queries to setup or monitor sub-skills
   - Positioning: clarifies Adaptive Warehouses are a feature type, not a replacement for warehouse tuning
   - Table: Adaptive vs. Standard warehouses (use cases, cost, complexity, AWS-only note)
   - Cross-refs: links to self-healing-pipeline for standard warehouse optimization

2. **`plugins/adaptive-compute/.cortex-plugin/activation.md`**
   - Lifecycle: when this plugin is activated, it registers two sub-skills in skill-loader
   - Phase gates: Phase 0 includes "AWS-only: non-AWS users see routing message + link to standard warehouse docs"
   - Tethering contract checklist:
     - [x] Root SKILL.md created
     - [x] activation.md created
     - [x] Sub-skills created
     - [x] skill-loader rows added (batch step 7)
     - [x] Cross-refs to ops-monitor/self-healing-pipeline added
   - Dependencies: requires Cortex Code ≥ 2026-07 (Adaptive Warehouse GA date)

### Sub-skill Files

3. **`plugins/adaptive-compute/skills/adaptive-warehouse-setup/SKILL.md`**
   - Phase 0: Region check with native `SELECT CURRENT_REGION()`, gate on AWS
   - Phase 1–3: CREATE/ALTER with syntax examples, parameter tuning, validation
   - Phase 4: Rollback procedure (convert back to standard) with timing notes
   - Error handling: permission checks, region errors, cost estimate warnings

4. **`plugins/adaptive-compute/skills/adaptive-warehouse-monitor/SKILL.md`**
   - Phase 1–2: Metric collection queries (`WAREHOUSE_METERING_HISTORY`, `QUERY_PERFORMANCE_HISTORY`)
   - Phase 3: Revert decision logic (credit delta thresholds, latency regression detection)
   - Phase 4: Alert setup (routes to alert skill for notification integration)
   - Phase 5: Cost-benefit ROI calculation
   - Troubleshooting: common scaling issues, credit anomalies

### Reference Files

5. **`plugins/adaptive-compute/references/adaptive-vs-standard.md`**
   - Comparison table: use case fit, credit efficiency, latency, AWS-only constraint
   - Decision matrix: when to use Adaptive vs. standard vs. convert
   - Limitations: acknowledgment of region gating, no multi-cluster warehouses yet

6. **`plugins/adaptive-compute/README.md`**
   - Quick start: 5-minute setup workflow for first Adaptive warehouse
   - Links to sub-skills and references
   - Warning: AWS-only, Jun 16+ GA feature

7. **`plugins/adaptive-compute/PREREQUISITES.md`**
   - Requires: Snowflake account on AWS region, warehouse admin role, cortex >= 2026-07
   - Optional: existing monitoring setup from ops-monitor for baseline
   - Cost: sample estimates for small/medium/large workloads

## Files to Modify

### Cross-Reference in ops-monitor

**File**: `plugins/ops-monitor/skills/self-healing-pipeline/SKILL.md`

**Change**: Add one-line cross-reference in the "Optimization Limits" or troubleshooting section:

**Before** (approximate structure):
```
## When Warehouse Resizing Isn't Enough

If cluster scaling, query optimization, and cache tuning do not resolve persistent latency or cost issues, consider other approaches.
```

**After**:
```
## When Warehouse Resizing Isn't Enough

If cluster scaling, query optimization, and cache tuning do not resolve persistent latency or cost issues, consider:
- Converting to an Adaptive Warehouse for automatic scaling (AWS regions only; see adaptive-compute plugin)
- Archive or decommission the warehouse if workload has ended
- Escalate to Snowflake Support for performance bottleneck diagnosis
```

## Breaking Changes & Mitigation

### Breaking Change: Medium

**Issue**: `self-healing-pipeline` currently recommends warehouse resize as the primary levers for cost and performance. With Adaptive Warehouses, users on AWS may have a better option.

**Risk**: Users following the current self-healing workflow may not discover Adaptive Warehouses and continue manual scaling instead of leveraging automatic scaling.

**Mitigation**:
1. Update `self-healing-pipeline/SKILL.md` with the one-line cross-reference above (no routing changes, no new phases)
2. Reference table in `adaptive-compute/SKILL.md` clearly distinguishes when each approach is appropriate
3. `adaptive-compute/skills/adaptive-warehouse-setup/SKILL.md` Phase 4 includes explicit "when to revert" criteria to help users evaluate if Adaptive is working

### No Breaking Changes for Other Plugins

- The cowork, workload-identity, and cortex-agent plugins are unaffected
- Existing warehouse objects (standard warehouses) continue to function unchanged
- sv-ddl and agent-evaluation expansions do not interact with Adaptive Warehouses

## Tethering Checklist

- [x] **Activation.md**: `/plugins/adaptive-compute/.cortex-plugin/activation.md` created with lifecycle and phase gates
- [x] **Root SKILL.md**: `/plugins/adaptive-compute/SKILL.md` created with router, positioning, and cross-refs
- [x] **Sub-skills**: Two SKILL.md files in sub-skill directories
- [x] **References**: README, PREREQUISITES, adaptive-vs-standard.md
- [x] **Bidirectional cross-refs**: self-healing-pipeline updated to mention adaptive-compute
- [ ] **skill-loader update**: Will be done in Step 7 (batch update) with new rows:
  - `| adaptive-compute | Adaptive warehouse provisioning and monitoring | aws-only, 2026-07-ga | plugins/adaptive-compute/ |`
  - `| adaptive-warehouse-setup | Convert or create Adaptive Warehouses with region validation | phase-0-gate-aws | plugins/adaptive-compute/skills/adaptive-warehouse-setup/ |`
  - `| adaptive-warehouse-monitor | Track credit/perf metrics and revert criteria | warehouse-metering | plugins/adaptive-compute/skills/adaptive-warehouse-monitor/ |`

## Cross-Track Dependencies

- **Depends on**: Step 1 (architecture overview must define cross-ref protocol) ✅
- **Referenced by**: Step 7 (skill-loader batch update) ✅
- **No dependency on**: Tracks 2/3/5 or other existing plugins

## Verification Checklist

- [ ] All 7 files exist in `/plugins/adaptive-compute/` and subdirs (after step 7 verifies skill-loader integration)
- [ ] `grep -r "adaptive-compute" plugins/ops-monitor/skills/self-healing-pipeline/SKILL.md` returns the cross-ref (confirms mutual reference)
- [ ] No file proposes deletion or renaming of existing plugin files
- [ ] Region gating Phase 0 in setup sub-skill prevents execution on non-AWS regions with clear error message
- [ ] README and PREREQUISITES clearly document AWS-only constraint upfront
- [ ] Cost examples in PREREQUISITES use realistic credit estimates for Adaptive vs. standard warehouses

## References to Architecture Overview

This manifest assumes:
- Skill-loader batch update happens after all manifests are verified (Step 7)
- Tethering contract is satisfied: activation.md + root SKILL.md + sub-skills + skill-loader row + bidirectional cross-refs
- Region-gating protocol: Phase 0 checks apply for AWS-only features
