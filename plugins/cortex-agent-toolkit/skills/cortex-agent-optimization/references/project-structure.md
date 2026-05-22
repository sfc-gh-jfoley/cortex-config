# Project Structure

Expected file layout for a project using the optimization workflow.

## Single-Agent Project (Flat Structure)

```
my_agent_project/
├── agent/                                  # Source of truth for agent behavior
│   ├── orchestration_instructions.md       # Decision logic, routing, workflows
│   ├── response_instructions.md            # Output format, tone, structure rules
│   ├── tool_descriptions.md                # Per-tool descriptions (## Tool: <name>)
│   └── spec_base.json                      # Static config: models, budget, tool types, tool_resources
│
├── scripts/
│   └── build_agent_spec.py                 # Assembles agent/*.md + spec_base.json → deploy.sql
│
├── deploy.sql                              # Generated — do not edit by hand
├── optimization_log.md                     # Iteration history with scores and decisions
├── metadata.yaml                           # Agent database/schema/name, workspace config
├── eval_config_dev_r1.yaml                 # DEV slot 1 eval config
├── eval_config_dev_r2.yaml                 # DEV slot 2 eval config (through r<RUNS_PER_SPLIT>)
├── eval_config_test_r1.yaml                # TEST slot 1 eval config
├── eval_config_test_r2.yaml                # TEST slot 2 eval config (through r<RUNS_PER_SPLIT>)
├── DEPLOYMENT_INSTRUCTIONS.md              # (Optional) project-specific workflow notes
└── snapshots/                              # Versioned copies of agent/*.md per iteration
    └── baseline/                           # Original instructions before any optimization
```

## Multi-Agent Workspace (Shared Tooling)

```
agent_workspace/
├── scripts/                                # Shared across all agents
│   └── build_agent_spec.py
│
├── investigation_agent/                    # First agent
│   ├── agent/                              # Source of truth
│   │   ├── orchestration_instructions.md
│   │   ├── response_instructions.md
│   │   ├── tool_descriptions.md
│   │   └── spec_base.json
│   ├── deploy.sql
│   ├── optimization_log.md
│   ├── metadata.yaml
│   ├── eval_config_dev_r1.yaml
│   ├── eval_config_dev_r2.yaml             (through r<RUNS_PER_SPLIT>)
│   ├── eval_config_test_r1.yaml
│   ├── eval_config_test_r2.yaml            (through r<RUNS_PER_SPLIT>)
│   └── snapshots/
│       └── baseline/
│
└── recommendation_agent/                   # Second agent (optional)
    └── ...
```

## Conventions

- `agent/*.md` files are the source of truth; `deploy.sql` is always generated.
- Never edit `deploy.sql` by hand.
- Use `ALTER AGENT ... MODIFY LIVE VERSION`, never `CREATE OR REPLACE`.
- Single-agent projects use flat structure; multi-agent workspaces detected when `scripts/` already exists.
- Before every edit to `agent/*.md`, a snapshot of the current state must exist in `snapshots/`.
- On accept: snapshot `agent/*.md` to `snapshots/<ITER_NAME>/`.
- On reject: restore `agent/*.md` from the last accepted snapshot (or `baseline/` if no iterations accepted).
