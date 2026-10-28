#!/usr/bin/env python3
"""Phase 4 (Side 2) — Open-loop replay of captured agent SQL against warehouse configs. No LLM.

For each config x tier x cache mode: warm up, then submit queries from the weighted SQL mix at the
modeled SQL arrival rate (Poisson arrivals, execute_async — the client never waits on the warehouse,
so queueing shows up server-side like real agent traffic). Every query carries
QUERY_TAG = agent_load:sql:<run_id>:<config>:<tier>:<cache>; collect_metrics.py measures server-side.

configs.json:
  [{"name": "XS_MC", "warehouse": "LT_XS_MC"},
   {"name": "S_MC",  "warehouse": "LT_S_MC"},
   {"name": "IWH",   "warehouse": "LT_IWH", "table_map": {"SRC.SCH.T": "SRC.LT_INTERACTIVE.T"}}]

Usage:
  python sql_replay.py --connection default --in ./lt_out --configs configs.json \
      --tiers 10,25,50,100,200 --duration 180 --cache on,off [--question-s 25] [--pause 30]
      [--rate-scale 1.0] [--max-queries 20000] [--dry-run]
Writes: <in>/sql_replay_<run_id>.json
"""

import argparse
import json
import os
import random
import sys
import threading
import time
import uuid
import zlib
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(__file__))
import lt_common as lt


def load_mix(path, top, max_avg_ms=None):
    with open(path) as f:
        mix = [json.loads(l) for l in f]
    if max_avg_ms:
        mix = [m for m in mix if m["avg_ms"] < max_avg_ms]
    return mix[:top] if top else mix


def tier_rates(profile, tiers, question_s, pause_s, scale):
    q_s = question_s if question_s else profile["total_s"]["avg"]
    p_s = profile["pause_s"] if pause_s is None else pause_s
    rows = lt.concurrency_table(tiers, profile["sql_calls_per_question"], q_s, p_s, profile["sql_s_per_call"])
    for r in rows:
        r["sql_qps"] = round(r["sql_qps"] * scale, 4)
    return rows, q_s, p_s


class Pool:
    """Round-robin connections, one session config per (warehouse, tag, cache)."""

    def __init__(self, connection, size, context_schema=None):
        """context_schema = agent DB.SCHEMA so unqualified names in agent SQL resolve as they did live."""
        kw = {}
        if context_schema:
            db, sch = context_schema.split(".")
            kw = {"database": lt.validate_ident(db, "database"), "schema": lt.validate_ident(sch, "schema")}
        self.conns = [lt.connect(connection, **kw) for _ in range(size)]
        self.i = 0; self.lock = threading.Lock()

    def configure(self, warehouse, tag, cache_on):
        lt.validate_ident(warehouse, "warehouse")
        for c in self.conns:
            cur = c.cursor()
            cur.execute(f"USE WAREHOUSE {warehouse}")
            cur.execute("ALTER SESSION SET QUERY_TAG = %s", (tag,))
            cur.execute(f"ALTER SESSION SET USE_CACHED_RESULT = {'TRUE' if cache_on else 'FALSE'}")
            cur.close()

    def submit(self, sql):
        with self.lock:
            c = self.conns[self.i % len(self.conns)]; self.i += 1
        cur = c.cursor()
        res = cur.execute_async(sql)
        cur.close()
        return res.get("queryId") if isinstance(res, dict) else None

    def wait_all(self, qids, timeout_s):
        deadline = time.monotonic() + timeout_s
        pending = set(q for q in qids if q)
        c = self.conns[0]
        while pending and time.monotonic() < deadline:
            for q in list(pending):
                try:
                    if not c.is_still_running(c.get_query_status(q)):
                        pending.discard(q)
                except Exception:
                    pending.discard(q)
            if pending:
                time.sleep(2)
        return len(pending)

    def close(self):
        for c in self.conns:
            c.close()


def weighted_choice(rnd, cum, total):
    x = rnd.uniform(0, total)
    lo, hi = 0, len(cum) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if cum[mid] < x:
            lo = mid + 1
        else:
            hi = mid
    return lo


def run_cell(pool, mix, cfg, tier, rate, cache, a, run_id, budget):
    tag = lt.make_tag(run_id, cfg["name"], tier, cache)
    pool.configure(cfg["warehouse"], tag, cache == "on")
    sqls = [lt.rewrite_tables(m["sql"], cfg.get("table_map") or {}) for m in mix]
    cum, s = [], 0
    for m in mix:
        s += m["weight"]; cum.append(s)
    sched = lt.poisson_schedule(rate, a.duration, seed=zlib.crc32(f"{cfg['name']}:{tier}:{cache}".encode()))
    sched = sched[: max(0, budget[0])]
    budget[0] -= len(sched)
    rnd = random.Random(tier)
    qids, errors, late = [], [], 0
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=a.submitters) as ex:
        futs = []
        for off in sched:
            delay = t0 + off - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            elif delay < -1:
                late += 1
            futs.append(ex.submit(pool.submit, sqls[weighted_choice(rnd, cum, s)]))
        for f in futs:
            try:
                qids.append(f.result())
            except Exception as e:
                errors.append(str(e)[:200])
    unfinished = pool.wait_all(qids, a.drain_timeout)
    return {"config": cfg["name"], "warehouse": cfg["warehouse"], "tier": tier, "cache": cache,
            "target_qps": rate, "submitted": len(qids), "submit_errors": len(errors),
            "late_submissions": late, "unfinished_after_drain": unfinished, "query_tag": tag,
            "sample_errors": errors[:3]}


def validate_mix(pool, mix, cfg, workers=8):
    """EXPLAIN every (rewritten) SQL; drop ones that no longer compile (schema drift since the eval)."""
    def check(m):
        c = pool.conns[hash(m["id"]) % len(pool.conns)]
        cur = c.cursor()
        try:
            cur.execute("EXPLAIN " + lt.rewrite_tables(m["sql"], cfg.get("table_map") or {}))
            return None
        except Exception as e:
            return {"id": m["id"], "weight": m["weight"], "error": str(e).splitlines()[-1][:200]}
        finally:
            cur.close()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        bad = [b for b in ex.map(check, mix) if b]
    bad_ids = {b["id"] for b in bad}
    return [m for m in mix if m["id"] not in bad_ids], bad


def warmup(pool, mix, cfg, run_id, n):
    pool.configure(cfg["warehouse"], lt.make_tag(run_id, cfg["name"], 0, "warm"), True)
    qids = [pool.submit(lt.rewrite_tables(m["sql"], cfg.get("table_map") or {})) for m in mix[:n]]
    pool.wait_all(qids, 600)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--connection", required=True)
    ap.add_argument("--in", dest="inp", default="./lt_out")
    ap.add_argument("--configs", required=True)
    ap.add_argument("--tiers", default="10,25,50,100,200")
    ap.add_argument("--duration", type=float, default=180, help="steady-state seconds per cell")
    ap.add_argument("--cache", default="on,off")
    ap.add_argument("--question-s", type=float, help="override end-to-end question time (e.g. from llm_replay what-if)")
    ap.add_argument("--pause", type=float, help="override user pause (s); default from profile")
    ap.add_argument("--rate-scale", type=float, default=1.0)
    ap.add_argument("--top-sql", type=int, default=0, help="limit to N most frequent SQL")
    ap.add_argument("--exclude-over-ms", type=float, help="drop SQL whose eval avg >= this (outliers to tune first)")
    ap.add_argument("--connections", type=int, default=4)
    ap.add_argument("--submitters", type=int, default=16)
    ap.add_argument("--drain-timeout", type=float, default=900)
    ap.add_argument("--cooldown", type=float, default=30)
    ap.add_argument("--max-queries", type=int, default=20000)
    ap.add_argument("--no-warmup", action="store_true")
    ap.add_argument("--context-schema", help="DB.SCHEMA for unqualified names (default: agent's)")
    ap.add_argument("--no-validate", action="store_true", help="skip EXPLAIN pre-validation")
    ap.add_argument("--warmup-n", type=int, default=100, help="warm the N most frequent SQL per config")
    ap.add_argument("--dry-run", action="store_true", help="print schedule sizes, submit nothing")
    ap.add_argument("--run-id")
    a = ap.parse_args()

    profile = lt.read_json(os.path.join(a.inp, "profile.json"))
    mix = load_mix(os.path.join(a.inp, "sql_mix.jsonl"), a.top_sql, a.exclude_over_ms)
    configs = lt.read_json(a.configs)
    tiers = [int(x) for x in a.tiers.split(",")]
    caches = a.cache.split(",")
    rates, q_s, p_s = tier_rates(profile, tiers, a.question_s, a.pause, a.rate_scale)
    run_id = a.run_id or uuid.uuid4().hex[:8]

    plan = [{"config": c["name"], **r, "cache": k, "expected_queries": int(r["sql_qps"] * a.duration)}
            for c in configs for r in rates for k in caches]
    total = sum(p["expected_queries"] for p in plan)
    print(f"run_id={run_id} question_s={q_s:.1f} pause_s={p_s} distinct_sql={len(mix)} "
          f"cells={len(plan)} expected_queries={total} (cap {a.max_queries})")
    for p in plan:
        print(f"  {p['config']:<8} users={p['users']:>4} cache={p['cache']:<3} {p['sql_qps']:>7.2f} qps "
              f"~{p['sql_concurrency']:.1f} conc  {p['expected_queries']} queries")
    if a.dry_run:
        return

    pool = Pool(a.connection, a.connections, a.context_schema or ".".join(profile["agent"].split(".")[:2]))
    budget = [a.max_queries]
    out = {"run_id": run_id, "side": "sql_replay", "question_s": q_s, "pause_s": p_s,
           "duration_s": a.duration, "distinct_sql": len(mix), "cells": []}
    try:
        base_mix = mix
        for cfg in configs:
            mix = base_mix
            if not a.no_validate:
                mix, bad = validate_mix(pool, base_mix, cfg)
                w_bad, w_all = sum(b["weight"] for b in bad), sum(m["weight"] for m in base_mix)
                print(f"[validate] {cfg['name']}: dropped {len(bad)}/{len(base_mix)} SQL "
                      f"({100 * w_bad / w_all:.1f}% of traffic) that no longer compile", flush=True)
                out.setdefault("validation", {})[cfg["name"]] = {"dropped": len(bad), "dropped_traffic_pct": round(100 * w_bad / w_all, 2),
                                                                "sample": bad[:10]}
            if not a.no_warmup:
                print(f"[warmup] {cfg['name']}", flush=True)
                warmup(pool, mix, cfg, run_id, a.warmup_n)
            for r in rates:
                for cache in caches:
                    if budget[0] <= 0:
                        out["stopped"] = "max-queries budget exhausted"; break
                    print(f"[sql_replay] {cfg['name']} users={r['users']} cache={cache} {r['sql_qps']} qps", flush=True)
                    cell = run_cell(pool, mix, cfg, r["users"], r["sql_qps"], cache, a, run_id, budget)
                    cell.update({"users": r["users"], "modeled_concurrency": r["sql_concurrency"]})
                    out["cells"].append(cell)
                    lt.write_json(os.path.join(a.inp, f"sql_replay_{run_id}.json"), out)
                    time.sleep(a.cooldown)
    finally:
        pool.close()
    path = os.path.join(a.inp, f"sql_replay_{run_id}.json")
    lt.write_json(path, out)
    print(f"wrote {path}\nNext: python collect_metrics.py --side sql --run-file {path} --connection {a.connection}")


if __name__ == "__main__":
    main()
