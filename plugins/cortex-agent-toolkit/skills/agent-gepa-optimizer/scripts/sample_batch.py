"""Generate stratified mini-batch SQL for a GEPA generation."""

import argparse
import json
import sys
from pathlib import Path


def _qi(identifier: str) -> str:
    """Quote a Snowflake identifier if not already quoted."""
    if identifier.startswith('"') and identifier.endswith('"'):
        return identifier
    # Don't quote fully-qualified paths that are already uppercase alphanumeric
    if identifier.replace("_", "").isalnum() and identifier == identifier.upper():
        return identifier
    return f'"{identifier}"'


def _fqn(database: str, schema: str, obj: str) -> str:
    """Build a fully-qualified name with proper quoting."""
    return f"{_qi(database)}.{_qi(schema)}.{_qi(obj)}"


def get_batch_sql(database: str, schema: str, eval_table: str,
                  dev_split_value: str, batch_pct: float,
                  generation: int, history: list[dict]) -> tuple[str, str]:
    """Generate CREATE VIEW SQL for a stratified batch.

    Returns:
        tuple of (CREATE VIEW SQL, SELECT query to retrieve chosen IDs)
    """
    table_fqn = _fqn(database, schema, eval_table)
    view_name = _fqn(database, schema, f"GEPA_BATCH_GEN_{generation}")
    seed = generation  # reproducible but different each gen

    # Build exclusion set from immediately previous generation only
    exclude_ids = set()
    if history:
        last_gen = history[-1]
        for qid in last_gen.get("batch_questions", []):
            exclude_ids.add(qid)

    exclude_clause = ""
    if exclude_ids:
        # Exclude up to half of previous batch to force partial exploration
        id_list = ",".join(f"'{qid}'" for qid in list(exclude_ids)[:50])
        exclude_clause = f"""
        AND INPUT_ID NOT IN (
            SELECT INPUT_ID FROM (
                SELECT INPUT_ID, ROW_NUMBER() OVER (ORDER BY RANDOM({seed + 1000})) AS rn
                FROM {table_fqn}
                WHERE SPLIT = '{dev_split_value}'
                AND INPUT_ID IN ({id_list})
            ) WHERE rn <= {len(exclude_ids) // 2}
        )"""

    # Stratified proportional sample via QUALIFY
    sql = f"""CREATE OR REPLACE VIEW {view_name} AS
WITH category_counts AS (
    SELECT
        TEST_CATEGORY,
        COUNT(*) AS cat_total,
        GREATEST(1, CEIL(COUNT(*) * {batch_pct})) AS cat_sample_size
    FROM {table_fqn}
    WHERE SPLIT = '{dev_split_value}'{exclude_clause}
    GROUP BY TEST_CATEGORY
),
ranked AS (
    SELECT
        t.*,
        ROW_NUMBER() OVER (
            PARTITION BY t.TEST_CATEGORY
            ORDER BY RANDOM({seed})
        ) AS rn
    FROM {table_fqn} t
    WHERE t.SPLIT = '{dev_split_value}'{exclude_clause}
)
SELECT r.*
FROM ranked r
JOIN category_counts c ON r.TEST_CATEGORY = c.TEST_CATEGORY
WHERE r.rn <= c.cat_sample_size;"""

    # Query to retrieve selected IDs after view creation
    id_query = f"SELECT INPUT_ID FROM {view_name} ORDER BY INPUT_ID;"

    return sql, id_query


def main():
    parser = argparse.ArgumentParser(description="GEPA stratified batch sampler")
    parser.add_argument("database", help="Snowflake database name")
    parser.add_argument("schema", help="Snowflake schema name")
    parser.add_argument("eval_table", help="Eval dataset table/view name")
    parser.add_argument("dev_split_value", help="Value of SPLIT column for dev set")
    parser.add_argument("--batch-pct", type=float, default=0.30,
                        help="Fraction of dev set per batch (default: 0.30)")
    parser.add_argument("--generation", type=int, required=True,
                        help="Current generation number")
    parser.add_argument("--history-file", default=None,
                        help="Path to gepa_state.json for history lookup")

    args = parser.parse_args()

    # Load history from state file if provided
    history = []
    if args.history_file:
        p = Path(args.history_file)
        if p.exists():
            with p.open("r") as f:
                state = json.load(f)
                history = state.get("history", [])

    sql, id_query = get_batch_sql(
        database=args.database,
        schema=args.schema,
        eval_table=args.eval_table,
        dev_split_value=args.dev_split_value,
        batch_pct=args.batch_pct,
        generation=args.generation,
        history=history,
    )

    # Structured JSON to stdout (for CoCo to parse)
    print(json.dumps({"view_sql": sql, "id_query": id_query}))

    # Human-readable info to stderr
    print(f"[sample_batch] Generation {args.generation}, batch_pct={args.batch_pct}",
          file=sys.stderr)
    print(f"[sample_batch] History: {len(history)} previous generations",
          file=sys.stderr)


if __name__ == "__main__":
    main()
