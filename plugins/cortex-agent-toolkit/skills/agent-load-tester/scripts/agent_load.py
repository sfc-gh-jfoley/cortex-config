#!/usr/bin/env python3
"""Phase 3 (Side 1-A) — Real concurrent agent:run calls (deep introspection + model validation).

Closed-loop users stream agent:run with questions from the eval dataset (or the questions captured
in prompts.jsonl), pause, repeat. Records client TTFT/total/status per call and the time window so
collect_metrics.py --side agent can pull the server-side span breakdown (think vs SQL under load)
and the actual SQL concurrency the agent produced.

Never alters the agent. To compare models, point --agent at clones (e.g. <AGENT>_LT_HAIKU).

Usage:
  SNOWFLAKE_PAT="<snowflake_pat>" python agent_load.py --connection default --agent DB.SCH.AGENT \
      --in ./lt_out --tiers 25 --duration 180 [--pause 30] [--questions-table DB.SCH.EVAL --question-col INPUT_QUERY]
      [--max-calls 300]
Writes: <in>/agent_load_<run_id>.json
"""

import argparse
import asyncio
import json
import os
import random
import sys
import time
import uuid
from datetime import datetime, timezone

import httpx

sys.path.insert(0, os.path.dirname(__file__))
import lt_common as lt


def questions_from_table(conn, table, col):
    lt.validate_fqn(table, "questions table"); lt.validate_ident(col, "question column")
    cur = conn.cursor()
    cur.execute(f"SELECT DISTINCT {col} FROM {table} WHERE {col} IS NOT NULL")
    qs = [r[0] if isinstance(r[0], str) else json.dumps(r[0]) for r in cur.fetchall()]
    cur.close()
    return qs


def questions_from_prompts(path):
    seen = set()
    with open(path) as f:
        for line in f:
            p = json.loads(line)
            if p["kind"] != "planning" or not p.get("messages"):
                continue
            try:
                msgs = json.loads(p["messages"])
                text = msgs[0] if isinstance(msgs, list) and msgs else p["messages"]
            except (ValueError, TypeError):
                text = p["messages"]
            text = str(text).removeprefix("User: ").strip()
            if text:
                seen.add(text)
    return sorted(seen)


async def call_agent(client, url, headers, question):
    body = {"messages": [{"role": "user", "content": [{"type": "text", "text": question}]}]}
    t0 = time.perf_counter(); ttft = None; status = None; err = None; tools = 0; sql_calls = 0
    req_id = None; event = None
    try:
        async with client.stream("POST", url, headers=headers, json=body) as r:
            status = r.status_code
            req_id = r.headers.get("x-snowflake-request-id") or r.headers.get("x-request-id")
            if status != 200:
                err = (await r.aread()).decode(errors="ignore")[:300]
            else:
                async for line in r.aiter_lines():
                    if line.startswith("event:"):
                        event = line[6:].strip()
                        if event == "response.text.delta" and ttft is None:
                            ttft = time.perf_counter() - t0
                        if event == "response.tool_use":
                            tools += 1
                    elif line.startswith("data:") and event == "response.tool_result" and '"sql"' in line:
                        sql_calls += 1
                    elif line.startswith("data:") and event == "error":
                        err = line[5:300]
    except Exception as e:
        err = f"{type(e).__name__}: {e}"[:300]
    return {"status": status, "error": err, "ttft_s": ttft, "total_s": time.perf_counter() - t0,
            "tool_uses": tools, "sql_results": sql_calls, "request_id": req_id}


async def run_tier(users, questions, a, url, headers, budget):
    results = []
    start = datetime.now(timezone.utc)
    deadline = time.monotonic() + a.duration
    limits = httpx.Limits(max_connections=users + 10, max_keepalive_connections=users + 10)
    async with httpx.AsyncClient(timeout=a.timeout, limits=limits) as client:
        async def user_loop(uid):
            rnd = random.Random(1000 + uid)
            await asyncio.sleep(rnd.uniform(0, min(a.pause, 10)))
            while time.monotonic() < deadline and budget[0] > 0:
                budget[0] -= 1
                r = await call_agent(client, url, headers, rnd.choice(questions))
                r["user"] = uid; results.append(r)
                await asyncio.sleep(rnd.expovariate(1 / a.pause) if a.pause > 0 else 0)
        await asyncio.gather(*(user_loop(i) for i in range(users)))
    end = datetime.now(timezone.utc)
    ok = [r for r in results if r["status"] == 200 and not r["error"]]
    return {"users": users, "window_start": start.isoformat(), "window_end": end.isoformat(),
            "calls": len(results), "success_rate": round(len(ok) / len(results), 4) if results else None,
            "http_429": sum(r["status"] == 429 for r in results),
            "http_5xx": sum((r["status"] or 0) >= 500 for r in results),
            "ttft_s": lt.summarize([r["ttft_s"] for r in ok]),
            "total_s": lt.summarize([r["total_s"] for r in ok]),
            "sql_results_per_call": round(sum(r["sql_results"] for r in ok) / len(ok), 2) if ok else None,
            "sample_errors": list({r["error"] for r in results if r["error"]})[:5],
            "request_ids": [r["request_id"] for r in results if r["request_id"]]}


async def main_async(a):
    lt.validate_fqn(a.agent, "agent")
    db, sch, name = a.agent.split(".")
    conn = lt.connect(a.connection)
    base, token = lt.base_url_and_token(conn)
    questions = (questions_from_table(conn, a.questions_table, a.question_col) if a.questions_table
                 else questions_from_prompts(os.path.join(a.inp, "prompts.jsonl")))
    if not questions:
        raise SystemExit("No questions found (eval table or prompts.jsonl)")
    url = f"{base}/api/v2/databases/{db}/schemas/{sch}/agents/{name}:run"
    headers = {"Authorization": f'Snowflake Token="{token}"', "Content-Type": "application/json",
               "Accept": "text/event-stream"}
    run_id = a.run_id or uuid.uuid4().hex[:8]
    budget = [a.max_calls]
    out = {"run_id": run_id, "side": "agent_live", "agent": a.agent, "pause_s": a.pause,
           "questions": len(questions), "tiers": []}
    for users in [int(x) for x in a.tiers.split(",")]:
        if budget[0] <= 0:
            out["stopped"] = "max-calls budget exhausted"; break
        print(f"[agent_load] {a.agent} users={users} ...", flush=True)
        r = await run_tier(users, questions, a, url, headers, budget)
        out["tiers"].append(r)
        print(f"   calls={r['calls']} success={r['success_rate']} 429s={r['http_429']} "
              f"total p50={r['total_s'].get('p50')} p95={r['total_s'].get('p95')}")
        await asyncio.sleep(a.cooldown)
    path = os.path.join(a.inp, f"agent_load_{run_id}.json")
    lt.write_json(path, out)
    print(f"wrote {path}\nNext: python collect_metrics.py --side agent --run-file {path} --connection {a.connection}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--connection", required=True)
    ap.add_argument("--agent", required=True)
    ap.add_argument("--in", dest="inp", default="./lt_out")
    ap.add_argument("--tiers", default="25")
    ap.add_argument("--duration", type=float, default=180)
    ap.add_argument("--pause", type=float, default=30)
    ap.add_argument("--timeout", type=float, default=300)
    ap.add_argument("--cooldown", type=float, default=30)
    ap.add_argument("--max-calls", type=int, default=300)
    ap.add_argument("--questions-table")
    ap.add_argument("--question-col", default="INPUT_QUERY")
    ap.add_argument("--run-id")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
