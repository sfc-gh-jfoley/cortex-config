"""
Semantic View DDL Validator

Validates Snowflake CREATE SEMANTIC VIEW DDL strings against 18 self-check rules
derived from the semantic-view-ddl Phase 5 specification.

Stdlib-only — no external dependencies required.

Usage:
    python sv_validator.py <file.sql>

Programmatic:
    from sv_validator import validate_ddl, validate_file, CheckResult
    results = validate_ddl(ddl_string)
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

__all__ = ["validate_ddl", "validate_file", "CheckResult"]


@dataclass
class CheckResult:
    name: str
    passed: bool
    severity: str  # "error" | "warning"
    message: str


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _find_balanced_parens(text: str, start: int) -> str:
    """Return the content between balanced parentheses starting at `start`.
    `start` should point to the opening '('."""
    depth = 0
    i = start
    while i < len(text):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i]
        i += 1
    return text[start + 1 :]


def _find_clause(ddl: str, clause: str) -> Optional[str]:
    """Find a top-level clause (TABLES, RELATIONSHIPS, etc.) and return its
    parenthesised body. Returns None if the clause is absent."""
    # Match the clause keyword followed by optional whitespace and '('
    pattern = re.compile(rf"\b{clause}\s*\(", re.IGNORECASE)
    m = pattern.search(ddl)
    if not m:
        return None
    return _find_balanced_parens(ddl, m.end() - 1)


def _clause_positions(ddl: str) -> list[tuple[str, int]]:
    """Return (clause_name, start_position) for each top-level clause found."""
    clauses = ["TABLES", "RELATIONSHIPS", "FACTS", "DIMENSIONS", "METRICS"]
    found = []
    for c in clauses:
        pattern = re.compile(rf"\b{c}\s*\(", re.IGNORECASE)
        m = pattern.search(ddl)
        if m:
            found.append((c.upper(), m.start()))
    found.sort(key=lambda x: x[1])
    return found


def _parse_tables(tables_body: str) -> list[dict]:
    """Parse the TABLES clause body into a list of table dicts.
    Each dict: {alias, physical, pk_cols, unique_cols, comment}"""
    tables = []
    # Split on top-level commas (not inside parens)
    entries = _split_top_level(tables_body, ",")
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        t = _parse_single_table(entry)
        if t:
            tables.append(t)
    return tables


def _split_top_level(text: str, delimiter: str) -> list[str]:
    """Split text by delimiter, but only at depth 0 (not inside parens)."""
    parts = []
    depth = 0
    current = []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == delimiter and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current))
    return parts


def _parse_single_table(entry: str) -> Optional[dict]:
    """Parse a single table entry like:
    orders AS MY_DB.PUBLIC.ORDERS PRIMARY KEY (ORDER_ID) COMMENT = 'desc'
    """
    m = re.match(r"(\w+)\s+AS\s+([\w.\"]+)", entry, re.IGNORECASE)
    if not m:
        return None
    alias = m.group(1).strip()
    physical = m.group(2).strip()

    pk_cols = []
    pk_match = re.search(r"PRIMARY\s+KEY\s*\(([^)]*)\)", entry, re.IGNORECASE)
    if pk_match:
        pk_cols = [c.strip().strip('"') for c in pk_match.group(1).split(",") if c.strip()]

    unique_cols = []
    uq_match = re.search(r"UNIQUE\s*\(([^)]*)\)", entry, re.IGNORECASE)
    if uq_match:
        unique_cols = [c.strip().strip('"') for c in uq_match.group(1).split(",") if c.strip()]

    comment = ""
    cm = re.search(r"COMMENT\s*=\s*'((?:[^']|'')*)'", entry, re.IGNORECASE)
    if cm:
        comment = cm.group(1).replace("''", "'")

    return {
        "alias": alias,
        "physical": physical,
        "pk_cols": pk_cols,
        "unique_cols": unique_cols,
        "comment": comment,
    }


def _parse_relationships(rel_body: str) -> list[dict]:
    """Parse RELATIONSHIPS body. Each relationship:
    {name, left_table, left_cols, right_table, is_asof, asof_col}"""
    rels = []
    entries = _split_top_level(rel_body, ",")
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        r = _parse_single_relationship(entry)
        if r:
            rels.append(r)
    return rels


def _parse_single_relationship(entry: str) -> Optional[dict]:
    """Parse named or unnamed relationships:
    Named:   name AS left_table (COL[, COL]) REFERENCES right_table [ASOF ...]
    Unnamed: left_table (COL[, COL]) REFERENCES right_table [ASOF ...]
    """
    # Try named format first: name AS left_table(COL) REFERENCES right_table
    m = re.match(
        r"(\w+)\s+AS\s+(\w+)\s*\(([^)]*)\)\s*REFERENCES\s+(\w+)",
        entry,
        re.IGNORECASE,
    )
    if m:
        name = m.group(1)
        left_table = m.group(2)
        left_cols = [c.strip().strip('"') for c in m.group(3).split(",") if c.strip()]
        right_table = m.group(4)
    else:
        # Try unnamed format: left_table(COL) REFERENCES right_table
        m = re.match(
            r"(\w+)\s*\(([^)]*)\)\s*REFERENCES\s+(\w+)",
            entry,
            re.IGNORECASE,
        )
        if not m:
            return None
        left_table = m.group(1)
        left_cols = [c.strip().strip('"') for c in m.group(2).split(",") if c.strip()]
        right_table = m.group(3)
        name = f"_auto_{left_table}_{right_table}"

    is_asof = bool(re.search(r"\bASOF\b", entry, re.IGNORECASE))
    asof_col = None
    asof_m = re.search(r"ASOF\s*\(\s*(\w+)", entry, re.IGNORECASE)
    if asof_m:
        asof_col = asof_m.group(1)

    return {
        "name": name,
        "left_table": left_table,
        "left_cols": left_cols,
        "right_table": right_table,
        "is_asof": is_asof,
        "asof_col": asof_col,
    }


def _parse_column_entries(body: str) -> list[dict]:
    """Parse FACTS/DIMENSIONS/METRICS body into column entries.
    Each: {table, col_name, expr, labels, synonyms, comment, using, full_entry}"""
    cols = []
    entries = _split_top_level(body, ",")
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        c = _parse_single_column(entry)
        if c:
            cols.append(c)
    return cols


def _parse_single_column(entry: str) -> Optional[dict]:
    """Parse: table.col_name AS expr [COMMENT = '...'] [LABELS = (...)] [WITH SYNONYMS (...)] [USING ...]"""
    # Match table.col_name AS <rest>
    m = re.match(r"(\w+)\.(\w+)\s+AS\s+", entry, re.IGNORECASE)
    if not m:
        return None
    table = m.group(1)
    col_name = m.group(2)

    # Extract expression: everything after AS until COMMENT, LABELS, WITH SYNONYMS, or USING
    rest = entry[m.end():]
    # Find where the expression ends
    expr_end_pattern = re.compile(
        r"\b(COMMENT\s*=|LABELS\s*=|WITH\s+SYNONYMS|USING\b|NON\s+ADDITIVE)", re.IGNORECASE
    )
    expr_match = expr_end_pattern.search(rest)
    if expr_match:
        expr = rest[: expr_match.start()].strip().rstrip(",")
    else:
        expr = rest.strip().rstrip(",")

    labels = []
    lab_m = re.search(r"LABELS\s*=\s*\(([^)]*)\)", entry, re.IGNORECASE)
    if lab_m:
        labels = [l.strip() for l in lab_m.group(1).split(",") if l.strip()]

    synonyms = []
    syn_m = re.search(r"WITH\s+SYNONYMS\s*=?\s*\(([^)]*)\)", entry, re.IGNORECASE)
    if syn_m:
        synonyms = [s.strip().strip("'\"") for s in syn_m.group(1).split(",") if s.strip()]

    comment = ""
    cm = re.search(r"COMMENT\s*=\s*'((?:[^']|'')*)'", entry, re.IGNORECASE)
    if cm:
        comment = cm.group(1)

    using = None
    using_m = re.search(r"USING\s+(\w+)", entry, re.IGNORECASE)
    if using_m:
        using = using_m.group(1)

    non_additive = bool(re.search(r"NON\s+ADDITIVE\s+BY", entry, re.IGNORECASE))

    return {
        "table": table,
        "col_name": col_name,
        "expr": expr,
        "labels": labels,
        "synonyms": synonyms,
        "comment": comment,
        "using": using,
        "non_additive": non_additive,
        "full_entry": entry,
    }


# ---------------------------------------------------------------------------
# Parsed DDL context
# ---------------------------------------------------------------------------

@dataclass
class _DDLContext:
    raw: str = ""
    tables: list = field(default_factory=list)
    relationships: list = field(default_factory=list)
    facts: list = field(default_factory=list)
    dimensions: list = field(default_factory=list)
    metrics: list = field(default_factory=list)
    tables_body: Optional[str] = None
    relationships_body: Optional[str] = None
    facts_body: Optional[str] = None
    dimensions_body: Optional[str] = None
    metrics_body: Optional[str] = None
    clause_order: list = field(default_factory=list)


def _build_context(ddl: str) -> _DDLContext:
    ctx = _DDLContext(raw=ddl)
    ctx.clause_order = _clause_positions(ddl)

    ctx.tables_body = _find_clause(ddl, "TABLES")
    ctx.relationships_body = _find_clause(ddl, "RELATIONSHIPS")
    ctx.facts_body = _find_clause(ddl, "FACTS")
    ctx.dimensions_body = _find_clause(ddl, "DIMENSIONS")
    ctx.metrics_body = _find_clause(ddl, "METRICS")

    if ctx.tables_body is not None:
        ctx.tables = _parse_tables(ctx.tables_body)
    if ctx.relationships_body is not None:
        ctx.relationships = _parse_relationships(ctx.relationships_body)
    if ctx.facts_body is not None:
        ctx.facts = _parse_column_entries(ctx.facts_body)
    if ctx.dimensions_body is not None:
        ctx.dimensions = _parse_column_entries(ctx.dimensions_body)
    if ctx.metrics_body is not None:
        ctx.metrics = _parse_column_entries(ctx.metrics_body)

    return ctx


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_clause_order(ctx: _DDLContext) -> CheckResult:
    """1. Clause order: TABLES → RELATIONSHIPS → FACTS → DIMENSIONS → METRICS."""
    expected = ["TABLES", "RELATIONSHIPS", "FACTS", "DIMENSIONS", "METRICS"]
    found_names = [name for name, _ in ctx.clause_order]
    # Filter expected to only those present
    expected_filtered = [c for c in expected if c in found_names]
    if found_names == expected_filtered:
        return CheckResult("clause_order", True, "error", "Clause order is correct.")
    return CheckResult(
        "clause_order",
        False,
        "error",
        f"Clause order violation. Found: {' → '.join(found_names)}, "
        f"expected: {' → '.join(expected_filtered)}.",
    )


def _check_alias_matches_physical(ctx: _DDLContext) -> CheckResult:
    """2. For direct column refs, alias must match physical column name."""
    issues = []
    for section_name, entries in [("FACTS", ctx.facts), ("DIMENSIONS", ctx.dimensions)]:
        for col in entries:
            expr = col["expr"].strip().strip('"')
            # A direct column reference is a bare identifier (no operators, parens, functions)
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", expr):
                if expr.upper() != col["col_name"].upper():
                    issues.append(
                        f"{section_name}: {col['table']}.{col['col_name']} AS {expr} "
                        f"(expected AS {col['col_name']})"
                    )
    if issues:
        return CheckResult(
            "alias_matches_physical", False, "error",
            "Alias/physical mismatch: " + "; ".join(issues),
        )
    return CheckResult("alias_matches_physical", True, "error", "All aliases match physical columns.")


def _check_no_duplicate_columns(ctx: _DDLContext) -> CheckResult:
    """3. No duplicate column names within FACTS or within DIMENSIONS."""
    issues = []
    for section_name, entries in [("FACTS", ctx.facts), ("DIMENSIONS", ctx.dimensions)]:
        names = [col["col_name"].upper() for col in entries]
        dupes = [name for name, count in Counter(names).items() if count > 1]
        if dupes:
            issues.append(f"{section_name} duplicates: {', '.join(dupes)}")
    if issues:
        return CheckResult("no_duplicate_columns", False, "error", "; ".join(issues))
    return CheckResult("no_duplicate_columns", True, "error", "No duplicate columns found.")


def _check_pk_on_referenced_tables(ctx: _DDLContext) -> CheckResult:
    """4. Every table on RHS of REFERENCES must have PK or UNIQUE defined."""
    alias_to_table = {t["alias"].upper(): t for t in ctx.tables}
    issues = []
    for rel in ctx.relationships:
        rt = rel["right_table"].upper()
        tbl = alias_to_table.get(rt)
        if tbl and not tbl["pk_cols"] and not tbl["unique_cols"]:
            issues.append(f"Table '{rel['right_table']}' referenced by '{rel['name']}' has no PK/UNIQUE.")
    if issues:
        return CheckResult("pk_on_referenced_tables", False, "error", "; ".join(issues))
    return CheckResult("pk_on_referenced_tables", True, "error", "All referenced tables have PK/UNIQUE.")


def _check_using_clause_for_multi_rel(ctx: _DDLContext) -> CheckResult:
    """5. If two+ relationships connect the same table pair, metrics on those
    tables must have a USING clause."""
    pair_counts: dict[tuple, int] = defaultdict(int)
    for rel in ctx.relationships:
        pair = tuple(sorted([rel["left_table"].upper(), rel["right_table"].upper()]))
        pair_counts[pair] += 1

    multi_pairs = {pair for pair, cnt in pair_counts.items() if cnt >= 2}
    if not multi_pairs:
        return CheckResult(
            "using_clause_for_multi_rel", True, "error",
            "No multi-relationship table pairs found.",
        )

    affected_tables = set()
    for pair in multi_pairs:
        affected_tables.update(pair)

    issues = []
    for metric in ctx.metrics:
        if metric["table"].upper() in affected_tables and not metric["using"]:
            issues.append(f"Metric {metric['table']}.{metric['col_name']} lacks USING clause.")

    if issues:
        return CheckResult("using_clause_for_multi_rel", False, "error", "; ".join(issues))
    return CheckResult("using_clause_for_multi_rel", True, "error", "USING clauses present where needed.")


def _check_no_empty_relationships(ctx: _DDLContext) -> CheckResult:
    """6. If RELATIONSHIPS block exists, it must contain at least one definition."""
    if ctx.relationships_body is not None and not ctx.relationships:
        return CheckResult(
            "no_empty_relationships", False, "error",
            "RELATIONSHIPS block is empty — remove it or add relationships.",
        )
    return CheckResult("no_empty_relationships", True, "error", "RELATIONSHIPS block is non-empty (or absent).")


def _check_fully_qualified_tables(ctx: _DDLContext) -> CheckResult:
    """7. Every physical table reference must be DB.SCHEMA.TABLE (3 parts)."""
    issues = []
    for t in ctx.tables:
        physical = t["physical"].replace('"', "")
        parts = physical.split(".")
        if len(parts) != 3:
            issues.append(f"Table '{t['alias']}' physical ref '{t['physical']}' is not fully qualified.")
    if issues:
        return CheckResult("fully_qualified_tables", False, "error", "; ".join(issues))
    return CheckResult("fully_qualified_tables", True, "error", "All table references are fully qualified.")


def _check_string_literal_escaping(ctx: _DDLContext) -> CheckResult:
    """8. In FACTS/METRICS AS expressions, no double-single-quote escaping."""
    issues = []
    for section_name, entries in [("FACTS", ctx.facts), ("METRICS", ctx.metrics)]:
        for col in entries:
            if "''" in col["expr"]:
                issues.append(f"{section_name}: {col['table']}.{col['col_name']} expr contains ''.")
    if issues:
        return CheckResult(
            "string_literal_escaping", False, "warning",
            "Possible double-quote escaping in expressions: " + "; ".join(issues),
        )
    return CheckResult("string_literal_escaping", True, "warning", "No string literal escaping issues.")


def _check_non_standard_column_quoting(ctx: _DDLContext) -> CheckResult:
    """9. Non-standard column names must be double-quoted."""
    standard_re = re.compile(r"^[A-Z][A-Z0-9_]*$")
    issues = []
    for section_name, entries in [
        ("FACTS", ctx.facts), ("DIMENSIONS", ctx.dimensions), ("METRICS", ctx.metrics)
    ]:
        for col in entries:
            name = col["col_name"]
            # If already quoted in the raw entry, skip
            if f'"{name}"' in col["full_entry"]:
                continue
            if not standard_re.match(name):
                issues.append(f"{section_name}: {col['table']}.{name} needs quoting.")
    if issues:
        return CheckResult("non_standard_column_quoting", False, "warning", "; ".join(issues))
    return CheckResult(
        "non_standard_column_quoting", True, "warning",
        "All non-standard column names are properly quoted.",
    )


def _check_filter_label_boolean(ctx: _DDLContext) -> CheckResult:
    """10. Columns with LABELS = ( FILTER ) should have boolean-like expressions."""
    bool_patterns = re.compile(
        r"(^IS_|^HAS_|[<>=!]=|<>|\bBETWEEN\b|\bIN\s*\(|\bLIKE\b|\bIS\s+NULL|\bIS\s+NOT\s+NULL|"
        r"\bNOT\b|\bAND\b|\bOR\b|\bBOOLEAN\b|\bTRUE\b|\bFALSE\b)",
        re.IGNORECASE,
    )
    issues = []
    for section_name, entries in [
        ("FACTS", ctx.facts), ("DIMENSIONS", ctx.dimensions), ("METRICS", ctx.metrics)
    ]:
        for col in entries:
            labels_upper = [l.upper() for l in col["labels"]]
            if "FILTER" in labels_upper:
                col_identifier = f"{col['table']}.{col['col_name']}"
                # Check col name and expression for boolean hints
                if not bool_patterns.search(col["col_name"]) and not bool_patterns.search(col["expr"]):
                    issues.append(f"{section_name}: {col_identifier} has FILTER label but expression "
                                  f"doesn't look boolean.")
    if issues:
        return CheckResult("filter_label_boolean", False, "warning", "; ".join(issues))
    return CheckResult("filter_label_boolean", True, "warning", "All FILTER-labeled columns look boolean.")


def _check_window_metric_inner_ref(ctx: _DDLContext) -> CheckResult:
    """11. Window function metrics must reference a defined metric/fact."""
    # Collect known metric/fact names per table
    known: dict[str, set[str]] = defaultdict(set)
    for col in ctx.facts:
        known[col["table"].upper()].add(col["col_name"].upper())
    for col in ctx.metrics:
        known[col["table"].upper()].add(col["col_name"].upper())

    issues = []
    for metric in ctx.metrics:
        if re.search(r"\bOVER\s*\(", metric["expr"], re.IGNORECASE):
            # Extract inner references — look for identifiers before OVER
            inner_refs = re.findall(r"\b(\w+)\s*\)", metric["expr"].split("OVER")[0])
            # Also try extracting function arguments like SUM(metric_name)
            func_args = re.findall(r"\w+\s*\(\s*(\w+)", metric["expr"])
            all_refs = set(r.upper() for r in inner_refs + func_args)
            table_known = known.get(metric["table"].upper(), set())
            for ref in all_refs:
                if ref.upper() not in table_known and ref.upper() not in (
                    "SUM", "COUNT", "AVG", "MIN", "MAX", "ROW_NUMBER", "RANK",
                    "DENSE_RANK", "LAG", "LEAD", "FIRST_VALUE", "LAST_VALUE",
                    "ROWS", "RANGE", "UNBOUNDED", "PRECEDING", "FOLLOWING",
                    "CURRENT", "ROW", "PARTITION", "ORDER", "BY", "ASC", "DESC",
                ):
                    issues.append(
                        f"Metric {metric['table']}.{metric['col_name']}: "
                        f"inner reference '{ref}' not found as a defined fact/metric."
                    )
    if issues:
        return CheckResult("window_metric_inner_ref", False, "warning", "; ".join(issues))
    return CheckResult(
        "window_metric_inner_ref", True, "warning",
        "All window metric inner references are valid.",
    )


def _check_asof_column_type_hint(ctx: _DDLContext) -> CheckResult:
    """12. ASOF relationship columns should contain date/time/timestamp keywords."""
    date_hints = re.compile(r"(DATE|TIME|TIMESTAMP|DT|_AT$|_ON$|CREATED|UPDATED|MODIFIED)", re.IGNORECASE)
    issues = []
    for rel in ctx.relationships:
        if rel["is_asof"] and rel["asof_col"]:
            if not date_hints.search(rel["asof_col"]):
                issues.append(
                    f"Relationship '{rel['name']}': ASOF column '{rel['asof_col']}' "
                    f"doesn't look like a date/time column."
                )
    if issues:
        return CheckResult("asof_column_type_hint", False, "warning", "; ".join(issues))
    return CheckResult("asof_column_type_hint", True, "warning", "All ASOF columns look like date/time.")


def _check_orphan_detection(ctx: _DDLContext) -> CheckResult:
    """13. Every table in TABLES must appear in at least one RELATIONSHIP."""
    if len(ctx.tables) <= 1:
        return CheckResult(
            "orphan_detection", True, "warning",
            "Single table — no relationships needed.",
        )
    referenced = set()
    for rel in ctx.relationships:
        referenced.add(rel["left_table"].upper())
        referenced.add(rel["right_table"].upper())

    orphans = []
    for t in ctx.tables:
        if t["alias"].upper() not in referenced:
            orphans.append(t["alias"])

    if orphans:
        return CheckResult(
            "orphan_detection", False, "warning",
            f"Orphan tables (not in any relationship): {', '.join(orphans)}.",
        )
    return CheckResult("orphan_detection", True, "warning", "All tables are connected via relationships.")


def _check_fan_trap_warning(ctx: _DDLContext) -> CheckResult:
    """14. Warn about potential fan traps (multi-hop metric grouping)."""
    # Build adjacency from relationships
    adj: dict[str, set[str]] = defaultdict(set)
    for rel in ctx.relationships:
        lt = rel["left_table"].upper()
        rt = rel["right_table"].upper()
        adj[lt].add(rt)
        adj[rt].add(lt)

    # For each metric, check if its table connects to other tables only through intermediaries
    metric_tables = set(m["table"].upper() for m in ctx.metrics)
    dim_tables = set(d["table"].upper() for d in ctx.dimensions)

    issues = []
    for mt in metric_tables:
        direct_neighbors = adj.get(mt, set())
        for dt in dim_tables:
            if dt == mt:
                continue
            if dt not in direct_neighbors:
                # Check if reachable through 2 hops
                for neighbor in direct_neighbors:
                    if dt in adj.get(neighbor, set()):
                        issues.append(
                            f"Potential fan trap: metrics on '{mt}' grouped by dimensions "
                            f"on '{dt}' via bridge table '{neighbor}'."
                        )
                        break

    if issues:
        return CheckResult("fan_trap_warning", False, "warning", "; ".join(issues))
    return CheckResult("fan_trap_warning", True, "warning", "No fan trap patterns detected.")


def _check_chasm_trap_warning(ctx: _DDLContext) -> CheckResult:
    """18. Warn about potential chasm traps (two fact tables converging on a shared dimension)."""
    adj: dict[str, set[str]] = defaultdict(set)
    for rel in ctx.relationships:
        lt = rel["left_table"].upper()
        rt = rel["right_table"].upper()
        adj[lt].add(rt)
        adj[rt].add(lt)

    metric_tables = list(set(m["table"].upper() for m in ctx.metrics))
    dim_tables = set(d["table"].upper() for d in ctx.dimensions)

    issues = []
    for i, mt1 in enumerate(metric_tables):
        for mt2 in metric_tables[i + 1:]:
            shared = adj.get(mt1, set()) & adj.get(mt2, set())
            for shared_node in shared:
                if shared_node in dim_tables or any(
                    shared_node in adj.get(dt, set()) for dt in dim_tables
                ):
                    issues.append(
                        f"Potential chasm trap: metrics on '{mt1}' and '{mt2}' both connect "
                        f"to shared table '{shared_node}'. Aggregating both in one query will "
                        f"multiply results. Pre-aggregate each to '{shared_node}' grain separately."
                    )
                    break

    if issues:
        return CheckResult("chasm_trap_warning", False, "warning", "; ".join(issues))
    return CheckResult("chasm_trap_warning", True, "warning", "No chasm trap patterns detected.")


def _check_cardinality_lie_warning(ctx: _DDLContext) -> CheckResult:
    """15. Warn if a PK column also appears as FK to another table."""
    pk_by_alias: dict[str, set[str]] = {}
    for t in ctx.tables:
        pk_by_alias[t["alias"].upper()] = set(c.upper() for c in t["pk_cols"])

    issues = []
    for rel in ctx.relationships:
        lt = rel["left_table"].upper()
        for col in rel["left_cols"]:
            col_upper = col.upper()
            pks = pk_by_alias.get(lt, set())
            if col_upper in pks:
                issues.append(
                    f"Column '{col}' in table '{rel['left_table']}' is both PK and FK "
                    f"(references '{rel['right_table']}') — possible cardinality issue."
                )

    if issues:
        return CheckResult("cardinality_lie_warning", False, "warning", "; ".join(issues))
    return CheckResult("cardinality_lie_warning", True, "warning", "No cardinality issues detected.")


def _check_synonym_overlap(ctx: _DDLContext) -> CheckResult:
    """16. No synonym value should appear in multiple definitions."""
    synonym_owners: dict[str, list[str]] = defaultdict(list)
    for section_name, entries in [
        ("FACTS", ctx.facts), ("DIMENSIONS", ctx.dimensions), ("METRICS", ctx.metrics)
    ]:
        for col in entries:
            for syn in col["synonyms"]:
                key = syn.upper()
                synonym_owners[key].append(f"{section_name}:{col['table']}.{col['col_name']}")

    overlaps = {syn: owners for syn, owners in synonym_owners.items() if len(owners) > 1}
    if overlaps:
        msgs = [f"'{syn}' used by {', '.join(owners)}" for syn, owners in overlaps.items()]
        return CheckResult("synonym_overlap", False, "warning", "Overlapping synonyms: " + "; ".join(msgs))
    return CheckResult("synonym_overlap", True, "warning", "No synonym overlaps found.")


def _check_semi_additive_audit(ctx: _DDLContext) -> CheckResult:
    """17. Metrics using SUM/COUNT on snapshot/balance tables should have NON ADDITIVE BY."""
    snapshot_hints = re.compile(
        r"(snapshot|balance|headcount|inventory|pipeline|open.deals|active.subscribers)",
        re.IGNORECASE,
    )
    agg_pattern = re.compile(r"\b(SUM|COUNT)\s*\(", re.IGNORECASE)

    # Map table alias -> comment
    alias_comment: dict[str, str] = {}
    for t in ctx.tables:
        alias_comment[t["alias"].upper()] = t["comment"]

    issues = []
    for metric in ctx.metrics:
        tbl_comment = alias_comment.get(metric["table"].upper(), "")
        if snapshot_hints.search(tbl_comment) and agg_pattern.search(metric["expr"]):
            if not metric["non_additive"]:
                issues.append(
                    f"Metric {metric['table']}.{metric['col_name']} uses "
                    f"SUM/COUNT on snapshot table but missing NON ADDITIVE BY."
                )

    if issues:
        return CheckResult("semi_additive_audit", False, "warning", "; ".join(issues))
    return CheckResult(
        "semi_additive_audit", True, "warning",
        "No semi-additive issues detected.",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_ddl(ddl: str) -> List[CheckResult]:
    """Validate a CREATE SEMANTIC VIEW DDL string. Returns list of CheckResults."""
    ctx = _build_context(ddl)

    checks = [
        _check_clause_order,
        _check_alias_matches_physical,
        _check_no_duplicate_columns,
        _check_pk_on_referenced_tables,
        _check_using_clause_for_multi_rel,
        _check_no_empty_relationships,
        _check_fully_qualified_tables,
        _check_string_literal_escaping,
        _check_non_standard_column_quoting,
        _check_filter_label_boolean,
        _check_window_metric_inner_ref,
        _check_asof_column_type_hint,
        _check_orphan_detection,
        _check_fan_trap_warning,
        _check_chasm_trap_warning,
        _check_cardinality_lie_warning,
        _check_synonym_overlap,
        _check_semi_additive_audit,
    ]

    results = []
    for check_fn in checks:
        results.append(check_fn(ctx))

    # 18. overall_summary
    passed_count = sum(1 for r in results if r.passed)
    results.append(
        CheckResult(
            "overall_summary",
            True,
            "error",
            f"{passed_count}/{len(checks)} checks passed.",
        )
    )

    return results


def validate_file(path: str) -> List[CheckResult]:
    """Read a .sql file and validate each CREATE SEMANTIC VIEW statement found."""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Split on CREATE [OR REPLACE] SEMANTIC VIEW boundaries
    pattern = re.compile(
        r"(CREATE\s+(?:OR\s+REPLACE\s+)?SEMANTIC\s+VIEW\b)",
        re.IGNORECASE,
    )
    parts = pattern.split(content)

    # Reassemble statements: parts[0] is pre-content, then alternating (delimiter, body)
    statements = []
    for i in range(1, len(parts), 2):
        stmt = parts[i]
        if i + 1 < len(parts):
            stmt += parts[i + 1]
        statements.append(stmt)

    if not statements:
        return [
            CheckResult(
                "file_parse",
                False,
                "error",
                f"No CREATE SEMANTIC VIEW statements found in {path}.",
            )
        ]

    all_results = []
    for idx, stmt in enumerate(statements):
        results = validate_ddl(stmt)
        if len(statements) > 1:
            # Prefix check names with statement index
            for r in results:
                r.name = f"stmt{idx + 1}:{r.name}"
        all_results.extend(results)

    return all_results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _cli_main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python sv_validator.py <file.sql>", file=sys.stderr)
        return 1

    path = sys.argv[1]
    results = validate_file(path)

    any_fail = False
    for r in results:
        if r.passed:
            print(f"  \u2713 {r.name} (PASS)")
        else:
            any_fail = True
            severity = r.severity.upper()
            print(f"  \u2717 {r.name} [{severity}]: {r.message}")

    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(_cli_main())
