# Cortex Agent Experimental Flags Reference

Last updated: 2026-04-09

This document catalogs all known experimental flags and chart customization options
for Cortex Agents. Flags are set in the agent specification under the `experimental` key.

---

## Agent-Level Experimental Flags

These go in the agent spec JSON under `"experimental"`:

```json
{
  "experimental": {
    "FlagName": true
  }
}
```

### EnableAgenticAnalyst

**Status:** Widely deployed, most commonly used flag

**What it does:**
Enables "Agentic Analyst" mode for Cortex Analyst (text-to-SQL) tool calls.
Provides significantly lower latency and improved quality compared to the default
routing mode. The default mode favors semantic SQL routing; Agentic Analyst provides
a faster, more accurate path.

**When to use:**
- Any agent with `cortex_analyst_text_to_sql` tools
- Recommended as a default for all new agents with structured data tools

**Tradeoffs:**
- Generally improves both latency and accuracy -- minimal downside
- Behavioral differences from default mode in edge cases

**Source:** Christopher Pelky (Cortex team): "lower latency than the default mode
with higher accuracy"

---

### EnableVQRFastPath

**Status:** Available, used with agents that have Verified Query Representations

**What it does:**
Enables a fast path for VQRs (Verified Query Representations). When a user question
closely matches a pre-verified query, the agent bypasses full text-to-SQL generation
and uses the verified query directly.

**When to use:**
- Agents with semantic views that have VQRs defined
- Latency-sensitive applications where known query patterns dominate
- Agents where accuracy on common questions is critical (VQRs are human-verified)

**When NOT to use:**
- Agents without VQRs (flag has no effect)
- Exploratory analytics agents where questions are highly varied

**Tradeoffs:**
- Reduces latency for known patterns
- May reduce flexibility for novel questions that partially match a VQR

---

### EnableUnrestrictedChartTool

**Status:** Available, extends Agentic Charting

**What it does:**
Removes the fixed chart-type allowlist from Agentic Charting. By default, agents
can only generate bar, line, arc, point, and rect Vega-Lite charts. With this flag,
any valid single-view Vega-Lite spec is accepted.

**Chart types unlocked:**
- Area charts
- Dual-axis layered charts
- Boxplots
- Waterfall charts
- Annotations and reference lines
- Any other valid Vega-Lite mark type

**When to use:**
- Agents that serve data analysts or executives who need rich visualizations
- Use cases requiring area charts, dual-axis, boxplots, or waterfall charts
- Demo agents where visual impact matters

**When NOT to use:**
- Simple Q&A agents that rarely chart
- Environments where strict chart-type guardrails are desired

**Tradeoffs:**
- Reduced server-side guardrails (e.g., won't block a bar chart with 200 categories)
- Chart selection and styling may differ from restricted mode
- More freedom = both better and different results

**Can also be enabled at account level:**
```sql
ALTER ACCOUNT <<ACCOUNT_ID>> SET COPILOT_ORCHESTRATOR_PARAM_157 = 'true'
  parameter_comment="EnableUnrestrictedChartTool";
```

**Contact:** Adrian Stepniak (adrian.stepniak@snowflake.com)

---

### EnableSkillBasedPromptNoExtendedThinking

**Status:** Private Preview (requires Agent Skills signup)

**What it does:**
Disables extended thinking (longer internal chain-of-thought reasoning) when the
skill-based orchestration prompt is active. Skills use a modified system prompt that
includes skill discovery, selection, and execution logic.

**When to use:**
- Agents with skills attached from stages or Git repos
- Latency-sensitive agents where skill routing is straightforward
- When extended thinking causes over-deliberation on skill selection

**When NOT to use:**
- Agents without skills configured (flag is a no-op)
- Complex multi-skill agents where careful reasoning about skill selection matters

**Prerequisites:**
- Agent Skills Private Preview access (signup form required)
- Skills configured in the agent specification

**Tradeoffs:**
- Faster responses at the potential cost of less deliberative skill selection
- Best paired with `EnableVQRFastPath` for maximum speed

---

## Account-Level Parameters (Require Deployment Access)

These are NOT set in the agent spec. They require ALTER ACCOUNT access (internal only
or account admin).

| Parameter | Flag Name | Description |
|-----------|-----------|-------------|
| `PARAM_150` | `EnableAgentLevelChartCustomization` | Enables agent-level `vega_template` and soft chart instructions |
| `PARAM_151` | `EnableVizPolicies` | Enables `viz_policies` rule-based chart enforcement at any level |
| `PARAM_108` | `EnableChartCustomizationFromSemanticModel` | Enables SM-level chart customization via `custom_instructions` |
| `PARAM_157` | `EnableUnrestrictedChartTool` | Account-wide unrestricted charting (same as agent-level flag) |

```sql
ALTER ACCOUNT <<ACCOUNT_ID>> SET COPILOT_ORCHESTRATOR_PARAM_150 = 'true'
  parameter_comment="EnableAgentLevelChartCustomization";
```

---

## Chart Customization

Chart customization is NOT an experimental flag -- it's a block embedded in agent
orchestration instructions or semantic model custom_instructions. It requires certain
account-level params to be enabled (see above).

### Placement

| Level | Field | Scope |
|-------|-------|-------|
| Agent | `instructions.orchestration` | Global baseline for all charts |
| Semantic View | `module_custom_instructions.sql_generation` *(preferred)* | Overrides agent for that SV only |
| Semantic View (legacy) | `custom_instructions` | Same scope; superseded when `module_custom_instructions.sql_generation` is also set |

> **Note:** When both agent and semantic view define a `vega_template`, the agent template
> is applied first and the semantic view template is applied second. On conflicting keys,
> the semantic view wins.

### Syntax

Wrap everything in `<chart_customization>` tags. This block is **stripped before the
LLM sees it** -- raw JSON and policy arrays never pollute the model's context.

```xml
<chart_customization>
  ... soft instructions, vega_template:, viz_policies: ...
</chart_customization>
```

### Three Content Types

#### 1. Soft Instructions (LLM guidance, no guarantee)

```xml
<chart_customization>
Prefer bar charts for comparisons. Use short axis labels.
</chart_customization>
```

#### 2. vega_template: (deterministic deep-merge)

Partial Vega-Lite JSON merged onto every generated spec. Default mode: `override`
(template wins). Add `"usermeta": {"merge": "extend"}` to only fill missing values.

```xml
<chart_customization>
vega_template:
{
  "config": {
    "background": "#1a1a2e",
    "axis": {"labelColor": "#ffffff", "titleColor": "#ffffff"}
  },
  "encoding": {
    "color": {"scale": {"scheme": "tableau10"}}
  }
}
</chart_customization>
```

#### 3. viz_policies: (rule-based enforcement)

> **Internal-only:** `viz_policies` is not documented in the public Snowflake docs as of
> 2026-04-17. It is available via `PARAM_151` (EnableVizPolicies) but treat as unstable —
> do not rely on it in customer-facing demos without confirming with the Cortex team.

Rules use AND logic. Mechanical actions apply deterministically; LLM actions trigger
spec regeneration.

```xml
<chart_customization>
viz_policies:
[
  {
    "name": "brand_colors",
    "rules": [{"column": "TICKER", "role": "COLOR"}],
    "actions": [{"type": "ensure_color", "params": {"mapping": {"SNOW": "#29B5E8"}}}]
  }
]
</chart_customization>
```

### Font Compatibility

Font settings go in the `config` block of `vega_template`. Charts render in two contexts:
**Snowsight** (browser, user OS fonts) and a **Linux server-side container** (image export/
validation). Named fonts like `Arial` or `Georgia` may not be installed in the container.

Use CSS generic families for guaranteed cross-platform rendering:

| Generic family | Resolves to |
|----------------|-------------|
| `sans-serif` | Arial (Win/macOS), DejaVu Sans or Liberation Sans (Linux) |
| `serif` | Times New Roman (Win/macOS), DejaVu Serif or Liberation Serif (Linux) |
| `monospace` | Courier New (Win/macOS), DejaVu Sans Mono or Liberation Mono (Linux) |

Common config font properties:

| Property | Where it applies |
|----------|-----------------|
| `title.font`, `title.fontSize`, `title.fontWeight`, `title.fontStyle` | Chart title |
| `axis.labelFont`, `axis.labelFontSize` | Axis tick labels |
| `axis.titleFont`, `axis.titleFontSize` | Axis titles (e.g. "Revenue") |
| `header.labelFont`, `header.labelFontSize` | Facet / small-multiple headers |
| `legend.labelFont`, `legend.labelFontSize` | Legend value labels |
| `legend.titleFont`, `legend.titleFontSize` | Legend title |
| `mark.font` | Text marks (annotations) |

> **Tip:** Before deploying a `vega_template`, paste a representative chart spec (with your
> template already merged in) into the [Vega Editor](https://vega.github.io/editor/) to
> validate. Check the console for warnings about invalid property names, type mismatches,
> or unreachable `calculate` expressions.

### Color Mapping with `_color` Transform

For exact per-value hex colors, use a `calculate` transform to create a `_color` field:

```json
{
  "transform": [
    {
      "calculate": "datum.STATUS === 'Active' ? '#22c55e' : datum.STATUS === 'Inactive' ? '#ef4444' : datum.STATUS === 'Pending' ? '#eab308' : ''",
      "as": "_color"
    }
  ],
  "encoding": {
    "color": {
      "field": "STATUS",
      "type": "nominal",
      "scale": {"range": {"field": "_color"}}
    }
  }
}
```

**Important caveats:**
- The `_color` transform is merged into every chart at that level, regardless of which
  column the LLM chose to color. If a different column is used for color, `_color` is
  present in the data but colors won't match.
- Only one column can be targeted per template.
- Values not listed in the expression receive an empty string; Vega-Lite uses its default
  color for those.

**Alternative — pinned values with palette fallback** (use `"merge": "extend"` to preserve
LLM's existing color choices and only add new mappings):

```json
{
  "encoding": {
    "color": {
      "scale": {
        "domain": ["Furniture", "Technology", "Office Supplies"],
        "range": ["#4e79a7", "#f28e2b", "#e15759"],
        "scheme": "tableau10"
      }
    }
  },
  "usermeta": {"merge": "extend"}
}
```

### Mechanical Actions (Deterministic)

| Action | Key Params | Effect |
|--------|-----------|--------|
| `ensure_color` | `mapping: {"val": "#hex"}` | Per-value colors via calculate transform |
| `ensure_shape` | `mapping: {"val": "diamond"}` | Per-value point shapes |
| `ensure_sort` | `channel`, `order`, `custom_order: [...]` | Forces sort on an encoding channel |
| `ensure_number_format` | `format` (D3), `channel` (optional) | Sets axis/legend format |
| `ensure_axis_range` | `channel`, `min`, `max` | Sets scale domain min/max |

### LLM-Driven Actions (Regenerates Spec)

| Action | Key Params | Effect |
|--------|-----------|--------|
| `change_viz_type` | `viz_type: "bar"` | Asks LLM to redraw as different mark type |
| `new_prompt` | `instruction: "..."` | Injects free-form requirement into regeneration |

### Rule Fields

```json
{
  "column": "REVENUE",
  "role": "Y_AXIS",
  "viz_type": "bar",
  "negate": false
}
```

- `column`: match when this column appears in encoding (empty = any)
- `role`: COLOR | SHAPE | X_AXIS | Y_AXIS (empty = any)
- `viz_type`: match chart mark type (empty = any)
- `negate`: invert the condition

### Complete Example

```xml
<chart_customization>
Always use concise axis titles.
vega_template:
{
  "config": {
    "background": "#1a1a2e",
    "font": "monospace",
    "title": {"font": "monospace", "fontSize": 16, "color": "#ffffff"},
    "axis": {"labelColor": "#cccccc", "titleColor": "#ffffff", "labelFont": "monospace"},
    "legend": {"labelColor": "#cccccc", "titleColor": "#ffffff", "labelFont": "monospace"}
  }
}
viz_policies:
[
  {"name": "zero_baseline", "rules": [],
   "actions": [{"type": "ensure_axis_range", "params": {"channel": "y", "min": 0}}]},
  {"name": "dollar_revenue",
   "rules": [{"column": "REVENUE", "role": "Y_AXIS"}],
   "actions": [{"type": "ensure_number_format", "params": {"format": "$,.0f", "channel": "y"}}]},
  {"name": "brand_colors",
   "rules": [{"column": "COMPANY", "role": "COLOR"}],
   "actions": [{"type": "ensure_color", "params": {"mapping": {"Snowflake": "#29B5E8", "Competitor": "#FF6B35"}}}]},
  {"name": "force_bar_for_revenue",
   "rules": [{"column": "REVENUE", "role": "Y_AXIS"}, {"viz_type": "bar", "negate": true}],
   "actions": [{"type": "change_viz_type", "params": {"viz_type": "bar"}}]}
]
</chart_customization>
```

---

## Quick Copy-Paste Spec Templates

### Minimal agent with recommended flags

```json
{
  "models": {"orchestration": "auto"},
  "experimental": {
    "EnableAgenticAnalyst": true
  },
  "tools": [...],
  "tool_resources": {...}
}
```

### Full-featured agent with all flags

```json
{
  "models": {"orchestration": "auto"},
  "experimental": {
    "EnableAgenticAnalyst": true,
    "EnableVQRFastPath": true,
    "EnableUnrestrictedChartTool": true
  },
  "orchestration": {
    "budget": {"seconds": 900, "tokens": 400000}
  },
  "instructions": {
    "orchestration": "You are a helpful data analyst.\n<chart_customization>\nPrefer bar charts for comparisons.\nvega_template:\n{\"config\": {\"background\": \"#1a1a2e\"}}\n</chart_customization>"
  },
  "tools": [...],
  "tool_resources": {...}
}
```

---

## Freshness Metadata

<!-- Used by SKILL.md Step 0 to detect staleness. Update after each verification pass. -->

**last_verified:** 2026-05-21

**Sources consulted:**
- Snowflake public docs (ALTER AGENT, CREATE AGENT, Cortex Agents overview)
- Snowflake documentation and release notes
- Internal docs: "Unrestricted Charting for Cortex Agents" (Adrian Stepniak, 2026-04-09)
- Internal docs: "Chart Customization -- Quick Reference" (two versions)
- Existing agents on default connection
- Snowflake public docs: "Customize charts in Snowflake Intelligence" (fetched 2026-04-17)

**Change log:**
- 2026-04-09: Initial inventory. 4 agent-level flags, 4 account-level params, chart customization documented.
- 2026-04-17: (from public docs fetch) Added Font Compatibility section (CSS generic families, config property table, Vega Editor validation tip). Added `_color` transform pattern for exact color mapping + pinned-values-with-palette-fallback alternative. Updated Placement table: `module_custom_instructions.sql_generation` is now the preferred SV field (supersedes legacy `custom_instructions`); added merge precedence note. Added internal-only warning to `viz_policies` section (absent from public docs).
