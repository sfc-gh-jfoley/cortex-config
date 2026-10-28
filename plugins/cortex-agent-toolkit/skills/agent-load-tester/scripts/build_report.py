#!/usr/bin/env python3
"""Phase 5 — Combine both sides into a markdown report with sizing + tuning guidance.

Predicted end-to-end p95 per (model, config, tier) =
    think p95 (llm_replay for that model+tier, else profile think p95)
  + other avg (profile; orchestration/tool overhead)
  + sql_calls_per_question x SQL elapsed p95 (sql_replay metrics, cache mode chosen by --cache)

Usage:
  python build_report.py --in ./lt_out [--llm lt_out/llm_replay_X.json] [--sql lt_out/sql_replay_Y_metrics.json]
         [--agent lt_out/agent_load_Z_metrics.json] [--sla-p95 20] [--cache off] [--out lt_out/report.md]
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import lt_common as lt


def f(x, nd=2):
    return "-" if x is None else (f"{x:.{nd}f}" if isinstance(x, (int, float)) else str(x))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", default="./lt_out")
    ap.add_argument("--llm", action="append", default=[])
    ap.add_argument("--sql")
    ap.add_argument("--agent")
    ap.add_argument("--sla-p95", type=float, help="end-to-end p95 target (s)")
    ap.add_argument("--cache", default="off", help="cache mode used for prediction (off = worst case)")
    ap.add_argument("--out")
    a = ap.parse_args()

    P = lt.read_json(os.path.join(a.inp, "profile.json"))
    outliers = lt.read_json(os.path.join(a.inp, "outliers.json")) if os.path.exists(os.path.join(a.inp, "outliers.json")) else []
    L = [lt.read_json(p) for p in a.llm]
    S = lt.read_json(a.sql)["rows"] if a.sql else []
    A = lt.read_json(a.agent)["rows"] if a.agent else []
    md = [f"# Agent Load Test — {P['agent']}", "",
          f"Eval questions profiled: {P['questions']} across {len(P['runs'])} run(s). Models: {', '.join(P['models']) or '-'}. "
          f"Source warehouse(s): {', '.join(P['source_warehouses']) or '-'}.", "",
          "## 1. Baseline profile (single-user eval telemetry)", "",
          "| Metric | avg | p50 | p95 |", "|---|---|---|---|"]
    for k, lbl in (("total_s", "Total s"), ("think_s", "Think s (LLM)"), ("sql_s_per_question", "SQL s / question"), ("other_s", "Other s")):
        s = P[k]; md.append(f"| {lbl} | {f(s.get('avg'))} | {f(s.get('p50'))} | {f(s.get('p95'))} |")
    md += ["", f"Think {P['think_pct']}% · SQL {P['sql_pct']}% · {P['sql_calls_per_question']} SQL calls/question · "
               f"{P['sql_s_per_call']}s per SQL call · {P['plan_steps_per_question']} planning steps/question · user pause {P['pause_s']}s", "",
           "### Modeled SQL load (think time paces the warehouse)", "",
           "| Users | Questions/s | SQL/s | Concurrent SQL |", "|---|---|---|---|"]
    md += [f"| {r['users']} | {r['questions_per_s']} | {r['sql_qps']} | {r['sql_concurrency']} |" for r in P["modeled_concurrency"]]
    if outliers:
        md += ["", f"**{len(outliers)} SQL executions ≥ outlier threshold — tune these before sizing** "
                   "(route to `workload-performance-analysis`):", ""]
        md += [f"- `{o['query_id']}` {o['duration_ms']/1000:.1f}s — `{o['sql'][:120].replace(chr(10), ' ')}…`" for o in outliers[:10]]

    think_by = {}
    if L:
        md += ["", "## 2. Side 1-B — LLM replay (directional)", "",
               "| Model | Users | Requests | Success | 429s | TTFT p50 | Step p95 | Think/question p50 | p95 |",
               "|---|---|---|---|---|---|---|---|---|"]
        for run in L:
            for t in run["tiers"]:
                if "preflight_failed" in t:
                    md.append(f"| {t['model']} | - | preflight failed: {t['preflight_failed']['error'][:60]} |||||||"); continue
                tq = t["think_s_per_question"]
                think_by[(t["model"], t["users"])] = tq.get("p95")
                md.append(f"| {t['model']} | {t['users']} | {t['requests']} | {f(t['success_rate'])} | {t['http_429']} | "
                          f"{f(t['ttft_s'].get('p50'))} | {f(t['step_total_s'].get('p95'))} | {f(tq.get('p50'))} | {f(tq.get('p95'))} |")
        md += ["", "_Prompts reconstructed from telemetry and padded to recorded input tokens; excludes orchestration and tool round trips._"]

    if A:
        md += ["", "## 3. Side 1-A — Live agent calls", "",
               "| Users | Calls | Success | Server total p95 | Think p95 | SQL p95 | Observed SQL/s | Observed conc | Modeled conc | SQL queued p95 ms |",
               "|---|---|---|---|---|---|---|---|---|---|"]
        mod = {r["users"]: r["sql_concurrency"] for r in P["modeled_concurrency"]}
        for r in A:
            md.append(f"| {r['users']} | {r['client_calls']} | {f(r['client_success_rate'])} | {f(r['server_total_s'].get('p95'))} | "
                      f"{f(r['server_think_s'].get('p95'))} | {f(r['server_sql_s'].get('p95'))} | {f(r['observed_sql_qps'])} | "
                      f"{f(r['observed_sql_concurrency'])} | {f(mod.get(r['users']))} | {f(r['sql_queue'].get('queued_p95_ms'), 0)} |")
        md += ["", "_Model check: observed vs modeled SQL concurrency within ~25% means Phase 4 rates are trustworthy._"]

    if S:
        md += ["", "## 4. Side 2 — SQL replay (server-side)", "",
               "| Config | Users | Cache | Target SQL/s | Queries | Failed | Elsewhere | Elapsed p50 ms | p95 | p99 | Queued p95 ms | Queued # | Max clusters | Cache hit % |",
               "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in S:
            md.append(f"| {r['config']} | {r['users']} | {r['cache']} | {f(r['target_qps'])} | {r.get('queries')} | {r.get('failed')} | "
                      f"{f(r.get('ran_elsewhere'), 0)} | {f(r.get('elapsed_p50_ms'), 0)} | {f(r.get('elapsed_p95_ms'), 0)} | "
                      f"{f(r.get('elapsed_p99_ms'), 0)} | {f(r.get('queued_p95_ms'), 0)} | {r.get('queued_queries')} | "
                      f"{r.get('max_clusters', '-')} | {f(r.get('result_cache_pct'), 1)} |")
        md += ["", "_Elsewhere = queries tagged for the config that ran on another warehouse (Interactive 5s-limit fallback)._"]

        # predicted end-to-end
        models = sorted({m for m, _ in think_by}) or ["(profile)"]
        md += ["", f"## 5. Predicted end-to-end p95 (cache {a.cache})", ""]
        hdr = "| Model | Config | " + " | ".join(f"{u} users" for u in sorted({r['users'] for r in S})) + " |"
        md += [hdr, "|" + "---|" * (hdr.count("|") - 1)]
        users = sorted({r["users"] for r in S})
        winners = {}
        for m in models:
            for cfg in sorted({r["config"] for r in S}):
                cells = []
                for u in users:
                    row = next((r for r in S if r["config"] == cfg and r["users"] == u and r["cache"] == a.cache), None)
                    if not row or row.get("elapsed_p95_ms") is None:
                        cells.append("-"); continue
                    think, mark = think_by.get((m, u)), ""
                    if think is None:
                        lower = sorted(t for (mm, t) in think_by if mm == m and t <= u)
                        think, mark = (think_by[(m, lower[-1])], "*") if lower else (P["think_s"]["p95"], "†")
                    e2e = think + P["other_s"]["avg"] + P["sql_calls_per_question"] * row["elapsed_p95_ms"] / 1000
                    ok = a.sla_p95 is None or e2e <= a.sla_p95
                    if ok and not mark:
                        winners.setdefault((m, u), cfg)
                    cells.append(f"{e2e:.1f}{mark}{'' if ok else ' ✗'}")
                md.append(f"| {m} | {cfg} | " + " | ".join(cells) + " |")
        md += ["", "_`*` think time extrapolated from the model's highest measured lower tier (LLM load not measured here — "
                   "optimistic if throttling starts above it). `†` no LLM replay for this model; eval-baseline think p95. "
                   "Extrapolated cells never count as SLA winners._"]
        if a.sla_p95:
            md += ["", f"SLA p95 ≤ {a.sla_p95}s. First passing config per model/tier (configs listed smallest-first in configs.json):", ""]
            md += [f"- {m} @ {u} users → **{c}**" for (m, u), c in sorted(winners.items())]

    md += ["", "## 6. Tuning handoff", "",
           "| Side | Signal | Route to |", "|---|---|---|",
           "| SQL | Outliers, high exec p95, spill, poor pruning | `workload-performance-analysis` (clustering, SOS, QAS, spill) |",
           "| SQL | Queued time rising with users, cluster ceiling hit | `warehouse` (size, MAX_CLUSTER_COUNT, scaling policy, Gen2) |",
           "| SQL | Selective repeated shapes, sub-second target | `snowflake-interactive` (interactive tables + WH) |",
           "| LLM | Think p95 dominates, 429s at target tier | `agent-model-tester` (smaller orchestration model; must pass eval gate) |",
           "| LLM | Many planning steps / question | `agent-instruction-optimizer`, `agent-optimizer` |",
           "", "> A faster model raises SQL arrival rate. After any Side 1 change, re-run sql_replay with `--question-s <new e2e>`."]
    path = a.out or os.path.join(a.inp, "report.md")
    open(path, "w").write("\n".join(md) + "\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
