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


def _lit(value: str) -> str:
    """Single-quoted SQL string literal."""
    return "'" + str(value).replace("'", "''") + "'"


def get_batch_sql(database: str, schema: str, eval_table: str,
                  dev_split_value: str, batch_pct: float,
                  generation: int, history: list[dict],
                  id_column: str = "TEST_ID") -> tuple[str, str]:
    """Generate SQL that materializes a stratified batch and exposes it as a view.

    The sample is frozen into ``GEPA_BATCH_GEN_<G>_DATA`` and the view
    ``GEPA_BATCH_GEN_<G>`` selects from it, so every candidate in a generation
    is scored on the same questions. Ordering uses HASH(id, seed), which is
    deterministic; RANDOM(seed) is not stable across view evaluations.

    Returns:
        tuple of (setup SQL: CREATE TABLE + CREATE VIEW, SELECT query to retrieve chosen IDs)
    """
    if not id_column.replace("_", "").isalnum():
        raise ValueError(f"invalid id column: {id_column!r}")
    id_col = _qi(id_column)
    table_fqn = _fqn(database, schema, eval_table)
    view_name = _fqn(database, schema, f"GEPA_BATCH_GEN_{generation}")
    data_name = _fqn(database, schema, f"GEPA_BATCH_GEN_{generation}_DATA")
    seed = generation  # reproducible but different each gen
    split = _lit(dev_split_value)

    # Build exclusion set from immediately previous generation only
    exclude_ids = set()
    if history:
        last_gen = history[-1]
        for qid in last_gen.get("batch_questions", []):
            exclude_ids.add(qid)

    exclude_clause = ""
    if exclude_ids:
        # Exclude up to half of previous batch to force partial exploration
        id_list = ",".join(_lit(qid) for qid in sorted(exclude_ids)[:50])
        exclude_clause = f"""
        AND {id_col} NOT IN (
            SELECT {id_col} FROM (
                SELECT {id_col}, ROW_NUMBER() OVER (ORDER BY HASH({id_col}, {seed + 1000})) AS rn
                FROM {table_fqn}
                WHERE SPLIT = {split}
                AND {id_col} IN ({id_list})
            ) WHERE rn <= {len(exclude_ids) // 2}
        )"""

    # Stratified proportional sample, frozen into a table so it cannot drift
    sql = f"""CREATE OR REPLACE TABLE {data_name} AS
WITH category_counts AS (
    SELECT
        TEST_CATEGORY,
        COUNT(*) AS cat_total,
        GREATEST(1, CEIL(COUNT(*) * {batch_pct})) AS cat_sample_size
    FROM {table_fqn}
    WHERE SPLIT = {split}{exclude_clause}
    GROUP BY TEST_CATEGORY
),
ranked AS (
    SELECT
        t.*,
        ROW_NUMBER() OVER (
            PARTITION BY t.TEST_CATEGORY
            ORDER BY HASH(t.{id_col}, {seed})
        ) AS rn
    FROM {table_fqn} t
    WHERE t.SPLIT = {split}{exclude_clause}
)
SELECT r.* EXCLUDE (rn)
FROM ranked r
JOIN category_counts c ON r.TEST_CATEGORY = c.TEST_CATEGORY
WHERE r.rn <= c.cat_sample_size;
CREATE OR REPLACE VIEW {view_name} AS SELECT * FROM {data_name};"""

    # Query to retrieve selected IDs after view creation
    id_query = f"SELECT {id_col} FROM {view_name} ORDER BY {id_col};"

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
    parser.add_argument("--id-column", default="TEST_ID",
                        help="Question ID column in the eval table (default: TEST_ID)")

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
        id_column=args.id_column,
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
