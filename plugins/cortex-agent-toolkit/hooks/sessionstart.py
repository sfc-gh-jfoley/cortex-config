#!/usr/bin/env python3
"""
SessionStart hook for cortex-agent-toolkit.

Fires at session start to:
1. Check prerequisites (uv, snow CLI) and warn if missing
2. Inject operating rules that establish this toolkit's priority over the
   bundled `cortex-agent` skill
"""
import sys
import json
import shutil
import os

PLUGIN_ROOT = os.environ.get("CORTEX_PLUGIN_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RULES = """\
# cortex-agent-toolkit — Active

This plugin provides the full Cortex Agent lifecycle toolkit. It takes priority \
over the bundled `cortex-agent` skill for all agent work.

## Override Directive

When the user requests agent-related work (create, evaluate, optimize, flag-test, \
query, version, or inspect a Cortex Agent), invoke `$cortex-agent-toolkit` — \
do NOT use the bundled `cortex-agent` skill. The bundled skill lacks the full \
lifecycle pipeline (eval → flags → optimize → GEPA).

## Available Sub-Skills

| Trigger | Skill |
|---|---|
| create/build agent, agent DDL | cortex-agent-ddl |
| evaluate, baseline, accuracy | agent-evaluation |
| flags, model sweep, A/B test | agent-flag-tester |
| optimize, improve, iterate | cortex-agent-optimization |
| GEPA, evolutionary, plateau | agent-gepa-optimizer |
| query, invoke, DATA_AGENT_RUN | query-cortex-agent |
| flags reference | cortex-agent-flags |
| version, alias, rollback, CI/CD | agent-versioning |

## Key Rule

Every `cortex_analyst_text_to_sql` tool MUST have `execution_environment.warehouse` \
in its `tool_resources` — without it, CREATE AGENT succeeds but DATA_AGENT_RUN \
fails with error 399504.

## Full Instructions

Read: {plugin_root}/SKILL.md
""".format(plugin_root=PLUGIN_ROOT)


def check_prerequisites():
    issues = []
    if not shutil.which("snow"):
        issues.append("- `snow` CLI not on PATH (needed for DESCRIBE/CREATE/ALTER AGENT)")
    if not shutil.which("uv"):
        issues.append("- `uv` not on PATH (needed for evaluation and GEPA optimization scripts)")
    return issues


def main():
    try:
        json.load(sys.stdin)
    except Exception:
        # Graceful fallback on empty/malformed stdin
        print(json.dumps({"continue": True}))
        return

    issues = check_prerequisites()
    context = RULES

    if issues:
        warning = (
            "## Setup Incomplete\n\n"
            "The following prerequisites are missing:\n"
            + "\n".join(issues)
            + "\n\nRun the bundled setup guide: "
            + PLUGIN_ROOT + "/SETUP.md\n\n---\n\n"
        )
        context = warning + context

    print(json.dumps({"additionalContext": context}))


if __name__ == "__main__":
    main()
