"""Data profile loader, validator, and SQL hint translator.

Loads YAML data profiles that guide the data-engineering agent
toward semantically meaningful synthetic data generation.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import yaml

# Valid strategy types and their required keys
_STRATEGY_SCHEMA: dict[str, set[str]] = {
    "sequential": set(),  # optional: prefix, start, zero_pad
    "pattern": {"format"},
    "distribution": {"distribution"},
    "time_series": {"start", "end"},
    "enum": {"values"},
    "reference": {"source", "column"},
    "uuid": set(),
}

# Optional keys per strategy
_OPTIONAL_KEYS: dict[str, set[str]] = {
    "sequential": {"prefix", "start", "zero_pad"},
    "pattern": {"domains", "adjectives", "nouns", "suffixes"},
    "distribution": {"mean", "stddev", "min", "max", "round_to"},
    "time_series": {"distribution"},
    "enum": {"weights"},
    "reference": set(),
    "uuid": set(),
}

MAX_ROW_COUNT = 1000


def _profiles_dir() -> Path:
    """Return the directory containing built-in profile YAML files."""
    return Path(__file__).parent


def load_profile(name: str) -> dict[str, Any]:
    """Load a built-in YAML profile by name.

    Args:
        name: Profile name (without .yaml extension).

    Returns:
        Parsed profile dictionary.

    Raises:
        FileNotFoundError: If the profile doesn't exist.
        yaml.YAMLError: If the YAML is malformed.
    """
    profile_path = _profiles_dir() / f"{name}.yaml"
    if not profile_path.exists():
        raise FileNotFoundError(
            f"Profile '{name}' not found. Available: {[p['name'] for p in list_profiles()]}"
        )
    with open(profile_path) as f:
        data: dict[str, Any] = yaml.safe_load(f)
        return data


def list_profiles() -> list[dict[str, str]]:
    """Return name and description for all built-in profiles.

    Returns:
        List of dicts with 'name' and 'description' keys.
    """
    profiles = []
    for path in sorted(_profiles_dir().glob("*.yaml")):
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
            profiles.append({
                "name": data.get("profile", path.stem),
                "description": data.get("description", ""),
            })
        except (yaml.YAMLError, OSError):
            continue
    return profiles


def validate_profile(profile: dict[str, Any]) -> list[str]:
    """Validate profile structure. Returns list of errors (empty = valid).

    Args:
        profile: Parsed profile dictionary.

    Returns:
        List of validation error strings. Empty list means valid.
    """
    errors: list[str] = []

    if not isinstance(profile, dict):
        return ["Profile must be a dictionary"]

    if "profile" not in profile:
        errors.append("Missing required key: 'profile'")
    if "description" not in profile:
        errors.append("Missing required key: 'description'")
    if "tables" not in profile:
        errors.append("Missing required key: 'tables'")
        return errors

    tables = profile["tables"]
    if not isinstance(tables, dict):
        errors.append("'tables' must be a dictionary")
        return errors

    for table_name, table_def in tables.items():
        if not isinstance(table_def, dict):
            errors.append(f"Table '{table_name}' must be a dictionary")
            continue

        row_count = table_def.get("row_count")
        if row_count is None:
            errors.append(f"Table '{table_name}': missing 'row_count'")
        elif not isinstance(row_count, int) or row_count < 1:
            errors.append(f"Table '{table_name}': 'row_count' must be a positive integer")
        elif row_count > MAX_ROW_COUNT:
            errors.append(
                f"Table '{table_name}': 'row_count' exceeds maximum of {MAX_ROW_COUNT}"
            )

        columns = table_def.get("columns")
        if columns is None:
            errors.append(f"Table '{table_name}': missing 'columns'")
            continue
        if not isinstance(columns, dict):
            errors.append(f"Table '{table_name}': 'columns' must be a dictionary")
            continue

        for col_name, col_def in columns.items():
            if not isinstance(col_def, dict):
                errors.append(
                    f"Table '{table_name}'.'{col_name}': column definition must be a dictionary"
                )
                continue

            strategy = col_def.get("type")
            if strategy is None:
                errors.append(f"Table '{table_name}'.'{col_name}': missing 'type'")
                continue
            if strategy not in _STRATEGY_SCHEMA:
                errors.append(
                    f"Table '{table_name}'.'{col_name}': unknown strategy type '{strategy}'. "
                    f"Valid types: {sorted(_STRATEGY_SCHEMA.keys())}"
                )
                continue

            required = _STRATEGY_SCHEMA[strategy]
            for key in required:
                if key not in col_def:
                    errors.append(
                        f"Table '{table_name}'.'{col_name}': strategy '{strategy}' "
                        f"requires key '{key}'"
                    )

            # Validate enum weights sum to ~1.0 if provided
            if strategy == "enum" and "weights" in col_def:
                weights = col_def["weights"]
                values = col_def.get("values", [])
                if len(weights) != len(values):
                    errors.append(
                        f"Table '{table_name}'.'{col_name}': "
                        f"'weights' length ({len(weights)}) must match "
                        f"'values' length ({len(values)})"
                    )
                elif weights and not math.isclose(sum(weights), 1.0, abs_tol=0.01):
                    errors.append(
                        f"Table '{table_name}'.'{col_name}': "
                        f"'weights' must sum to 1.0 (got {sum(weights):.3f})"
                    )

    return errors


def _translate_column(col_name: str, col_def: dict[str, Any]) -> str:
    """Translate a single column definition to a Snowflake SQL expression."""
    strategy = col_def["type"]

    if strategy == "sequential":
        prefix = col_def.get("prefix", "")
        start = col_def.get("start", 1)
        pad = col_def.get("zero_pad", 0)
        if prefix and pad:
            return f"'{prefix}' || LPAD(SEQ4() + {start}, {pad}, '0')"
        elif prefix:
            return f"'{prefix}' || (SEQ4() + {start})::VARCHAR"
        elif pad:
            return f"LPAD(SEQ4() + {start}, {pad}, '0')"
        else:
            return f"SEQ4() + {start}"

    elif strategy == "pattern":
        fmt = col_def["format"]
        # For pattern strategy, provide ARRAY_CONSTRUCT with random selection
        arrays = []
        if "domains" in col_def:
            domains = col_def["domains"]
            arr = "ARRAY_CONSTRUCT(" + ", ".join(f"'{d}'" for d in domains) + ")"
            arrays.append(f"-- domains: {arr}[UNIFORM(0, {len(domains) - 1}, RANDOM())]")
        if "adjectives" in col_def:
            items = col_def["adjectives"]
            arr = "ARRAY_CONSTRUCT(" + ", ".join(f"'{a}'" for a in items) + ")"
            arrays.append(f"-- adjectives: {arr}[UNIFORM(0, {len(items) - 1}, RANDOM())]")
        if "nouns" in col_def:
            items = col_def["nouns"]
            arr = "ARRAY_CONSTRUCT(" + ", ".join(f"'{n}'" for n in items) + ")"
            arrays.append(f"-- nouns: {arr}[UNIFORM(0, {len(items) - 1}, RANDOM())]")
        if "suffixes" in col_def:
            items = col_def["suffixes"]
            arr = "ARRAY_CONSTRUCT(" + ", ".join(f"'{s}'" for s in items) + ")"
            arrays.append(f"-- suffixes: {arr}[UNIFORM(0, {len(items) - 1}, RANDOM())]")

        hint = f"-- Pattern: {fmt}\n"
        if arrays:
            hint += "\n".join(arrays)
        else:
            hint += "-- Use ARRAY_CONSTRUCT with random selection for each placeholder"
        return hint

    elif strategy == "distribution":
        dist = col_def["distribution"]
        mean = col_def.get("mean", 0)
        stddev = col_def.get("stddev", 1)
        min_val = col_def.get("min")
        round_to = col_def.get("round_to", 2)

        if dist == "normal":
            expr = f"ROUND(NORMAL({mean}, {stddev}, RANDOM()), {round_to})"
            if min_val is not None:
                expr = f"GREATEST({min_val}, {expr})"
            return expr
        elif dist == "lognormal":
            expr = f"ROUND(EXP(NORMAL(LN({mean}), {stddev}, RANDOM())), {round_to})"
            if min_val is not None:
                expr = f"GREATEST({min_val}, {expr})"
            max_val = col_def.get("max")
            if max_val is not None:
                expr = f"LEAST({max_val}, {expr})"
            return expr
        else:
            return f"NORMAL({mean}, {stddev}, RANDOM())"

    elif strategy == "time_series":
        start = col_def["start"]
        end = col_def["end"]
        # Calculate seconds between start and end (approximate)
        # The agent should compute exact range; we provide the pattern
        return (
            f"DATEADD('second', UNIFORM(0, "
            f"DATEDIFF('second', '{start}'::TIMESTAMP, '{end}'::TIMESTAMP), "
            f"RANDOM()), '{start}'::TIMESTAMP)"
        )

    elif strategy == "enum":
        values = col_def["values"]
        weights = col_def.get("weights")
        if weights:
            # Generate CASE with cumulative probability
            lines = ["CASE"]
            cum = 0.0
            rand_var = "UNIFORM(0::FLOAT, 1::FLOAT, RANDOM())"
            for i, (val, w) in enumerate(zip(values, weights)):
                cum += w
                if i == len(values) - 1:
                    lines.append(f"    ELSE '{val}'")
                else:
                    lines.append(f"    WHEN {rand_var} < {cum:.4f} THEN '{val}'")
            lines.append("END")
            return "\n".join(lines)
        else:
            arr = "ARRAY_CONSTRUCT(" + ", ".join(f"'{v}'" for v in values) + ")"
            return f"{arr}[UNIFORM(0, {len(values) - 1}, RANDOM())]::VARCHAR"

    elif strategy == "reference":
        source = col_def["source"]
        column = col_def["column"]
        return (
            f"-- FK reference: JOIN to {source}.{column}"
            f" or use SEQ4() % (SELECT COUNT(*) FROM {source})"
        )

    elif strategy == "uuid":
        return "UUID_STRING()"

    return f"-- Unknown strategy: {strategy}"


def translate_to_sql_hints(profile: dict[str, Any]) -> str:
    """Convert a profile to a markdown block of SQL generation guidance.

    Args:
        profile: Validated profile dictionary.

    Returns:
        Markdown-formatted string with SQL hints for each table/column.
    """
    lines: list[str] = []
    lines.append("## Seed Data Generation")
    lines.append("")
    lines.append("Use the following data profile to generate realistic sample data.")
    lines.append("Do NOT use UNIFORM(1, 100, RANDOM()) for columns that have a profile defined.")
    lines.append("")

    tables = profile.get("tables", {})
    for table_name, table_def in tables.items():
        row_count = table_def.get("row_count", 100)
        lines.append(f"### Table: `{table_name}` ({row_count} rows)")
        lines.append("")
        lines.append("| Column | SQL Expression |")
        lines.append("|--------|---------------|")

        columns = table_def.get("columns", {})
        for col_name, col_def in columns.items():
            sql = _translate_column(col_name, col_def)
            # Flatten multiline SQL for table display
            sql_flat = sql.replace("\n", " ").strip()
            lines.append(f"| `{col_name}` | `{sql_flat}` |")

        lines.append("")
        lines.append(f"Generate using: `SELECT ... FROM TABLE(GENERATOR(ROWCOUNT => {row_count}))`")
        lines.append("")

    lines.append("### Translation Rules Reference")
    lines.append("")
    lines.append("| Strategy | Snowflake SQL Pattern |")
    lines.append("|----------|---------------------|")
    lines.append("| sequential | `'PREFIX-' \\|\\| LPAD(SEQ4() + start, pad, '0')` |")
    lines.append("| pattern | `ARRAY_CONSTRUCT(...)[UNIFORM(0, N, RANDOM())]` |")
    lines.append(
        "| distribution.normal | `GREATEST(min, ROUND(NORMAL(mean, stddev, RANDOM()), N))` |"
    )
    lines.append(
        "| distribution.lognormal"
        " | `LEAST(max, GREATEST(min, ROUND(EXP(NORMAL(LN(mean), stddev, RANDOM())), N)))` |"
    )
    lines.append(
        "| time_series"
        " | `DATEADD('second', UNIFORM(0, range_seconds, RANDOM()), 'start'::TIMESTAMP)` |"
    )
    lines.append(
        "| enum (weighted)"
        " | `CASE WHEN UNIFORM(0::FLOAT,1::FLOAT,RANDOM()) < cumulative THEN 'val' ... END` |"
    )
    lines.append("| reference | `JOIN to referenced table` |")
    lines.append("| uuid | `UUID_STRING()` |")
    lines.append("")

    return "\n".join(lines)
