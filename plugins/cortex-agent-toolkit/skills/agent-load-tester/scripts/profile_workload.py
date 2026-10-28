#!/usr/bin/env python3
"""Phase 1 — Profile an agent's eval telemetry into a load-test workload.

Reads SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS for the agent's eval runs and writes to --out:
  profile.json      per-question think/sql/other stats + modeled SQL concurrency per tier
  sql_mix.jsonl     captured SQL (text, query_id, duration, weight) joined to QUERY_HISTORY
  prompts.jsonl     planning/response LLM steps (model, tokens, instruction, tools, messages) for Phase 2
  outliers.json     SQL whose duration needs tuning before sizing

Usage:
  python profile_workload.py --connection default --agent DB.SCHEMA.AGENT [--run RUN_NAME ...]
         [--tiers 10,25,50,100,200] [--pause 30] [--out ./lt_out] [--outlier-s 10]
"""

import argparse
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
import lt_common as lt

SPAN_SQL = """
SELECT
  RECORD_ATTRIBUTES:"snow.ai.observability.run.name"::string            AS run_name,
  RECORD_ATTRIBUTES:"ai.observability.record_id"::string                 AS record_id,
  RECORD:name::string                                                    AS span,
  DATEDIFF('millisecond', START_TIMESTAMP, TIMESTAMP)                    AS ms,
  START_TIMESTAMP                                                        AS start_ts,
  RECORD_ATTRIBUTES:"snow.ai.observability.agent.tool.sql_execution.query"::string    AS sql_text,
  RECORD_ATTRIBUTES:"snow.ai.observability.agent.tool.sql_execution.query_id"::string AS query_id,
  RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.model"::string              AS model,
  RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.token_count.input"::int     AS tok_in,
  RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.token_count.output"::int    AS tok_out,
  RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.instruction"::string        AS instruction,
  RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.tool.description"           AS tool_desc,
  RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.messages"::string           AS messages
FROM SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS
WHERE RECORD_TYPE = 'SPAN'
  AND RECORD_ATTRIBUTES:"snow.ai.observability.database.name"::string = %(db)s
  AND RECORD_ATTRIBUTES:"snow.ai.observability.schema.name"::string   = %(sch)s
  AND RECORD_ATTRIBUTES:"snow.ai.observability.object.name"::string   = %(agent)s
  AND RECORD_ATTRIBUTES:"snow.ai.observability.run.name" IS NOT NULL
  {run_filter}
"""

QH_SQL = """
SELECT query_id, warehouse_name, warehouse_size, execution_status,
       total_elapsed_time, compilation_time, execution_time,
       queued_overload_time, queued_provisioning_time,
       bytes_scanned, partitions_scanned, partitions_total,
       bytes_spilled_to_local_storage, bytes_spilled_to_remote_storage,
       percentage_scanned_from_cache
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE query_id IN ({ids})
"""


def fetch_spans(conn, agent_fqn, runs):
    db, sch, name = agent_fqn.split(".")
    params = {"db": db, "sch": sch, "agent": name}
    run_filter = ""
    if runs:
        keys = []
        for i, r in enumerate(runs):
            params[f"r{i}"] = r
            keys.append(f"%(r{i})s")
        run_filter = f'AND RECORD_ATTRIBUTES:"snow.ai.observability.run.name"::string IN ({",".join(keys)})'
    cur = conn.cursor()
    cur.execute(SPAN_SQL.format(run_filter=run_filter), params)
    cols = [c[0].lower() for c in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


def fetch_query_history(conn, query_ids):
    out = {}
    ids = sorted({q for q in query_ids if q})
    cur = conn.cursor()
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        cur.execute(QH_SQL.format(ids=",".join(["%s"] * len(chunk))), chunk)
        cols = [c[0].lower() for c in cur.description]
        for r in cur.fetchall():
            d = dict(zip(cols, r))
            out[d["query_id"]] = d
    cur.close()
    return out


def build(rows, tiers, pause_s, outlier_s):
    by_q = defaultdict(lambda: {"total": None, "plan": 0, "resp": 0, "sql": 0, "sql_calls": 0, "plan_steps": 0})
    sql_rows, prompt_rows = [], []
    for r in rows:
        k = (r["run_name"], r["record_id"])
        q, span, ms = by_q[k], r["span"], r["ms"] or 0
        if span == "Agent":
            q["total"] = ms
        elif span.startswith("ReasoningAgentStepPlanning-"):
            q["plan"] += ms; q["plan_steps"] += 1
            prompt_rows.append({"kind": "planning", "run": r["run_name"], "record_id": r["record_id"], "ms": ms,
                                "model": r["model"], "tok_in": r["tok_in"], "tok_out": r["tok_out"],
                                "instruction": r["instruction"], "tool_desc": r["tool_desc"],
                                "messages": r["messages"]})
        elif span.startswith("ReasoningAgentStepResponseGeneration-"):
            q["resp"] += ms
            prompt_rows.append({"kind": "response", "run": r["run_name"], "record_id": r["record_id"], "ms": ms,
                                "model": r["model"], "tok_in": r["tok_in"], "tok_out": r["tok_out"]})
        elif span.startswith("SqlExecution"):
            q["sql"] += ms; q["sql_calls"] += 1
            if r["sql_text"]:
                sql_rows.append({"run": r["run_name"], "record_id": r["record_id"], "query_id": r["query_id"],
                                 "duration_ms": ms, "sql": r["sql_text"]})
    qs = [q for q in by_q.values() if q["total"]]
    if not qs:
        raise SystemExit("No eval traces with an Agent span found for this agent/run filter.")
    s = lambda key: lt.summarize([q[key] / 1000 for q in qs])
    think = lt.summarize([(q["plan"] + q["resp"]) / 1000 for q in qs])
    other = lt.summarize([(q["total"] - q["plan"] - q["resp"] - q["sql"]) / 1000 for q in qs])
    calls = sum(q["sql_calls"] for q in qs) / len(qs)
    sql_per_call = (sum(q["sql"] for q in qs) / max(1, sum(q["sql_calls"] for q in qs))) / 1000
    total_avg = s("total")["avg"]
    profile = {
        "questions": len(qs), "runs": sorted({k[0] for k in by_q}),
        "total_s": s("total"), "think_s": think, "sql_s_per_question": s("sql"), "other_s": other,
        "sql_calls_per_question": round(calls, 2), "sql_s_per_call": round(sql_per_call, 3),
        "plan_steps_per_question": round(sum(q["plan_steps"] for q in qs) / len(qs), 2),
        "think_pct": round(100 * think["avg"] / total_avg, 1),
        "sql_pct": round(100 * s("sql")["avg"] / total_avg, 1),
        "pause_s": pause_s,
        "models": sorted({p["model"] for p in prompt_rows if p["model"]}),
        "modeled_concurrency": lt.concurrency_table(tiers, calls, total_avg, pause_s, sql_per_call),
    }
    outliers = [r for r in sql_rows if r["duration_ms"] >= outlier_s * 1000]
    return profile, sql_rows, prompt_rows, outliers


def weight_sql(sql_rows, qh):
    """Dedupe identical SQL text; weight = occurrences. Attach QUERY_HISTORY stats of a representative."""
    groups = {}
    for r in sql_rows:
        g = groups.setdefault(r["sql"], {"sql": r["sql"], "weight": 0, "durations_ms": [], "query_ids": []})
        g["weight"] += 1; g["durations_ms"].append(r["duration_ms"]); g["query_ids"].append(r["query_id"])
    out = []
    for i, g in enumerate(groups.values()):
        rep = next((qh[q] for q in g["query_ids"] if q in qh), {})
        out.append({"id": f"q{i:04d}", "weight": g["weight"], "avg_ms": sum(g["durations_ms"]) / len(g["durations_ms"]),
                    "query_ids": g["query_ids"][:5], "history": rep, "sql": g["sql"]})
    return sorted(out, key=lambda x: -x["weight"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--connection", required=True)
    ap.add_argument("--agent", required=True, help="DB.SCHEMA.AGENT")
    ap.add_argument("--run", action="append", default=[], help="eval run name (repeatable); default all")
    ap.add_argument("--tiers", default="10,25,50,100,200")
    ap.add_argument("--pause", type=float, default=30.0, help="user pause between questions (s)")
    ap.add_argument("--outlier-s", type=float, default=10.0)
    ap.add_argument("--no-query-history", action="store_true", help="skip ACCOUNT_USAGE join")
    ap.add_argument("--out", default="./lt_out")
    a = ap.parse_args()
    lt.validate_fqn(a.agent, "agent")
    os.makedirs(a.out, exist_ok=True)
    tiers = [int(x) for x in a.tiers.split(",")]

    conn = lt.connect(a.connection)
    rows = fetch_spans(conn, a.agent, a.run)
    profile, sql_rows, prompt_rows, outliers = build(rows, tiers, a.pause, a.outlier_s)
    qh = {} if a.no_query_history else fetch_query_history(conn, [r["query_id"] for r in sql_rows])
    conn.close()
    mix = weight_sql(sql_rows, qh)
    profile.update({"agent": a.agent, "connection": a.connection, "distinct_sql": len(mix),
                    "query_history_matched": len(qh), "outlier_sql": len(outliers)})
    whs = sorted({m["history"].get("warehouse_name") for m in mix if m["history"].get("warehouse_name")})
    profile["source_warehouses"] = whs

    lt.write_json(os.path.join(a.out, "profile.json"), profile)
    with open(os.path.join(a.out, "sql_mix.jsonl"), "w") as f:
        for m in mix:
            f.write(json.dumps(m, default=str) + "\n")
    with open(os.path.join(a.out, "prompts.jsonl"), "w") as f:
        for p in prompt_rows:
            f.write(json.dumps(p, default=str) + "\n")
    lt.write_json(os.path.join(a.out, "outliers.json"), outliers)

    print(json.dumps({k: profile[k] for k in ("agent", "questions", "think_pct", "sql_pct",
                                              "sql_calls_per_question", "sql_s_per_call", "distinct_sql",
                                              "outlier_sql", "source_warehouses", "models")}, indent=2, default=str))
    print("modeled SQL concurrency:")
    for r in profile["modeled_concurrency"]:
        print(f"  {r['users']:>4} users  {r['sql_qps']:>7.2f} sql/s  ~{r['sql_concurrency']:.1f} concurrent")


if __name__ == "__main__":
    main()
