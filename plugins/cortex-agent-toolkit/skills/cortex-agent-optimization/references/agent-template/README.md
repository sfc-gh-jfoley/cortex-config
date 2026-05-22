# Agent Template Examples

This directory contains minimal example agent instruction files for format validation and testing.

## Purpose

These templates are **developer-facing references** that serve as:
- **Format validation examples** - Shows expected structure for agent instruction files
- **Test fixtures** - Used by test-fixture-example/ (via symlink) to validate the build script pattern
- **Pattern reference** - Demonstrates the markdown structure and JSON schema the skill expects

## Important: Not for End-User Copying

**The skill extracts agent instructions from existing deployed agents** via `DESCRIBE AGENT`. End users do not copy these templates. Instead:
1. User invokes skill with an existing agent
2. Skill runs `DESCRIBE AGENT <FQN>` to get current specification
3. Skill extracts instructions and creates `agent/*.md` files from the live agent
4. User then optimizes those extracted instructions iteratively

These templates exist to validate the format and structure, not as starting points for users.

## Files

### orchestration_instructions.md
Minimal example of routing/orchestration logic. Shows basic tool selection patterns.

### response_instructions.md  
Minimal example of response formatting instructions. Shows how to structure agent output.

### tool_descriptions.md
Example tool descriptions using the `## Tool: <name>` section format. The build script parses these into per-tool description strings.

### spec_base.json
Base agent configuration (models, budget, tool types, tool_resources) without instructions or tool descriptions.

## Usage

### For format validation
When implementing or debugging the build script, use these files to verify correct parsing:
- HTML comments should be stripped
- Top-level headings should be removed
- Tool descriptions should be split on `## Tool: <name>` boundaries
- Base spec should merge cleanly with extracted instructions

### For testing
The `test-fixture-example/agent/` directory symlinks here. Running the build script in test-fixture-example validates that the script correctly processes these minimal templates.

### Referenced by skill
The setup workflow mentions `references/agent-template/` once as a validation reference (setup/SKILL.md line 62), allowing developers to check format expectations.

## Structure Requirements

**orchestration_instructions.md & response_instructions.md:**
- Can include HTML comments (stripped during build)
- Can include a top-level heading (stripped during build)
- Body content becomes the agent instruction text

**tool_descriptions.md:**
```markdown
## Tool: tool_name_1
Description for first tool

## Tool: tool_name_2
Description for second tool
```

**spec_base.json:**
Must include: `name`, `model`, `tools` array (with tool names/types), `tool_resources`, and `budget`.
