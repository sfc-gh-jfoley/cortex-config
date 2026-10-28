#!/usr/bin/env python3
"""Phase 2 (Side 1-B) — Replay captured agent LLM steps against candidate models at concurrency.

Each simulated user replays one eval question's chain of LLM steps (planning steps, then response
generation) sequentially, as the agent would, then pauses and picks another question (closed loop).
Prompts are reconstructed from telemetry: instruction + tool descriptions + messages, padded to the
recorded input token count (prefill cost dominates latency), max_tokens = recorded output tokens.
This is DIRECTIONAL: it excludes agent orchestration overhead and tool round trips.

Usage:
  SNOWFLAKE_PAT="<snowflake_pat>" python llm_replay.py --connection default --in ./lt_out \
      --models claude-sonnet-4-5,claude-haiku-4-5 --tiers 10,25,50 --duration 120 [--pause 30]
      [--include-sql-sleep] [--max-requests 2000] [--no-pad]
Writes: <in>/llm_replay_<run_id>.json
"""

import argparse
import asyncio
import json
import os
import random
import sys
import time
import uuid
from collections import defaultdict

import httpx

sys.path.insert(0, os.path.dirname(__file__))
import lt_common as lt

CHARS_PER_TOKEN = 4
FILLER = ("Context record: subscriber metrics, churn indicators, network events, billing summaries. ")


def load_questions(path):
    steps = defaultdict(list)
    with open(path) as f:
        for line in f:
            p = json.loads(line)
            steps[(p["run"], p["record_id"])].append(p)
    return [v for v in steps.values() if v]


def build_prompt(step, pad):
    parts = []
    if step.get("instruction"):
        parts.append(f"Instructions:\n{step['instruction']}")
    if step.get("tool_desc"):
        parts.append(f"Tools:\n{json.dumps(step['tool_desc'], default=str)[:20000]}")
    user = step.get("messages") or "Summarize the results for the user."
    sys_text = "\n\n".join(parts) or "You are a data analysis agent."
    target = (step.get("tok_in") or 0) * CHARS_PER_TOKEN
    cur = len(sys_text) + len(user)
    if pad and target > cur:
        sys_text += "\n\n" + (FILLER * ((target - cur) // len(FILLER) + 1))[: target - cur]
    return sys_text, user, len(sys_text) + len(user)


async def call_model(client, url, headers, model, step, pad):
    sys_text, user, chars = build_prompt(step, pad)
    body = {"model": model, "stream": True, "max_tokens": max(16, min(step.get("tok_out") or 512, 4096)),
            "messages": [{"role": "system", "content": sys_text}, {"role": "user", "content": user}]}
    t0 = time.perf_counter(); ttft = None; status = None; err = None; out_chars = 0
    try:
        async with client.stream("POST", url, headers=headers, json=body) as r:
            status = r.status_code
            if status != 200:
                err = (await r.aread()).decode(errors="ignore")[:300]
            else:
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    if ttft is None:
                        ttft = time.perf_counter() - t0
                    out_chars += len(line)
    except Exception as e:  # network/timeout
        err = f"{type(e).__name__}: {e}"[:300]
    return {"kind": step["kind"], "status": status, "error": err, "ttft_s": ttft,
            "total_s": time.perf_counter() - t0, "prompt_chars": chars,
            "recorded_tok_in": step.get("tok_in"), "recorded_ms": step.get("ms"), "out_chars": out_chars}


async def run_tier(model, users, questions, a, url, headers, budget):
    results, qtimes = [], []
    deadline = time.monotonic() + a.duration
    limits = httpx.Limits(max_connections=users + 10, max_keepalive_connections=users + 10)
    async with httpx.AsyncClient(timeout=a.timeout, limits=limits) as client:
        async def user_loop(uid):
            rnd = random.Random(uid)
            await asyncio.sleep(rnd.uniform(0, min(a.pause, 10)))  # stagger start
            while time.monotonic() < deadline and budget[0] > 0:
                q = rnd.choice(questions)
                t0 = time.perf_counter(); ok = True
                for step in q:
                    if budget[0] <= 0 or time.monotonic() >= deadline:
                        return
                    budget[0] -= 1
                    r = await call_model(client, url, headers, model, step, not a.no_pad)
                    r["user"] = uid; results.append(r)
                    if r["status"] != 200:
                        ok = False
                        break
                    if a.include_sql_sleep and step["kind"] == "planning":
                        await asyncio.sleep(a.sql_sleep_s)
                if ok:
                    qtimes.append(time.perf_counter() - t0)
                await asyncio.sleep(rnd.expovariate(1 / a.pause) if a.pause > 0 else 0)
        await asyncio.gather(*(user_loop(i) for i in range(users)))
    ok = [r for r in results if r["status"] == 200]
    return {
        "model": model, "users": users, "requests": len(results),
        "success_rate": round(len(ok) / len(results), 4) if results else None,
        "http_429": sum(r["status"] == 429 for r in results),
        "http_5xx": sum((r["status"] or 0) >= 500 for r in results),
        "errors": sum(r["status"] is None for r in results),
        "ttft_s": lt.summarize([r["ttft_s"] for r in ok]),
        "step_total_s": lt.summarize([r["total_s"] for r in ok]),
        "planning_step_s": lt.summarize([r["total_s"] for r in ok if r["kind"] == "planning"]),
        "response_step_s": lt.summarize([r["total_s"] for r in ok if r["kind"] == "response"]),
        "think_s_per_question": lt.summarize(qtimes),
        "sample_errors": list({r["error"] for r in results if r["error"]})[:5],
    }


async def main_async(a):
    conn = lt.connect(a.connection)
    base, token = lt.base_url_and_token(conn)  # conn stays open: session token lives with it
    url = f"{base}/api/v2/cortex/inference:complete"
    headers = {"Authorization": f'Snowflake Token="{token}"', "Content-Type": "application/json",
               "Accept": "text/event-stream"}
    questions = load_questions(os.path.join(a.inp, "prompts.jsonl"))
    prof = os.path.join(a.inp, "profile.json")
    a.sql_sleep_s = lt.read_json(prof)["sql_s_per_call"] if os.path.exists(prof) else 1.0
    if not questions:
        raise SystemExit("prompts.jsonl is empty — run profile_workload.py first")
    budget = [a.max_requests]
    run_id = a.run_id or uuid.uuid4().hex[:8]
    out = {"run_id": run_id, "side": "llm_replay", "directional": True, "pause_s": a.pause,
           "duration_s": a.duration, "padded": not a.no_pad, "tiers": []}
    for model in a.models.split(","):
        async with httpx.AsyncClient(timeout=a.timeout) as c:
            pf = await call_model(c, url, headers, model, questions[0][0], not a.no_pad)
        if pf["status"] != 200:
            print(f"[preflight] {model} FAILED status={pf['status']} {pf['error']}")
            out["tiers"].append({"model": model, "preflight_failed": pf})
            continue
        print(f"[preflight] {model} ok ttft={pf['ttft_s']:.2f}s total={pf['total_s']:.2f}s")
        for users in [int(x) for x in a.tiers.split(",")]:
            if budget[0] <= 0:
                out["stopped"] = "max-requests budget exhausted"; break
            print(f"[llm_replay] model={model} users={users} ...", flush=True)
            r = await run_tier(model, users, questions, a, url, headers, budget)
            out["tiers"].append(r)
            p = r["think_s_per_question"]
            print(f"   success={r['success_rate']} 429s={r['http_429']} think/q p50={p.get('p50')} p95={p.get('p95')}")
            if a.stop_on_throttle and r["success_rate"] is not None and r["success_rate"] < a.stop_on_throttle:
                print(f"   success below {a.stop_on_throttle}; skipping higher tiers for {model}")
                break
            await asyncio.sleep(a.cooldown)
    path = os.path.join(a.inp, f"llm_replay_{run_id}.json")
    lt.write_json(path, out)
    print(f"wrote {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--connection", required=True)
    ap.add_argument("--in", dest="inp", default="./lt_out")
    ap.add_argument("--models", required=True, help="comma list, e.g. claude-sonnet-4-5,claude-haiku-4-5")
    ap.add_argument("--tiers", default="10,25,50,100,200")
    ap.add_argument("--duration", type=float, default=120, help="seconds per tier")
    ap.add_argument("--pause", type=float, default=30, help="mean user pause between questions (s)")
    ap.add_argument("--timeout", type=float, default=180)
    ap.add_argument("--cooldown", type=float, default=15)
    ap.add_argument("--max-requests", type=int, default=2000, help="hard cap across all tiers/models")
    ap.add_argument("--stop-on-throttle", type=float, default=0.8, help="skip higher tiers below this success rate")
    ap.add_argument("--include-sql-sleep", action="store_true")
    ap.add_argument("--no-pad", action="store_true", help="do not pad prompts to recorded input tokens")
    ap.add_argument("--run-id")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
