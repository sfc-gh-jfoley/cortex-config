---
name: cortex-agent-flags
description: Reference for Cortex Agent experimental flags and chart customization options. Load when creating, editing, or optimizing a Cortex Agent to present available experimental configuration options. Uses a search-first workflow to stay current -- checks Snowflake docs before falling back to cached reference. Triggers: experimental flags, agent flags, chart customization, EnableAgenticAnalyst, EnableUnrestrictedChartTool, EnableVQRFastPath, vega_template, viz_policies.
---

# Cortex Agent Experimental Flags

When creating or editing a Cortex Agent, present the user with available experimental flags
and chart customization options. These enhance agent behavior beyond the default configuration.

## When to Use

Load this skill when:
- Creating a new Cortex Agent (after tool selection, before spec generation)
- Editing an existing agent's experimental configuration
- Optimizing an agent and considering feature toggles
- A user asks about experimental options, chart customization, or agent flags

## Workflow

### Step 0: Freshness Check (Search-First)

**CRITICAL:** Experimental flags change frequently. Flags get promoted to GA (and removed
from the `experimental` key), new flags appear, and old flags get renamed or deprecated.
Before presenting any flags to the user, always run the discovery steps below.

**Check the `last_verified` date** at the bottom of `EXPERIMENTAL_FLAGS.md`. If it is
older than 30 days, emit a warning:

```
WARNING: The experimental flags reference was last verified on <DATE>.
Running live discovery to check for updates...
```

**Always run these discovery steps regardless of staleness** (they're fast and catch changes):

#### 0a. Search Snowflake Docs

```bash
cortex search docs "cortex agent experimental specification flags"
```

Scan results for any mention of new experimental keys, deprecated flags, or flags that
have become default behavior (GA). Look for ALTER AGENT and CREATE AGENT doc updates.

#### 0b. Search Snowflake Documentation

Check Snowflake documentation or release notes for the latest experimental flags. Look for:
- New flag announcements
- Flags marked as GA / no longer needed
- Flag renames or behavior changes
- Account-level params that have moved to agent-level

#### 0c. Check Existing Agents on Account

If you know of agents on the current connection that have experimental flags set, DESCRIBE
one to see what flags are currently in use:

```sql
DESCRIBE AGENT <DATABASE>.<SCHEMA>.<KNOWN_AGENT>;
```

Parse the `agent_spec` for the `experimental` block to see what's active.

#### 0d. Merge Findings

Compare discovery results against `EXPERIMENTAL_FLAGS.md`:

- **New flags found?** Add them to the reference doc with `[UNVERIFIED]` tag and present
  to the user with a caveat that they were just discovered.
- **Flags now GA?** Mark them as `[GA - may no longer need experimental flag]` in the doc
  and note this when presenting to the user.
- **Flags deprecated?** Mark as `[DEPRECATED]` and do NOT suggest them.
- **No changes?** Update the `last_verified` date at the bottom of `EXPERIMENTAL_FLAGS.md`.

### Step 1: Read the Reference

**Read** `EXPERIMENTAL_FLAGS.md` in this directory for the cached inventory of flags,
descriptions, prerequisites, and example configurations. Merge with any findings from Step 0.

### Step 2: Assess Applicability

Based on the agent's tools and use case, determine which flags are relevant:

| If the agent has... | Suggest these flags |
|---------------------|---------------------|
| `cortex_analyst_text_to_sql` tools | ~~`EnableAgenticAnalyst`~~ (obsolete since Apr 2026), `EnableVQRFastPath` |
| Any tool that produces charts | `EnableUnrestrictedChartTool` |
| Skills from stages/Git repos | `EnableSkillBasedPromptNoExtendedThinking` |
| Chart-heavy analytics use case | Chart customization (`<chart_customization>` block) |

**Filter out:**
- Flags marked `[DEPRECATED]` -- do not present
- Flags marked `[GA]` -- mention that the flag may no longer be needed
- Flags whose prerequisites are not met (e.g., no skills configured)

### Step 3: Present Options to User

Show the user applicable flags with a brief description and ask which to enable:

```
Your agent uses Cortex Analyst tools. The following experimental flags may improve performance:

1. EnableVQRFastPath
   - Fast path for verified query representations
   - Bypasses full text-to-SQL when a VQR closely matches the question

2. EnableUnrestrictedChartTool
   - Unlocks all Vega-Lite chart types (area, boxplot, waterfall, dual-axis, etc.)
   - Default mode only allows bar, line, arc, point, rect

Would you like to enable any of these? (comma-separated numbers, or 'none')
```

> **Note**: `EnableAgenticAnalyst` is **obsolete since Apr 13, 2026** — direct SQL generation is now the default. Do not present or recommend it.

If any `[UNVERIFIED]` flags were discovered in Step 0, present them separately:

```
Additionally, I found these recently announced flags (not yet verified):

4. [UNVERIFIED] NewFlagName
   - <description from Slack/docs>
   - Discovered from: <source>

These are new and I haven't verified their behavior. Enable at your discretion.
```

### Step 4: Add to Agent Spec

Add the selected flags to the `experimental` key in the agent specification:

```json
{
  "models": {"orchestration": "auto"},
  "experimental": {
    "EnableAgenticAnalyst": true,
    "EnableVQRFastPath": true
  },
  "tools": [...],
  "tool_resources": {...}
}
```

### Step 5: Chart Customization (Optional)

If the user wants chart customization, guide them through adding a `<chart_customization>`
block to their orchestration instructions. See the "Chart Customization" section in
`EXPERIMENTAL_FLAGS.md` for the full reference.

Chart customization goes in `instructions.orchestration`, NOT in `experimental`:

```json
{
  "instructions": {
    "orchestration": "You are a helpful data analyst.\n<chart_customization>\nPrefer bar charts for comparisons.\nvega_template:\n{\"config\": {\"background\": \"#1a1a2e\"}}\n</chart_customization>"
  }
}
```

### Step 6: Update Reference (If Changes Found)

If Step 0 discovered any changes, **ask the user before writing**:

```
I found updates to the experimental flags reference:

  [NEW]        <FlagName> — <one-line description>
  [GA]         <FlagName> — may no longer need the experimental flag
  [DEPRECATED] <FlagName> — should be removed from suggestions
  [CONTENT]    <section> — <summary of doc content change>

Would you like me to update EXPERIMENTAL_FLAGS.md with these changes? (yes / no / show diff)
```

- If **yes**: apply all changes and update `last_verified` to today's date.
- If **no**: proceed without writing; note that the reference is stale for this session.
- If **show diff**: display the exact lines that would change, then ask again.

Do NOT auto-write. The user must confirm before `EXPERIMENTAL_FLAGS.md` is modified.

## Notes

- Experimental flags are per-agent (set in the spec), not per-account
- Flags evolve with preview features -- new ones appear, old ones may become default behavior
- Account-level params (PARAM_*) require deployment access and are not in scope for this skill
- The `<chart_customization>` block is stripped before the LLM sees it -- the JSON/policy content never pollutes the model's context
- The search-first workflow ensures flags are current even if the reference doc is stale
- Always trust live discovery over the cached reference when they conflict
