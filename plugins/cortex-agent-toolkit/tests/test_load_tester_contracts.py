import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/agent-load-tester/scripts"
sys.path.insert(0, str(SCRIPTS))


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lt = load("lt_common")


class LoadModelContracts(unittest.TestCase):
    def test_dish_agent_example(self):
        # Methodology example: 200 users, 1.6 calls, 37.6s/q, no pause, 1.6s/call -> ~8.5 qps, ~13.6 concurrent
        m = lt.LoadModel(200, 1.6, 37.6, 0, 1.6)
        self.assertAlmostEqual(m.sql_arrival_qps, 8.51, places=2)
        self.assertAlmostEqual(m.sql_concurrency, 13.62, places=1)

    def test_pause_lowers_rate(self):
        self.assertLess(lt.LoadModel(100, 2, 30, 30, 1).sql_arrival_qps,
                        lt.LoadModel(100, 2, 30, 0, 1).sql_arrival_qps)

    def test_faster_model_raises_sql_pressure(self):
        self.assertGreater(lt.LoadModel(50, 2, 15, 10, 1).sql_concurrency,
                           lt.LoadModel(50, 2, 40, 10, 1).sql_concurrency)

    def test_zero_cycle_safe(self):
        self.assertEqual(lt.LoadModel(10, 1, 0, 0, 1).sql_arrival_qps, 0.0)

    def test_table_shape(self):
        rows = lt.concurrency_table([10, 200], 1, 10, 0, 1)
        self.assertEqual([r["users"] for r in rows], [10, 200])
        self.assertEqual(rows[1]["sql_qps"], 20.0)


class ScheduleContracts(unittest.TestCase):
    def test_poisson_rate_and_bounds(self):
        s = lt.poisson_schedule(10, 600, seed=1)
        self.assertTrue(all(0 < t < 600 for t in s))
        self.assertEqual(s, sorted(s))
        self.assertAlmostEqual(len(s) / 600, 10, delta=0.6)

    def test_deterministic(self):
        self.assertEqual(lt.poisson_schedule(3, 60, seed=7), lt.poisson_schedule(3, 60, seed=7))

    def test_empty(self):
        self.assertEqual(lt.poisson_schedule(0, 60), [])


class TagContracts(unittest.TestCase):
    def test_roundtrip(self):
        t = lt.make_tag("ab12", "XS_MC", 50, "off")
        self.assertEqual(t, "agent_load:sql:ab12:XS_MC:50:off")
        self.assertEqual(lt.parse_tag(t), {"side": "sql", "run_id": "ab12", "config": "XS_MC", "tier": 50, "cache": "off"})

    def test_rejects_injection(self):
        with self.assertRaises(ValueError):
            lt.make_tag("x'; DROP", "XS", 1, "on")

    def test_parse_foreign_tag(self):
        self.assertIsNone(lt.parse_tag("dbt:model"))


class RewriteContracts(unittest.TestCase):
    M = {"SRC.SCH.T": "DST.LT_INTERACTIVE.T"}

    def test_unquoted_case_insensitive(self):
        self.assertEqual(lt.rewrite_tables("select * from src.sch.t where x=1", self.M),
                         "select * from DST.LT_INTERACTIVE.T where x=1")

    def test_quoted(self):
        self.assertIn("DST.LT_INTERACTIVE.T", lt.rewrite_tables('FROM "SRC"."SCH"."T"', self.M))

    def test_no_partial_match(self):
        sql = "FROM SRC.SCH.T_HISTORY JOIN XSRC.SCH.T"
        self.assertEqual(lt.rewrite_tables(sql, self.M), sql)

    def test_longest_first(self):
        m = {"A.B.C": "X.Y.C", "A.B.CD": "X.Y.CD"}
        self.assertEqual(lt.rewrite_tables("FROM A.B.CD, A.B.C", m), "FROM X.Y.CD, X.Y.C")

    def test_bad_mapping(self):
        with self.assertRaises(ValueError):
            lt.rewrite_tables("x", {"A.B": "X.Y.Z"})


class StatsContracts(unittest.TestCase):
    def test_percentiles(self):
        s = lt.summarize(list(range(1, 101)))
        self.assertEqual(s["n"], 100)
        self.assertAlmostEqual(s["p50"], 50.5)
        self.assertAlmostEqual(s["p95"], 95.05)

    def test_empty(self):
        self.assertEqual(lt.summarize([None]), {"n": 0})


class ProfileContracts(unittest.TestCase):
    def test_span_aggregation(self):
        pw = load("profile_workload")
        rows = []

        def span(rec, name, ms, **kw):
            base = {"run_name": "r1", "record_id": rec, "span": name, "ms": ms, "start_ts": None,
                    "sql_text": None, "query_id": None, "model": None, "tok_in": None, "tok_out": None,
                    "instruction": None, "tool_desc": None, "messages": None}
            base.update(kw); rows.append(base)

        span("a", "Agent", 10000)
        span("a", "ReasoningAgentStepPlanning-0", 4000, model="m1", tok_in=1000, tok_out=50, messages='["User: q1"]')
        span("a", "SqlExecution_SystemSQL", 1000, sql_text="SELECT 1", query_id="q1")
        span("a", "SqlExecution_SystemSQL", 3000, sql_text="SELECT 1", query_id="q2")
        span("a", "ReasoningAgentStepResponseGeneration-1", 1000, model="m1")
        span("b", "Agent", 20000)
        span("b", "ReasoningAgentStepPlanning-0", 18000, model="m1")
        span("b", "SqlExecution_SystemSQL", 15000, sql_text="SELECT 2", query_id="q3")
        span("c", "ReasoningAgentStepPlanning-0", 999)  # no Agent span -> excluded
        profile, sql_rows, prompts, outliers = pw.build(rows, [10], 0, 10)
        self.assertEqual(profile["questions"], 2)
        self.assertEqual(profile["sql_calls_per_question"], 1.5)
        self.assertAlmostEqual(profile["sql_s_per_call"], 19 / 3, places=3)
        self.assertEqual(profile["think_s"]["avg"], (5 + 18) / 2)
        self.assertEqual([o["query_id"] for o in outliers], ["q3"])
        mix = pw.weight_sql(sql_rows, {"q1": {"warehouse_name": "WH"}})
        self.assertEqual(mix[0]["sql"], "SELECT 1")
        self.assertEqual(mix[0]["weight"], 2)
        self.assertEqual(mix[0]["history"]["warehouse_name"], "WH")


class ReportContracts(unittest.TestCase):
    def test_report_builds_from_profile_only(self):
        br = load("build_report")
        with tempfile.TemporaryDirectory() as d:
            prof = {"agent": "D.S.A", "questions": 2, "runs": ["r1"], "models": ["m1"], "source_warehouses": [],
                    "total_s": {"avg": 15, "p50": 15, "p95": 20}, "think_s": {"avg": 11.5, "p50": 11.5, "p95": 17},
                    "sql_s_per_question": {"avg": 3, "p50": 3, "p95": 5}, "other_s": {"avg": 0.5, "p50": 0.5, "p95": 1},
                    "think_pct": 76, "sql_pct": 20, "sql_calls_per_question": 1.5, "sql_s_per_call": 2,
                    "plan_steps_per_question": 1, "pause_s": 0,
                    "modeled_concurrency": lt.concurrency_table([10], 1.5, 15, 0, 2)}
            Path(d, "profile.json").write_text(json.dumps(prof))
            sql = Path(d, "sql_metrics.json")
            sql.write_text(json.dumps({"rows": [{"config": "XS_MC", "warehouse": "LT_XS_MC", "users": 10, "tier": 10,
                                                 "cache": "off", "target_qps": 1, "submitted": 10, "modeled_concurrency": 2,
                                                 "queries": 10, "failed": 0, "elapsed_p95_ms": 2000}]}))
            sys.argv = ["build_report", "--in", d, "--sql", str(sql), "--sla-p95", "30"]
            br.main()
            md = Path(d, "report.md").read_text()
            # 17 think p95 + 0.5 other + 1.5 * 2.0 sql = 20.5
            self.assertIn("20.5†", md)          # no LLM replay -> eval baseline, flagged
            self.assertNotIn("**XS_MC**", md)    # flagged cells are never SLA winners


if __name__ == "__main__":
    unittest.main()
