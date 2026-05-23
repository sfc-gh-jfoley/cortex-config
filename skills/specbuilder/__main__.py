"""Unified CLI for SpecBuilder.

Usage:
    python3 -m specbuilder <command> [args...]
    python3 -m specbuilder --help

Commands:
    scaffold           Initialize spec directory structure
    generate-module    Generate a spec module from intake
    generate-index     Regenerate manifest.json and README tables
    discover-skills    Identify relevant CoCo skills
    detect-drift       Compare spec vs. implementation state
    diff               Semantic diff between spec versions
    implement          Generate stubs + dispatch plan
    validate-artifacts Validate implementation artifacts (tiered)
    demo-run           Run demo orchestration
    demo-handover      Generate demo handover artifact
    audit              Audit spec completeness and consistency
    test-acceptance    Run acceptance criteria checks
    release            Bump version and create changelog entry
    sign-off           Sign off a module (status → implemented + auto-changelog)
    quality            Assess spec quality (vagueness, testability)
    ci                 CI integration (drift check, promote, PR context)
    summary            Generate POC summary artifact
    ac-coverage        Report acceptance criteria test coverage
    checkpoint         Execution checkpoint for multi-proposal batches
"""

import sys

COMMANDS = {
    "scaffold": "specbuilder.src.scaffold",
    "generate-module": "specbuilder.src.generate_module",
    "generate-index": "specbuilder.src.generate_index",
    "discover-skills": "specbuilder.src.discover_skills",
    "detect-drift": "specbuilder.src.detect_drift",
    "diff": "specbuilder.src.diff",
    "implement": "specbuilder.src.implement",
    "validate-artifacts": "specbuilder.src.validate_artifacts",
    "demo-run": "specbuilder.src.demo_orchestrator",
    "demo-handover": "specbuilder.src.demo_orchestrator",
    "audit": "specbuilder.src.audit",
    "test-acceptance": "specbuilder.src.test_acceptance",
    "release": "specbuilder.src.release",
    "sign-off": "specbuilder.src.release",
    "quality": "specbuilder.src.spec_quality",
    "ci": "specbuilder.src.ci",
    "summary": "specbuilder.src.poc_summary",
    "ac-coverage": "specbuilder.src.ac_coverage",
    "checkpoint": "specbuilder.src.checkpoint",
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("--help", "-h"):
        print("Usage: python3 -m specbuilder <command> [args...]\n")
        print("Commands:")
        for cmd in COMMANDS:
            print(f"  {cmd}")
        print("\nRun 'python3 -m specbuilder <command> --help' for command-specific help.")
        sys.exit(0)

    command = sys.argv[1]

    if command not in COMMANDS:
        print(f"Unknown command: '{command}'", file=sys.stderr)
        print(f"Available commands: {', '.join(COMMANDS.keys())}", file=sys.stderr)
        sys.exit(2)

    # Remove the command name from argv so the submodule sees clean args
    sys.argv = [f"specbuilder {command}"] + sys.argv[2:]

    # Commands that are aliases for subcommands within another module
    _SUBCOMMAND_ALIASES = {
        "sign-off": "sign-off",  # maps to release.main(["sign-off", ...])
    }

    # Modules with a main() function
    _HAS_MAIN = {
        "scaffold",
        "generate-index",
        "diff",
        "implement",
        "validate-artifacts",
        "demo-run",
        "demo-handover",
        "audit",
        "test-acceptance",
        "release",
        "sign-off",
        "quality",
        "ci",
        "summary",
        "ac-coverage",
        "checkpoint",
    }

    module_path = COMMANDS[command]

    if command in _HAS_MAIN:
        module = __import__(module_path, fromlist=["main"])
        if command in _SUBCOMMAND_ALIASES:
            # Inject the subcommand name so argparse sees it
            module.main([_SUBCOMMAND_ALIASES[command]] + sys.argv[1:])
        else:
            module.main()
    else:
        # Module uses if __name__ == "__main__" pattern
        import runpy

        runpy.run_module(module_path, run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
