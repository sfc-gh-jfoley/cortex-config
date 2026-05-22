# cortex-config

Cortex Code skill vault — reusable skills and plugins for Snowflake Cortex AI workflows.

## Plugins

| Plugin | Skills | Purpose |
|---|---|---|
| **semantic-view-toolkit** | 9 | Full SV lifecycle: discovery, DDL, audit, eval, optimization, GEPA, watch, compose, VQR |
| **cortex-agent-toolkit** | 7 | Full agent lifecycle: create, eval, flags, optimization, GEPA, query |
| **ops-monitor** | 3 | Artifact drift, release changes, self-healing pipelines |
| **rule-governance** | 5 | Rule loading, creation, review, bulk review, memory organization |
| **coco-meta** | 5 | Doc review, plan review, skill testing, prompt determinism, timing |

## Standalone Skills

| Skill | Purpose |
|---|---|
| agent-architect | Multi-agent project framework (research → plan → build → gate → test) |
| architecture-diagram | Generate architecture/system/flow diagrams (Mermaid → Excalidraw → PNG) |
| coco-usage | CoCo token/credit consumption analysis |
| google-doc-formatter | Format markdown as Google Doc |
| lab-builder | Build HOL/workshop labs |
| semantic-view-ddl | (legacy) Build/edit SVs — use sv-ddl from semantic-view-toolkit instead |
| semantic-view-discovery | (legacy) Find SV candidates — use sv-discovery instead |
| snowflake-gslides | Create Google Slides decks |

## Install

```bash
# Install a plugin (once Cortex Code plugin system supports it)
cortex plugin install sfc-gh-jfoley/cortex-config/plugins/semantic-view-toolkit
```

## Usage

```
# Invoke the toolkit router
$semantic-view-toolkit
$cortex-agent-toolkit

# Or invoke individual skills directly
$sv-evaluation
$cortex-agent-optimization
$sv-gepa-optimizer
```

## License

MIT
