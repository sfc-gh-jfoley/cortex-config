import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import mutate  # noqa: E402
import population_state as ps  # noqa: E402
import sample_batch  # noqa: E402

SRC = "DB.SCH.SV"
CAND = "DB.SCH.SV__GEPA__R1A2B3C__G1__C1"


def run(script, *args):
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args], capture_output=True, text=True)


def init_state(tmp, baseline=0.5):
    r = run("population_state.py", "init", tmp, "--pop-size", "4", "--agent-name", "SV",
            "--source-fqn", SRC, "--baseline-fitness", str(baseline))
    assert r.returncode == 0, r.stderr
    return str(Path(tmp) / "gepa_state.json")


def add(state, cid, op, fqn, parent=None):
    args = ["add-candidate", state, "--id", cid, "--generation", "1", "--operator", op,
            "--mutations", f"{op} on X", "--candidate-fqn", fqn]
    if parent:
        args += ["--parent-fqn", parent]
    return run("population_state.py", *args)


class GuardTests(unittest.TestCase):
    def test_rejects_source_and_non_candidate(self):
        with tempfile.TemporaryDirectory() as t:
            st = init_state(t)
            self.assertNotEqual(add(st, "c1", "add_synonym", SRC).returncode, 0)
            self.assertNotEqual(add(st, "c1", "add_synonym", "DB.SCH.OTHER").returncode, 0)
            self.assertEqual(add(st, "c1", "add_synonym", CAND).returncode, 0)

    def test_mutate_guard(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t, "d.sql")
            p.write_text("CREATE SEMANTIC VIEW X TABLES (a AS b)")
            self.assertNotEqual(run("mutate.py", "get-prompt", "add_synonym", str(p), "--source", SRC, "--target", SRC).returncode, 0)
            self.assertEqual(run("mutate.py", "get-prompt", "add_synonym", str(p), "--source", SRC, "--target", CAND).returncode, 0)


class WeightTests(unittest.TestCase):
    def state(self, ops):
        s = {"baseline_fitness": 0.5, "operator_weights": dict(ps.DEFAULT_OPERATOR_WEIGHTS), "candidates": []}
        for i, (op, fit) in enumerate(ops):
            s["candidates"].append({"id": f"c{i}", "operator": op, "mutations": op, "fitness": fit, "candidate_fqn": f"x{i}"})
        return s

    def test_exact_operator(self):
        self.assertEqual(ps.extract_operator({"mutations": "add_metric_description on M"}), "add_metric_description")
        self.assertEqual(ps.extract_operator({"mutations": "add_metric on M"}), "add_metric")
        self.assertIsNone(ps.extract_operator({"mutations": "add_metrics"}))

    def test_description_winner_does_not_credit_add_metric(self):
        s = self.state([("add_metric_description", 0.9)])
        s["candidates"][0]["operator"] = None
        before = dict(s["operator_weights"])
        ps.apply_weight_update(s, ["c0"], [])
        w = s["operator_weights"]
        self.assertGreater(w["add_metric_description"] / before["add_metric_description"], w["add_metric"] / before["add_metric"])

    def test_delta_scaling(self):
        small = self.state([("add_synonym", 0.52)])
        big = self.state([("add_synonym", 0.80)])
        ps.apply_weight_update(small, ["c0"], [])
        ps.apply_weight_update(big, ["c0"], [])
        self.assertGreater(big["operator_weights"]["add_synonym"], small["operator_weights"]["add_synonym"])

    def test_floor_and_normalized(self):
        s = self.state([("remove_column", 0.0)] * 1)
        s["operator_weights"]["remove_column"] = ps.WEIGHT_FLOOR
        ps.apply_weight_update(s, [], ["c0"])
        self.assertAlmostEqual(sum(s["operator_weights"].values()), 1.0, places=2)
        self.assertGreater(s["operator_weights"]["remove_column"], 0)


class StateTests(unittest.TestCase):
    def test_metric_version_refused(self):
        with tempfile.TemporaryDirectory() as t:
            st = init_state(t)
            add(st, "c1", "add_synonym", CAND)
            r = run("population_state.py", "update-fitness", st, "--id", "c1", "--fitness", "0.7", "--metric-version", "v1")
            self.assertNotEqual(r.returncode, 0)

    def test_best_candidate_fqn_persisted(self):
        with tempfile.TemporaryDirectory() as t:
            st = init_state(t)
            add(st, "c1", "add_synonym", CAND)
            cand2 = "DB.SCH.SV__GEPA__R1A2B3C__G1__C2"
            add(st, "c2", "add_filter", cand2)
            r = run("tournament.py", json.dumps({"c1": 0.6, "c2": 0.55}), st, "--metric-version", "v3")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(Path(st).read_text())["best_candidate_fqn"], CAND)

    def test_finalize_requires_repeats_and_same_questions(self):
        with tempfile.TemporaryDirectory() as t:
            st = init_state(t)
            add(st, "c1", "add_synonym", CAND)
            q = Path(t, "q.json")
            q.write_text(json.dumps(["a", "b"]))
            run("population_state.py", "record-final", st, "--id", "c1", "--fitness", "0.7", "--metric-version", "v3", "--questions-file", str(q))
            self.assertNotEqual(run("population_state.py", "finalize", st).returncode, 0)
            run("population_state.py", "record-final", st, "--id", "c1", "--fitness", "0.8", "--metric-version", "v3", "--questions-file", str(q))
            r = run("population_state.py", "finalize", st)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(Path(st).read_text())["best_candidate_fqn"], CAND)


class PromptTests(unittest.TestCase):
    def test_all_templates(self):
        fails = [{"question": "Q1", "expected_sql": "SELECT 1", "generated_sql": "SELECT 2", "failure_class": "wrong_metric"}]
        wins = [{"candidate": "c9", "operator": "add_synonym", "summary": "added synonym revenue"}]
        for op in mutate.OPERATORS:
            tpl = mutate.PROMPT_TEMPLATES[op]
            self.assertIn("{failures}", tpl)
            self.assertIn("{prior_wins}", tpl)
            out = mutate.render_prompt(op, "DDL", fails, wins)
            self.assertIn("wrong_metric", out)
            self.assertIn("do not undo", out)
            self.assertNotIn("OR REPLACE", out.upper())
            for bad in ("IS_TIME_DIMENSION", "default_aggregation", "INSTRUCTIONS="):
                self.assertNotIn(bad, out)
            self.assertNotIn("{", mutate.render_prompt(op, "DDL").replace("DDL", ""))

    def test_operator_sets_match(self):
        self.assertEqual(set(mutate.OPERATORS), set(ps.DEFAULT_OPERATOR_WEIGHTS))
        self.assertEqual(set(mutate.OPERATORS), set(mutate.PROMPT_TEMPLATES))

    def test_replace_header_never_reaches_deploy(self):
        # GET_DDL returns a replace-style header; validate accepts it, rewrite-ddl must always neutralize it.
        ddl = "CREATE OR " + "REPLACE SEMANTIC VIEW DB.SCH.X TABLES (t AS v)"
        out = subprocess.run([sys.executable, str(SCRIPTS / "candidate.py"), "rewrite-ddl", "--source", "DB.SCH.X",
                              "--candidate", "DB.SCH.X__CAND__R1A2B3C"], input=ddl, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue(out.stdout.startswith("CREATE SEMANTIC VIEW DB.SCH.X__CAND__R1A2B3C "))


class SamplingTests(unittest.TestCase):
    def test_eval_yaml_uses_subset(self):
        qs = [{"question": f"q{i}", "previously_passed": i % 2 == 0} for i in range(10)]
        sel = sample_batch.stratified_sample(qs, 0.3, 1, {"batch_history": []})
        self.assertEqual(len(sel), 3)
        y = sample_batch.render_eval_config(CAND, sel, "v3")
        for q in sel:
            self.assertIn(f'"{q}"', y)
        self.assertEqual(y.count("      - "), 3)
        self.assertIn('version: "v3"', y)

    def test_reuse_questions_cli(self):
        with tempfile.TemporaryDirectory() as t:
            q = Path(t, "b.json")
            q.write_text(json.dumps(["only one?"]))
            r = run("sample_batch.py", "--reuse-questions", str(q), "--emit-eval-yaml", CAND, "--generation", "1", "--history-file", str(Path(t, "s.json")))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('- "only one?"', r.stdout)

    def test_small_pool_uses_all(self):
        qs = [{"question": f"q{i}"} for i in range(4)]
        self.assertEqual(len(sample_batch.stratified_sample(qs, 0.3, 1, {})), 4)


if __name__ == "__main__":
    unittest.main()
