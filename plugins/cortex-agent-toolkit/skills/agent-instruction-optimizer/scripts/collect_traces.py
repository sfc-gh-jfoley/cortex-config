"""Build a few-shot trace pool from an existing baseline eval run.

Queries GET_AI_EVALUATION_DATA for high-scoring examples — no new agent calls.
Outputs trace_pool.json for use by build_candidate.py.
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path


def get_connection(connection_name: str):
    """Return a snowflake-connector connection using environment variables or connections.toml."""
    try:
        import snowflake.connector
    except ImportError:
        print("ERROR: snowflake-connector-python not installed. Run: pip install snowflake-connector-python", file=sys.stderr)
        sys.exit(1)

    account = os.environ.get("SNOWFLAKE_ACCOUNT")
    user = os.environ.get("SNOWFLAKE_USER")
    password = os.environ.get("SNOWFLAKE_PASSWORD")

    if account and user and password:
        return snowflake.connector.connect(
            account=account,
            user=user,
            password=password,
        )

    # Fall back to connections.toml / keyring via connection name
    try:
        return snowflake.connector.connect(connection_name=connection_name)
    except Exception as e:
        print(
            f"ERROR: Could not connect. Set SNOWFLAKE_ACCOUNT/USER/PASSWORD or configure "
            f"connection '{connection_name}' in ~/.snowflake/connections.toml. Detail: {e}",
            file=sys.stderr,
        )
        sys.exit(1)


def fetch_eval_rows(conn, database: str, schema: str, agent: str, eval_run: str) -> list[dict]:
    """Query GET_AI_EVALUATION_DATA for the specified eval run."""
    sql = f"""
        SELECT INPUT, GROUND_TRUTH, EVAL_AGG_SCORE, TEST_CATEGORY, METRIC_NAME
        FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
            '{database}', '{schema}', '{agent}',
            'CORTEX AGENT', '{eval_run}'
        ))
        WHERE METRIC_NAME = 'answer_correctness'
          AND EVAL_AGG_SCORE IS NOT NULL
    """
    cursor = conn.cursor()
    cursor.execute(sql)
    columns = [col[0] for col in cursor.description]
    rows = []
    for row in cursor.fetchall():
        rows.append(dict(zip(columns, row)))
    cursor.close()
    return rows


def select_traces(
    rows: list[dict],
    min_score: float,
    max_traces: int,
) -> list[dict]:
    """Filter, deduplicate by category, and return the final trace list."""
    passing = [r for r in rows if float(r.get("EVAL_AGG_SCORE", 0)) >= min_score]
    passing.sort(key=lambda r: float(r.get("EVAL_AGG_SCORE", 0)), reverse=True)

    # Cap at 3 per category for diversity
    category_counts: dict[str, int] = defaultdict(int)
    selected = []
    for row in passing:
        cat = row.get("TEST_CATEGORY") or "UNKNOWN"
        if category_counts[cat] >= 3:
            continue
        category_counts[cat] += 1
        selected.append(row)
        if len(selected) >= max_traces:
            break

    return selected


def format_trace(row: dict) -> dict:
    """Convert a DB row to trace_pool entry format."""
    ground_truth = row.get("GROUND_TRUTH") or ""
    if isinstance(ground_truth, str):
        try:
            ground_truth = json.loads(ground_truth)
        except (json.JSONDecodeError, TypeError):
            pass  # Leave as string

    return {
        "input": row.get("INPUT", ""),
        "expected_output": ground_truth,
        # agent_response not available from GET_AI_EVALUATION_DATA — left empty.
        # build_candidate.py falls back to expected_output when this is empty.
        "agent_response": "",
        "category": row.get("TEST_CATEGORY") or "UNKNOWN",
        "score": float(row.get("EVAL_AGG_SCORE", 0)),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Build few-shot trace pool from a baseline eval run"
    )
    parser.add_argument("--database", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--agent", required=True)
    parser.add_argument("--eval-run", required=True, help="Baseline eval run name")
    parser.add_argument("--connection", default="default",
                        help="Snow CLI connection name (fallback if env vars not set)")
    parser.add_argument("--min-score", type=float, default=0.75)
    parser.add_argument("--max-traces", type=int, default=20)
    parser.add_argument("--output", default="trace_pool.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be selected without writing")
    args = parser.parse_args()

    print(f"Connecting to Snowflake (connection: {args.connection}) ...", file=sys.stderr)
    conn = get_connection(args.connection)

    print(
        f"Fetching eval data: agent={args.agent}, run={args.eval_run}",
        file=sys.stderr,
    )
    rows = fetch_eval_rows(conn, args.database, args.schema, args.agent, args.eval_run)
    conn.close()
    print(f"  Retrieved {len(rows)} answer_correctness rows", file=sys.stderr)

    traces = select_traces(rows, args.min_score, args.max_traces)
    pool = [format_trace(r) for r in traces]

    # Summary
    by_cat: dict[str, int] = defaultdict(int)
    for t in pool:
        by_cat[t["category"]] += 1
    print(f"Selected {len(pool)} traces (min_score={args.min_score}):", file=sys.stderr)
    for cat, count in sorted(by_cat.items()):
        print(f"  {cat}: {count}", file=sys.stderr)

    if args.dry_run:
        print("[dry-run] Would write:", file=sys.stderr)
        for t in pool:
            print(f"  [{t['score']:.3f}] {t['category']}: {str(t['input'])[:80]}", file=sys.stderr)
        print(json.dumps({"dry_run": True, "count": len(pool), "by_category": dict(by_cat)}))
        return

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        json.dump(pool, f, indent=2, default=str)
    print(f"Wrote {len(pool)} traces to {args.output}", file=sys.stderr)
    print(json.dumps({"status": "ok", "count": len(pool), "output": args.output}))


if __name__ == "__main__":
    main()
