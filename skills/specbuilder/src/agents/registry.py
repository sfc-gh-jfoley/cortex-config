"""Agent registry — maps domain tags to agent launch configurations.

Each entry defines:
- skills: CoCo skills to load for this domain
- artifact_types: file types/patterns this agent handles
- prompt_template: relative path to the agent's prompt template
- flags: optional markers for the workspace manifest
"""

# NOTE: Domain names here are AGENT domains (artifact → implementation agent).
# They are intentionally different from domain-hints.json, which classifies
# user-facing CoCo skills. Do not attempt to unify the two taxonomies.

from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

AGENT_REGISTRY: dict[str, dict] = {
    "data-engineering": {
        "skills": ["sql-author", "dynamic-tables", "snowpipe-streaming"],
        "artifact_types": [
            ".sql",
            "DDL",
            "DML",
            "stored-procedure",
            "task",
            "stream",
            "dynamic-table",
        ],
        "prompt_template": "data-engineering.md",
    },
    "security": {
        "skills": ["data-governance", "network-security", "access-troubleshooter"],
        "artifact_types": ["masking-policy", "row-access-policy", "grant", "role", "network-rule"],
        "prompt_template": "security.md",
    },
    "app-dev": {
        "skills": ["developing-with-streamlit-in-snowflake", "snowpark-python"],
        "artifact_types": [".py", "streamlit", "UDF", "UDTF", "sproc", "notebook"],
        "prompt_template": "app-dev.md",
    },
    "ml": {
        "skills": ["machine-learning", "cortex-ai-function-studio"],
        "artifact_types": ["model", "feature-store", "cortex-function", "ml-pipeline"],
        "prompt_template": "ml.md",
    },
    "fallback": {
        "skills": [],
        "artifact_types": ["*"],
        "prompt_template": "fallback.md",
        "flags": ["unvalidated-by-specialist", "requires-human-review"],
    },
}


def match_domain(artifact_type: str) -> str:
    """Match an artifact type to its owning domain agent.

    Args:
        artifact_type: The type string from the spec Output section
                       (e.g., "DDL", ".sql", "masking-policy", "streamlit")

    Returns:
        Domain name (key in AGENT_REGISTRY). Returns "fallback" if no match.
    """
    artifact_lower = artifact_type.lower().strip()
    for domain, config in AGENT_REGISTRY.items():
        if domain == "fallback":
            continue
        for pattern in config["artifact_types"]:
            if pattern.lower() == artifact_lower:
                return domain
            # Also check if the artifact type contains the pattern
            if pattern.lower() in artifact_lower:
                return domain
    return "fallback"


def get_agent_config(domain: str) -> dict:
    """Get the full agent configuration for a domain.

    Args:
        domain: Domain name (must be a key in AGENT_REGISTRY)

    Returns:
        Dict with skills, artifact_types, prompt_template, and optional flags.
        To resolve the absolute path to the template, compute:
        ``TEMPLATES_DIR / config["prompt_template"]`` using the exported
        ``TEMPLATES_DIR`` constant from this module.

    Raises:
        KeyError: If domain is not in the registry.
    """
    if domain not in AGENT_REGISTRY:
        raise KeyError(f"Unknown domain '{domain}'. Available: {list(AGENT_REGISTRY.keys())}")
    config = AGENT_REGISTRY[domain].copy()
    return config
