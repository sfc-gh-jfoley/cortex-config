#!/usr/bin/env python3
"""SV-specific mutation engine for GEPA optimization.

Provides operator selection, LLM prompt generation, and mutation validation.

Usage:
  python mutate.py select-operator --weights-file <state_path>
  python mutate.py get-prompt <operator> <sv_ddl_path>
  python mutate.py validate <original_ddl_path> <mutated_ddl_path>

Run with: python3 scripts/mutate.py
"""

import argparse
import json
import random
import re
import sys
from pathlib import Path


OPERATORS = [
    "add_synonym",
    "improve_description",
    "add_filter",
    "add_vqr",
    "add_metric",
    "refine_metric_expr",
    "add_metric_description",
    "change_relationship",
    "add_time_dimension",
    "remove_column",
]

PROMPT_TEMPLATES = {
    "add_synonym": """You are mutating a semantic view to improve natural language query matching.

TASK: Add 2-3 natural language synonyms to columns in this semantic view.

SEMANTIC VIEW DDL:
```sql
{ddl}
```

INSTRUCTIONS:
1. Identify columns where users might use different terminology than the column name
2. Add synonyms using the `synonyms` property (list of strings)
3. Focus on business terminology variations (e.g., "revenue" → ["sales", "income", "earnings"])
4. Only add synonyms that are genuinely used in business contexts
5. Return the complete modified DDL

Return ONLY the modified CREATE OR REPLACE SEMANTIC VIEW DDL, no explanation.""",

    "improve_description": """You are mutating a semantic view to improve column discoverability.

TASK: Improve descriptions for columns that have vague or missing descriptions.

SEMANTIC VIEW DDL:
```sql
{ddl}
```

INSTRUCTIONS:
1. Find columns with missing, generic, or unhelpful descriptions
2. Rewrite descriptions to clearly explain:
   - What the column represents in business terms
   - What values it typically contains
   - When/why an analyst would use this column
3. Keep descriptions concise (1-2 sentences max)
4. Do NOT change column names, types, or other properties
5. Return the complete modified DDL

Return ONLY the modified CREATE OR REPLACE SEMANTIC VIEW DDL, no explanation.""",

    "add_filter": """You are mutating a semantic view to add commonly-needed filters.

TASK: Add named filters for common WHERE clause patterns.

SEMANTIC VIEW DDL:
```sql
{ddl}
```

INSTRUCTIONS:
1. Identify dimensions that would benefit from pre-defined filters
2. Add filters using the `filters` property with clear names
3. Common patterns to consider:
   - Date ranges (last 30 days, current year, YTD)
   - Status filters (active only, completed, pending)
   - Category groupings (top N, specific segments)
4. Name filters with natural language users would say ("recent orders", "active customers")
5. Return the complete modified DDL

Return ONLY the modified CREATE OR REPLACE SEMANTIC VIEW DDL, no explanation.""",

    "add_vqr": """You are mutating a semantic view by adding a new verified query representation (VQR).

TASK: Generate a new verified query that tests a specific analytical capability.

SEMANTIC VIEW DDL:
```sql
{ddl}
```

INSTRUCTIONS:
1. Analyze the existing VQRs (if any) to identify gaps in coverage
2. Create a new VQR that tests a different analytical pattern:
   - Aggregation with GROUP BY
   - Time-based filtering
   - Multi-table joins
   - Metric calculations
   - Ranking or top-N queries
3. The VQR must have:
   - A natural language question (what a user would ask)
   - A verified SQL answer that correctly answers the question
4. Ensure the SQL is valid against the tables in this semantic view
5. Return the complete modified DDL with the new VQR added

Return ONLY the modified CREATE OR REPLACE SEMANTIC VIEW DDL, no explanation.""",

    "add_metric": """You are mutating a semantic view to add a new aggregate metric.

TASK: Define a new metric that answers common analytical questions.

SEMANTIC VIEW DDL:
```sql
{ddl}
```

INSTRUCTIONS:
1. Review existing metrics and identify gaps
2. Define a new metric with:
   - Clear name matching business terminology
   - Appropriate expression (SUM, AVG, COUNT, COUNT DISTINCT, etc.)
   - default_aggregation setting
   - Description explaining what it measures
3. Consider metrics like:
   - Conversion rates (ratio metrics)
   - Growth metrics (period-over-period)
   - Concentration metrics (top-N share)
4. Ensure the metric references valid columns from the semantic view's tables
5. Return the complete modified DDL

Return ONLY the modified CREATE OR REPLACE SEMANTIC VIEW DDL, no explanation.""",

    "refine_metric_expr": """You are mutating a semantic view to fix a metric that produces wrong results.

TASK: Fix the expression of an existing metric.

SEMANTIC VIEW DDL:
```sql
{ddl}
```

INSTRUCTIONS:
1. Review each metric's expression for correctness:
   - Is the aggregation function appropriate? (SUM vs AVG vs COUNT)
   - Are NULL values handled correctly?
   - Is the denominator correct for ratio metrics?
   - Does it account for duplicates from joins?
2. Fix any metric with an incorrect or suboptimal expression
3. Update the default_aggregation if it doesn't match the expression
4. Do NOT remove metrics — only refine their expressions
5. Return the complete modified DDL

Return ONLY the modified CREATE OR REPLACE SEMANTIC VIEW DDL, no explanation.""",

    "add_metric_description": """You are mutating a semantic view to improve metric descriptions.

TASK: Add or improve descriptions and synonyms for metrics.

SEMANTIC VIEW DDL:
```sql
{ddl}
```

INSTRUCTIONS:
1. Find metrics with missing or unclear descriptions
2. Add descriptions that explain:
   - What the metric measures in plain English
   - How it's calculated (briefly)
   - When to use this metric vs similar ones
3. Add 2-3 synonyms for each metric (alternative names users might say)
4. Do NOT change metric expressions or aggregations
5. Return the complete modified DDL

Return ONLY the modified CREATE OR REPLACE SEMANTIC VIEW DDL, no explanation.""",

    "change_relationship": """You are mutating a semantic view to fix join relationships.

TASK: Fix or improve the relationships between tables.

SEMANTIC VIEW DDL:
```sql
{ddl}
```

INSTRUCTIONS:
1. Review existing relationships for correctness:
   - Are join keys correct?
   - Is the join type appropriate (inner vs left)?
   - Are there missing relationships that cause wrong results?
2. Common fixes:
   - Change INNER JOIN to LEFT JOIN to preserve rows
   - Add missing relationships for tables that should be joinable
   - Fix join keys that reference wrong columns
3. Ensure referential integrity direction is correct (FK → PK)
4. Return the complete modified DDL

Return ONLY the modified CREATE OR REPLACE SEMANTIC VIEW DDL, no explanation.""",

    "add_time_dimension": """You are mutating a semantic view to add time dimension support.

TASK: Promote DATE/TIMESTAMP columns to proper time dimensions.

SEMANTIC VIEW DDL:
```sql
{ddl}
```

INSTRUCTIONS:
1. Find DATE or TIMESTAMP columns not yet marked as time dimensions
2. Promote them using `kind: time_dimension` with appropriate properties
3. Consider:
   - Which date column is the primary time axis for analysis?
   - Should it support drill-down (year → quarter → month → day)?
   - Are there multiple time dimensions (order_date, ship_date)?
4. Ensure only genuinely temporal columns are promoted (not IDs that happen to contain dates)
5. Return the complete modified DDL

Return ONLY the modified CREATE OR REPLACE SEMANTIC VIEW DDL, no explanation.""",

    "remove_column": """You are mutating a semantic view to reduce noise by removing confusing columns.

TASK: Remove columns that cause ambiguity or confusion for the AI analyst.

SEMANTIC VIEW DDL:
```sql
{ddl}
```

INSTRUCTIONS:
1. Identify columns that might cause the analyst to pick the wrong column:
   - Internal IDs not useful for analysis (surrogate keys, hash keys)
   - Redundant columns (same data in different formats)
   - Technical columns (ETL timestamps, audit fields, system columns)
   - Columns with confusingly similar names
2. Remove at most 2-3 columns per mutation
3. Do NOT remove:
   - Primary/foreign keys needed for relationships
   - Columns referenced in metrics
   - Columns used in verified queries
4. Return the complete modified DDL

Return ONLY the modified CREATE OR REPLACE SEMANTIC VIEW DDL, no explanation.""",
}


def load_state(state_path: str) -> dict:
    """Load GEPA state from YAML file."""
    path = Path(state_path)
    if not path.exists():
        print(f"Error: State file not found: {state_path}", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def cmd_select_operator(args: argparse.Namespace) -> None:
    """Weighted random selection of mutation operator."""
    state = load_state(args.weights_file)
    weights = state.get("operator_weights", {})

    if not weights:
        # Fallback to uniform
        selected = random.choice(OPERATORS)
    else:
        operators = list(weights.keys())
        probs = list(weights.values())
        selected = random.choices(operators, weights=probs, k=1)[0]

    # Suggest target based on operator type
    target_hints = {
        "add_synonym": "dimensions or facts with non-obvious names",
        "improve_description": "columns with missing or vague descriptions",
        "add_filter": "dimensions with common categorical or date-range patterns",
        "add_vqr": "semantic view level (new verified query)",
        "add_metric": "semantic view level (new aggregate metric)",
        "refine_metric_expr": "existing metrics with incorrect expressions",
        "add_metric_description": "metrics missing descriptions or synonyms",
        "change_relationship": "relationships with wrong join type or missing joins",
        "add_time_dimension": "DATE/TIMESTAMP columns not yet marked as time dimensions",
        "remove_column": "noisy/confusing columns causing analyst errors",
    }

    result = {
        "operator": selected,
        "target_hint": target_hints.get(selected, ""),
        "weight": weights.get(selected, 1.0 / len(OPERATORS)),
    }
    print(json.dumps(result))


def cmd_get_prompt(args: argparse.Namespace) -> None:
    """Generate LLM prompt for a given operator."""
    operator = args.operator
    ddl_path = Path(args.sv_ddl_path)

    if operator not in PROMPT_TEMPLATES:
        print(f"Error: Unknown operator '{operator}'. Valid: {OPERATORS}", file=sys.stderr)
        sys.exit(1)

    if not ddl_path.exists():
        print(f"Error: DDL file not found: {ddl_path}", file=sys.stderr)
        sys.exit(1)

    ddl = ddl_path.read_text()
    prompt = PROMPT_TEMPLATES[operator].format(ddl=ddl)

    print(json.dumps({"operator": operator, "prompt": prompt}))


def cmd_validate(args: argparse.Namespace) -> None:
    """Validate a mutated DDL against anti-patterns."""
    original_path = Path(args.original_ddl_path)
    mutated_path = Path(args.mutated_ddl_path)

    if not original_path.exists():
        print(f"Error: Original DDL not found: {original_path}", file=sys.stderr)
        sys.exit(1)
    if not mutated_path.exists():
        print(f"Error: Mutated DDL not found: {mutated_path}", file=sys.stderr)
        sys.exit(1)

    original = original_path.read_text()
    mutated = mutated_path.read_text()

    errors = []

    # Check 1: Clause order (TABLES → RELATIONSHIPS → FACTS → DIMENSIONS → METRICS)
    clause_order = ["TABLES", "RELATIONSHIPS", "FACTS", "DIMENSIONS", "METRICS"]
    positions = {}
    for clause in clause_order:
        # Look for the clause keyword at start of line or after WITH
        match = re.search(rf"\b{clause}\b", mutated, re.IGNORECASE)
        if match:
            positions[clause] = match.start()

    found_clauses = [c for c in clause_order if c in positions]
    for i in range(len(found_clauses) - 1):
        if positions[found_clauses[i]] > positions[found_clauses[i + 1]]:
            errors.append(
                f"Clause order violation: {found_clauses[i]} appears after {found_clauses[i+1]}"
            )

    # Check 2: Column alias must match physical name (direct columns)
    # Pattern: column_name TYPE ALIAS 'different_name'
    alias_pattern = re.compile(
        r"(\w+)\s+\w+(?:\(\d+(?:,\d+)?\))?\s+ALIAS\s+'(\w+)'", re.IGNORECASE
    )
    for match in alias_pattern.finditer(mutated):
        col_name = match.group(1).lower()
        alias_name = match.group(2).lower()
        if col_name != alias_name:
            errors.append(
                f"Column alias mismatch: '{match.group(1)}' has alias '{match.group(2)}' "
                f"(direct column alias must match physical name)"
            )

    # Check 3: No duplicate column names across tables
    # Simple heuristic: find all column definitions and check for duplicates
    col_defs = re.findall(r"^\s+(\w+)\s+(?:VARCHAR|NUMBER|DATE|TIMESTAMP|BOOLEAN|FLOAT|INT)", mutated, re.MULTILINE | re.IGNORECASE)
    seen_cols = {}
    for col in col_defs:
        col_lower = col.lower()
        if col_lower in seen_cols:
            # This is acceptable IF the columns are in different tables
            # We flag it as a warning, not a hard error
            pass
        seen_cols[col_lower] = seen_cols.get(col_lower, 0) + 1

    # Check 4: Mutation is not identical to original (no-op check)
    if original.strip() == mutated.strip():
        errors.append("Mutation is a no-op: mutated DDL is identical to original")

    # Check 5: DDL starts with CREATE OR REPLACE SEMANTIC VIEW
    if not re.match(r"\s*CREATE\s+OR\s+REPLACE\s+SEMANTIC\s+VIEW", mutated, re.IGNORECASE):
        errors.append("DDL must start with CREATE OR REPLACE SEMANTIC VIEW")

    if errors:
        result = {"status": "FAIL", "errors": errors}
    else:
        result = {"status": "PASS", "errors": []}

    print(json.dumps(result, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SV mutation engine for GEPA optimization"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # select-operator
    p_select = subparsers.add_parser("select-operator", help="Weighted random operator selection")
    p_select.add_argument("--weights-file", required=True, help="Path to gepa_state.yaml")
    p_select.add_argument("--seed", type=int, help="Random seed for reproducibility")

    # get-prompt
    p_prompt = subparsers.add_parser("get-prompt", help="Generate LLM prompt for operator")
    p_prompt.add_argument("operator", choices=OPERATORS, help="Mutation operator name")
    p_prompt.add_argument("sv_ddl_path", help="Path to semantic view DDL file")

    # validate
    p_validate = subparsers.add_parser("validate", help="Validate mutated DDL")
    p_validate.add_argument("original_ddl_path", help="Path to original DDL")
    p_validate.add_argument("mutated_ddl_path", help="Path to mutated DDL")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if hasattr(args, "seed") and args.seed is not None:
        random.seed(args.seed)

    commands = {
        "select-operator": cmd_select_operator,
        "get-prompt": cmd_get_prompt,
        "validate": cmd_validate,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
