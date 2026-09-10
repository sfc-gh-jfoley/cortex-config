#!/usr/bin/env python3
"""
SessionStart hook for semantic-view-toolkit.

Fires at session start to:
1. Check prerequisites (uv) and warn if missing
2. Inject operating rules that establish this toolkit's priority over the
   bundled `semantic-view` skill
"""
import sys
import json
import shutil
import os

PLUGIN_ROOT = os.environ.get("CORTEX_PLUGIN_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RULES = """\
# semantic-view-toolkit — Active

This plugin provides the full Semantic View lifecycle toolkit. It takes priority \
over the bundled `semantic-view` skill for all SV work.

## Override Directive

When the user requests semantic view work (discover, create, audit, evaluate, \
optimize, compose, watch, or generate VQRs), invoke `$semantic-view-toolkit` — \
do NOT use the bundled `semantic-view` skill.

**Exceptions — stay on the bundled skill:**
- YAML/FastGen local-file path (requires BASE_WORKING_DIR, Python/uv)
- Tableau .twb/.twbx/.tds/.tdsx or Power BI .pbit/.pbix import

## Available Sub-Skills

| Trigger | Skill |
|---|---|
| discover, what tables, recommend groupings | sv-discovery |
| create SV, DDL, I know my tables | sv-ddl |
| audit, what's missing, coverage | sv-audit |
| evaluate, accuracy, sql correctness | sv-evaluation |
| optimize, improve, iterate | sv-optimization |
| GEPA, evolutionary, plateau | sv-gepa-optimizer |
| compose, nested SV, multi-domain | sv-composer |
| watch, drift, monitor | sv-watch |
| VQR, verified queries, generate questions | vqr-generator |

## Full Instructions

Read: {plugin_root}/SKILL.md
""".format(plugin_root=PLUGIN_ROOT)


def check_prerequisites():
    issues = []
    if not shutil.which("uv"):
        issues.append("- `uv` not on PATH (needed for optimization and GEPA scripts)")
    return issues


def main():
    try:
        json.load(sys.stdin)
    except Exception:
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
