#!/usr/bin/env python3
"""Server-side metrics for Phase 3 (agent live) and Phase 4 (SQL replay) runs.

--side sql   : per (config, tier, cache) from QUERY_HISTORY by QUERY_TAG — latency/exec/queue/compile
               percentiles, failures, Interactive fallback (ran on another warehouse), cache-hit share;
               plus warehouse load (running vs queued), cluster events, metered credits for the window.
--side agent : spans for the agent inside each tier's window (non-eval traffic) — think vs SQL time
               under load, observed SQL concurrency (Little's law over the window), SQL queue time.

ACCOUNT_USAGE lags up to ~45 min (metering up to hours). Use --source info for immediate query
results (INFORMATION_SCHEMA, needs --info-db, 7-day/10k-row limits) and re-run later for final.

Usage:
  python collect_metrics.py --side sql   --run-file lt_out/sql_replay_<id>.json   --connection default [--source info --info-db MYDB]
  python collect_metrics.py --side agent --run-file lt_out/agent_load_<id>.json --connection default
Writes: <run-file stem>_metrics.json
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import lt_common as lt

PCT = """
  COUNT(*) AS queries,
  COUNT_IF(execution_status <> 'SUCCESS') AS failed,
  COUNT_IF(UPPER(warehouse_name) <> UPPER(%(wh)s)) AS ran_elsewhere,
  ROUND(100 * AVG(IFF(execution_time = 0 AND execution_status = 'SUCCESS', 1, 0)), 1) AS result_cache_pct,
  APPROX_PERCENTILE(total_elapsed_time, .5)  AS elapsed_p50_ms,
  APPROX_PERCENTILE(total_elapsed_time, .95) AS elapsed_p95_ms,
  APPROX_PERCENTILE(total_elapsed_time, .99) AS elapsed_p99_ms,
  APPROX_PERCENTILE(execution_time, .5)      AS exec_p50_ms,
  APPROX_PERCENTILE(execution_time, .95)     AS exec_p95_ms,
  APPROX_PERCENTILE(compilation_time, .5)    AS compile_p50_ms,
  AVG(queued_overload_time)                  AS queued_avg_ms,
  APPROX_PERCENTILE(queued_overload_time, .95) AS queued_p95_ms,
  COUNT_IF(queued_overload_time > 0)         AS queued_queries,
  MAX(queued_provisioning_time)              AS provisioning_max_ms,
  MIN(start_time) AS first_start, MAX(end_time) AS last_end
"""


def q(cur, sql, params=None):
    cur.execute(sql, params or {})
    cols = [c[0].lower() for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def sql_side(conn, run, a):
    cur = conn.cursor()
    out = []
    for cell in run["cells"]:
        params = {"tag": cell["query_tag"], "wh": cell["warehouse"]}
        if a.source == "info":
            lt.validate_ident(a.info_db, "info-db"); lt.validate_ident(cell["warehouse"], "warehouse")
            src = (f"TABLE({a.info_db}.INFORMATION_SCHEMA.QUERY_HISTORY_BY_WAREHOUSE("
                   f"WAREHOUSE_NAME => '{cell['warehouse']}', RESULT_LIMIT => 10000))")
        else:
            src = "SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY"
        rows = q(cur, f"SELECT {PCT} FROM {src} WHERE query_tag = %(tag)s", params)
        m = rows[0] if rows else {}
        if a.source == "info" and m.get("ran_elsewhere") is not None:
            m["ran_elsewhere"] = None  # by-warehouse view cannot see fallback queries; use account_usage pass
        win = (m.get("first_start"), m.get("last_end"))
        if all(win):
            wp = {"wh": cell["warehouse"], "s": str(win[0]), "e": str(win[1])}
            m["cluster_events"] = q(cur, """
                SELECT timestamp, event_name, event_reason, event_state, cluster_number
                FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_EVENTS_HISTORY
                WHERE UPPER(warehouse_name) = UPPER(%(wh)s) AND timestamp BETWEEN %(s)s::timestamp_ltz AND %(e)s::timestamp_ltz
                  AND event_name ILIKE '%%CLUSTER%%' ORDER BY timestamp""", wp)
            m["max_clusters"] = max([e["cluster_number"] or 1 for e in m["cluster_events"]] or [1])
            load = q(cur, """
                SELECT AVG(avg_running) AS avg_running, MAX(avg_running) AS max_running,
                       AVG(avg_queued_load) AS avg_queued, MAX(avg_queued_load) AS max_queued
                FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_LOAD_HISTORY
                WHERE UPPER(warehouse_name) = UPPER(%(wh)s) AND start_time >= DATEADD('minute', -5, %(s)s::timestamp_ltz)
                  AND end_time <= DATEADD('minute', 5, %(e)s::timestamp_ltz)""", wp)
            m["warehouse_load"] = load[0] if load else {}
            cr = q(cur, """
                SELECT SUM(credits_used_compute) AS credits
                FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
                WHERE UPPER(warehouse_name) = UPPER(%(wh)s)
                  AND start_time >= DATE_TRUNC('hour', %(s)s::timestamp_ltz) AND start_time <= %(e)s::timestamp_ltz""", wp)
            m["metered_credits_hour_buckets"] = cr[0]["credits"] if cr else None
        out.append({**{k: cell[k] for k in ("config", "warehouse", "users", "tier", "cache",
                                           "target_qps", "submitted", "modeled_concurrency")}, **m})
    cur.close()
    return out


def agent_side(conn, run, a):
    db, sch, name = run["agent"].split(".")
    cur = conn.cursor()
    out = []
    for t in run["tiers"]:
        p = {"db": db, "sch": sch, "agent": name, "s": t["window_start"], "e": t["window_end"]}
        spans = q(cur, """
            SELECT RECORD:name::string AS span, TRACE:trace_id::string AS trace_id,
                   DATEDIFF('millisecond', START_TIMESTAMP, TIMESTAMP) AS ms,
                   RECORD_ATTRIBUTES:"snow.ai.observability.agent.tool.sql_execution.query_id"::string AS qid
            FROM SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS
            WHERE RECORD_TYPE = 'SPAN'
              AND RECORD_ATTRIBUTES:"snow.ai.observability.database.name"::string = %(db)s
              AND RECORD_ATTRIBUTES:"snow.ai.observability.schema.name"::string = %(sch)s
              AND RECORD_ATTRIBUTES:"snow.ai.observability.object.name"::string = %(agent)s
              AND RECORD_ATTRIBUTES:"snow.ai.observability.run.name" IS NULL
              AND START_TIMESTAMP BETWEEN %(s)s::timestamp_ltz AND %(e)s::timestamp_ltz""", p)
        per = {}
        for s in spans:
            d = per.setdefault(s["trace_id"], {"total": None, "think": 0, "sql": 0})
            if s["span"] == "Agent":
                d["total"] = s["ms"]
            elif s["span"].startswith("ReasoningAgentStep"):
                d["think"] += s["ms"]
            elif s["span"].startswith("SqlExecution"):
                d["sql"] += s["ms"]
        reqs = [d for d in per.values() if d["total"]]
        sql_spans = [s for s in spans if s["span"].startswith("SqlExecution")]
        from datetime import datetime
        win_s = (datetime.fromisoformat(t["window_end"]) - datetime.fromisoformat(t["window_start"])).total_seconds()
        qids = [s["qid"] for s in sql_spans if s["qid"]]
        queue = {}
        if qids:
            ph = ",".join(["%s"] * len(qids[:5000]))
            cur.execute(f"""SELECT AVG(queued_overload_time), APPROX_PERCENTILE(queued_overload_time,.95),
                                   APPROX_PERCENTILE(execution_time,.95), MAX(warehouse_name)
                            FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY WHERE query_id IN ({ph})""", qids[:5000])
            r = cur.fetchone()
            queue = {"queued_avg_ms": r[0], "queued_p95_ms": r[1], "exec_p95_ms": r[2], "warehouse": r[3]}
        out.append({
            "users": t["users"], "client_calls": t["calls"], "client_success_rate": t["success_rate"],
            "traced_requests": len(reqs),
            "server_total_s": lt.summarize([d["total"] / 1000 for d in reqs]),
            "server_think_s": lt.summarize([d["think"] / 1000 for d in reqs]),
            "server_sql_s": lt.summarize([d["sql"] / 1000 for d in reqs]),
            "observed_sql_qps": round(len(sql_spans) / win_s, 3) if win_s else None,
            "observed_sql_concurrency": round(sum(s["ms"] for s in sql_spans) / 1000 / win_s, 2) if win_s else None,
            "sql_queue": queue,
        })
    cur.close()
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--side", choices=["sql", "agent"], required=True)
    ap.add_argument("--run-file", required=True)
    ap.add_argument("--connection", required=True)
    ap.add_argument("--source", choices=["account_usage", "info"], default="account_usage")
    ap.add_argument("--info-db")
    a = ap.parse_args()
    if a.source == "info" and not a.info_db:
        ap.error("--source info requires --info-db")
    run = lt.read_json(a.run_file)
    conn = lt.connect(a.connection)
    res = sql_side(conn, run, a) if a.side == "sql" else agent_side(conn, run, a)
    conn.close()
    path = a.run_file.replace(".json", "_metrics.json")
    lt.write_json(path, {"run_id": run["run_id"], "side": a.side, "source": a.source, "rows": res})
    print(f"wrote {path} ({len(res)} rows)")


if __name__ == "__main__":
    main()
