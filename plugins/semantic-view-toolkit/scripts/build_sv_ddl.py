#!/usr/bin/env python3
"""Generate CREATE OR REPLACE SEMANTIC VIEW DDL from structured input.

Builds valid semantic view DDL from JSON structure, or applies mutations
to existing DDL parsed from DESCRIBE SEMANTIC VIEW output.

Usage:
  python build_sv_ddl.py --input <structured_json> --output <ddl_file>
  python build_sv_ddl.py --from-describe <describe_output_json> --apply-mutations <mutations_json> --output <ddl_file>

Run with: python3 scripts/build_sv_ddl.py
"""

# =============================================================================
# DEPRECATED — DO NOT USE
# =============================================================================
# This script generates DDL using an outdated grammar that does not match
# current Snowflake semantic view syntax. Specifically:
#
#   - RELATIONSHIPS emitted as "name: table.col -> table.col (JOIN_TYPE)"
#     Correct syntax: "rel_name AS left_alias (fk_col) REFERENCES right_alias"
#
#   - Columns emitted with KIND / DESCRIPTION / EXPR keywords
#     Correct syntax: "table.col AS expr COMMENT = '...' WITH SYNONYMS = (...)"
#
#   - VQRs emitted as VERIFIED_QUERIES with "QUESTION:" colon syntax
#     Correct syntax: AI_VERIFIED_QUERIES ( name AS ( QUESTION '...' SQL '...' ) )
#
#   - No support for AI_SQL_GENERATION, AI_QUESTION_CATEGORIZATION, LABELS, PRIVATE/PUBLIC
#
# This script is orphaned — no skill in the toolkit calls it.
# The GEPA optimizer uses mutate.py (text-level SQL mutations) instead.
#
# This file is retained for reference only. A rewrite aligned to current DDL
# grammar is planned. See skills/sv-ddl/reference/ddl_syntax.md for correct syntax.
# =============================================================================

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def build_ddl(spec: dict[str, Any]) -> str:
    """Build CREATE OR REPLACE SEMANTIC VIEW DDL from structured spec.

    Args:
        spec: Dictionary with keys: sv_name, tables, relationships, facts, dimensions, metrics, verified_queries

    Returns:
        Complete DDL string
    """
    lines = []
    sv_name = spec["sv_name"]
    lines.append(f"CREATE OR REPLACE SEMANTIC VIEW {sv_name}")

    # TABLES clause
    tables = spec.get("tables", [])
    if tables:
        lines.append("  TABLES (")
        for i, table in enumerate(tables):
            comma = "," if i < len(tables) - 1 else ""
            alias = table.get("alias", "")
            fqn = table["fqn"]
            if alias:
                lines.append(f"    {fqn} AS {alias}{comma}")
            else:
                lines.append(f"    {fqn}{comma}")
        lines.append("  )")

    # RELATIONSHIPS clause
    relationships = spec.get("relationships", [])
    if relationships:
        lines.append("  RELATIONSHIPS (")
        for i, rel in enumerate(relationships):
            comma = "," if i < len(relationships) - 1 else ""
            from_table = rel.get("from_table", "")
            from_col = rel.get("from_column", "")
            to_table = rel.get("to_table", "")
            to_col = rel.get("to_column", "")
            join_type = rel.get("join_type", "INNER JOIN")
            name = rel.get("name", f"{from_table}_to_{to_table}")
            lines.append(f"    {name}: {from_table}.{from_col} -> {to_table}.{to_col} ({join_type}){comma}")
        lines.append("  )")

    # FACTS clause
    facts = spec.get("facts", [])
    if facts:
        lines.append("  FACTS (")
        for i, fact_group in enumerate(facts):
            table_ref = fact_group.get("table", "")
            columns = fact_group.get("columns", [])
            lines.append(f"    {table_ref} (")
            for j, col in enumerate(columns):
                col_comma = "," if j < len(columns) - 1 else ""
                col_line = _build_column_def(col)
                lines.append(f"      {col_line}{col_comma}")
            group_comma = "," if i < len(facts) - 1 else ""
            lines.append(f"    ){group_comma}")
        lines.append("  )")

    # DIMENSIONS clause
    dimensions = spec.get("dimensions", [])
    if dimensions:
        lines.append("  DIMENSIONS (")
        for i, dim_group in enumerate(dimensions):
            table_ref = dim_group.get("table", "")
            columns = dim_group.get("columns", [])
            lines.append(f"    {table_ref} (")
            for j, col in enumerate(columns):
                col_comma = "," if j < len(columns) - 1 else ""
                col_line = _build_column_def(col)
                lines.append(f"      {col_line}{col_comma}")
            group_comma = "," if i < len(dimensions) - 1 else ""
            lines.append(f"    ){group_comma}")
        lines.append("  )")

    # METRICS clause
    metrics = spec.get("metrics", [])
    if metrics:
        lines.append("  METRICS (")
        for i, metric in enumerate(metrics):
            comma = "," if i < len(metrics) - 1 else ""
            metric_line = _build_metric_def(metric)
            lines.append(f"    {metric_line}{comma}")
        lines.append("  )")

    # VERIFIED_QUERIES clause (VQRs)
    vqrs = spec.get("verified_queries", [])
    if vqrs:
        lines.append("  VERIFIED_QUERIES (")
        for i, vqr in enumerate(vqrs):
            comma = "," if i < len(vqrs) - 1 else ""
            question = vqr.get("question", "").replace("'", "''")
            sql = vqr.get("sql", "").replace("'", "''")
            name = vqr.get("name", f"vqr_{i+1}")
            lines.append(f"    {name}: (")
            lines.append(f"      QUESTION: '{question}'")
            lines.append(f"      SQL: '{sql}'")
            lines.append(f"    ){comma}")
        lines.append("  )")

    lines.append(";")
    return "\n".join(lines)


def _build_column_def(col: dict) -> str:
    """Build a single column definition line."""
    name = col["name"]
    parts = [name]

    if "data_type" in col:
        parts.append(col["data_type"])

    if "kind" in col:
        parts.append(f"KIND {col['kind']}")

    if "description" in col:
        desc = col["description"].replace("'", "''")
        parts.append(f"DESCRIPTION '{desc}'")

    if "synonyms" in col and col["synonyms"]:
        syn_list = ", ".join(f"'{s}'" for s in col["synonyms"])
        parts.append(f"SYNONYMS ({syn_list})")

    if "expr" in col:
        parts.append(f"EXPR '{col['expr']}'")

    return " ".join(parts)


def _build_metric_def(metric: dict) -> str:
    """Build a single metric definition line."""
    name = metric["name"]
    parts = [name]

    if "expr" in metric:
        expr = metric["expr"].replace("'", "''")
        parts.append(f"EXPR '{expr}'")

    if "default_aggregation" in metric:
        parts.append(f"DEFAULT_AGGREGATION {metric['default_aggregation']}")

    if "description" in metric:
        desc = metric["description"].replace("'", "''")
        parts.append(f"DESCRIPTION '{desc}'")

    if "synonyms" in metric and metric["synonyms"]:
        syn_list = ", ".join(f"'{s}'" for s in metric["synonyms"])
        parts.append(f"SYNONYMS ({syn_list})")

    return " ".join(parts)


def apply_mutations(base_spec: dict, mutations: list[dict]) -> dict:
    """Apply a list of mutations to a base semantic view spec.

    Args:
        base_spec: Base semantic view structure
        mutations: List of mutation operations to apply

    Returns:
        Modified spec with mutations applied
    """
    spec = json.loads(json.dumps(base_spec))  # Deep copy

    for mutation in mutations:
        op = mutation.get("operator")
        target = mutation.get("target", {})

        if op == "add_synonym":
            _apply_add_synonym(spec, target)
        elif op == "improve_description":
            _apply_improve_description(spec, target)
        elif op == "add_filter":
            _apply_add_filter(spec, target)
        elif op == "add_vqr":
            _apply_add_vqr(spec, target)
        elif op == "add_metric":
            _apply_add_metric(spec, target)
        elif op == "refine_metric_expr":
            _apply_refine_metric(spec, target)
        elif op == "add_metric_description":
            _apply_add_metric_description(spec, target)
        elif op == "change_relationship":
            _apply_change_relationship(spec, target)
        elif op == "add_time_dimension":
            _apply_add_time_dimension(spec, target)
        elif op == "remove_column":
            _apply_remove_column(spec, target)
        else:
            print(f"Warning: Unknown operator '{op}', skipping", file=sys.stderr)

    return spec


def _find_column(spec: dict, table: str, column: str, section: str = "facts") -> dict | None:
    """Find a column in the spec by table and column name."""
    groups = spec.get(section, [])
    for group in groups:
        if group.get("table") == table:
            for col in group.get("columns", []):
                if col.get("name") == column:
                    return col
    return None


def _apply_add_synonym(spec: dict, target: dict) -> None:
    table = target.get("table", "")
    column = target.get("column", "")
    synonyms = target.get("synonyms", [])
    for section in ("facts", "dimensions"):
        col = _find_column(spec, table, column, section)
        if col:
            existing = col.get("synonyms", [])
            col["synonyms"] = list(set(existing + synonyms))
            break


def _apply_improve_description(spec: dict, target: dict) -> None:
    table = target.get("table", "")
    column = target.get("column", "")
    description = target.get("description", "")
    for section in ("facts", "dimensions"):
        col = _find_column(spec, table, column, section)
        if col:
            col["description"] = description
            break


def _apply_add_filter(spec: dict, target: dict) -> None:
    table = target.get("table", "")
    column = target.get("column", "")
    filter_def = target.get("filter", {})
    for section in ("facts", "dimensions"):
        col = _find_column(spec, table, column, section)
        if col:
            if "filters" not in col:
                col["filters"] = []
            col["filters"].append(filter_def)
            break


def _apply_add_vqr(spec: dict, target: dict) -> None:
    if "verified_queries" not in spec:
        spec["verified_queries"] = []
    spec["verified_queries"].append({
        "name": target.get("name", f"vqr_{len(spec['verified_queries'])+1}"),
        "question": target.get("question", ""),
        "sql": target.get("sql", ""),
    })


def _apply_add_metric(spec: dict, target: dict) -> None:
    if "metrics" not in spec:
        spec["metrics"] = []
    spec["metrics"].append({
        "name": target.get("name", ""),
        "expr": target.get("expr", ""),
        "default_aggregation": target.get("default_aggregation", "SUM"),
        "description": target.get("description", ""),
        "synonyms": target.get("synonyms", []),
    })


def _apply_refine_metric(spec: dict, target: dict) -> None:
    metric_name = target.get("name", "")
    new_expr = target.get("expr", "")
    for metric in spec.get("metrics", []):
        if metric.get("name") == metric_name:
            if new_expr:
                metric["expr"] = new_expr
            if "default_aggregation" in target:
                metric["default_aggregation"] = target["default_aggregation"]
            break


def _apply_add_metric_description(spec: dict, target: dict) -> None:
    metric_name = target.get("name", "")
    for metric in spec.get("metrics", []):
        if metric.get("name") == metric_name:
            if "description" in target:
                metric["description"] = target["description"]
            if "synonyms" in target:
                existing = metric.get("synonyms", [])
                metric["synonyms"] = list(set(existing + target["synonyms"]))
            break


def _apply_change_relationship(spec: dict, target: dict) -> None:
    rel_name = target.get("name", "")
    for rel in spec.get("relationships", []):
        if rel.get("name") == rel_name:
            if "join_type" in target:
                rel["join_type"] = target["join_type"]
            if "from_column" in target:
                rel["from_column"] = target["from_column"]
            if "to_column" in target:
                rel["to_column"] = target["to_column"]
            break
    else:
        # Add new relationship if not found
        if "from_table" in target and "to_table" in target:
            if "relationships" not in spec:
                spec["relationships"] = []
            spec["relationships"].append(target)


def _apply_add_time_dimension(spec: dict, target: dict) -> None:
    table = target.get("table", "")
    column = target.get("column", "")
    for section in ("facts", "dimensions"):
        col = _find_column(spec, table, column, section)
        if col:
            col["kind"] = "time_dimension"
            break


def _apply_remove_column(spec: dict, target: dict) -> None:
    table = target.get("table", "")
    column = target.get("column", "")
    for section in ("facts", "dimensions"):
        groups = spec.get(section, [])
        for group in groups:
            if group.get("table") == table:
                group["columns"] = [
                    c for c in group.get("columns", []) if c.get("name") != column
                ]
                break


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build semantic view DDL from structured input"
    )
    parser.add_argument("--input", help="Path to structured JSON input")
    parser.add_argument("--from-describe", help="Path to DESCRIBE SEMANTIC VIEW output JSON")
    parser.add_argument("--apply-mutations", help="Path to mutations JSON")
    parser.add_argument("--output", help="Output DDL file path (default: stdout)")

    args = parser.parse_args()

    if not args.input and not args.from_describe:
        parser.error("Must provide either --input or --from-describe")

    if args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"Error: Input file not found: {args.input}", file=sys.stderr)
            sys.exit(1)
        with open(input_path) as f:
            spec = json.load(f)
    elif args.from_describe:
        describe_path = Path(args.from_describe)
        if not describe_path.exists():
            print(f"Error: Describe file not found: {args.from_describe}", file=sys.stderr)
            sys.exit(1)
        with open(describe_path) as f:
            spec = json.load(f)

        # Apply mutations if provided
        if args.apply_mutations:
            mutations_path = Path(args.apply_mutations)
            if not mutations_path.exists():
                print(f"Error: Mutations file not found: {args.apply_mutations}", file=sys.stderr)
                sys.exit(1)
            with open(mutations_path) as f:
                mutations = json.load(f)
            spec = apply_mutations(spec, mutations)

    ddl = build_ddl(spec)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(ddl)
        print(json.dumps({"output": str(output_path), "lines": ddl.count("\n") + 1}))
    else:
        print(ddl)


if __name__ == "__main__":
    main()
