"""Regression tests for cold-critic findings against the GEPA scripts."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S = ROOT / "scripts"
sys.path.insert(0, str(S))
import population_state as ps  # noqa: E402
import sample_batch  # noqa: E402,F401

SRC = "DB.SCH.SALES_SV"
BASE = (
    "CREATE SEMANTIC VIEW DB.SCH.SALES_SV TABLES (t AS DB.SCH.T)\n"
    "AI_VERIFIED_QUERIES (\n  vqr_a AS (QUESTION 'q' SQL 'SELECT 1')\n)"
)


def run(script, *args, stdin=None):
    return subprocess.run([sys.executable, str(S / script), *args], capture_output=True, text=True, input=stdin)


class ValidateTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.dir = Path(self.d.name)
        (self.dir / "orig.sql").write_text(BASE)

    def tearDown(self):
        self.d.cleanup()

    def validate(self, mutated, *extra):
        (self.dir / "mut.sql").write_text(mutated)
        return run("mutate.py", "validate", str(self.dir / "orig.sql"), str(self.dir / "mut.sql"), *extra)

    def test_fail_exits_nonzero(self):
        proc = self.validate(BASE)  # no-op mutation
        self.assertEqual(json.loads(proc.stdout)["status"], "FAIL")
        self.assertEqual(proc.returncode, 1)

    def test_trailing_drop_fails(self):
        proc = self.validate(BASE.replace("TABLES (t AS DB.SCH.T)", "TABLES (t AS DB.SCH.T COMMENT = 'x')") + ";\nDROP SEMANTIC VIEW DB.SCH.SALES_SV;")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("more than one statement", proc.stdout)

    def test_removed_or_changed_vqr_fails(self):
        changed = BASE.replace("SELECT 1", "SELECT 2")
        proc = self.validate(changed, "--operator", "add_synonym")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("SV-VQR-MUTATE", proc.stdout)
        removed = BASE.replace("vqr_a AS (QUESTION 'q' SQL 'SELECT 1')", "")
        self.assertEqual(self.validate(removed).returncode, 1)

    def test_only_add_vqr_may_add_vqrs(self):
        added = BASE.replace("SELECT 1')", "SELECT 1'),\n  vqr_b AS (QUESTION 'r' SQL 'SELECT 2')")
        self.assertEqual(self.validate(added, "--operator", "add_synonym").returncode, 1)
        proc = self.validate(added, "--operator", "add_vqr")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(json.loads(proc.stdout)["vqr_added"], ["VQR_B"])

    def test_clean_mutation_passes(self):
        proc = self.validate(BASE.replace("TABLES (t AS DB.SCH.T)", "TABLES (t AS DB.SCH.T COMMENT = 'x')"))
        self.assertEqual(proc.returncode, 0, proc.stdout)


class TournamentTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.dir = Path(self.d.name)
        self.state = str(self.dir / "s.json")
        init = run("population_state.py", "init", str(self.dir), "--pop-size", "3", "--agent-name", SRC,
                   "--source-fqn", SRC, "--baseline-fitness", "0.5")
        self.assertEqual(init.returncode, 0, init.stderr)
        self.state = str(self.dir / "gepa_state.json")
        for i in (1, 2, 3):
            proc = run("population_state.py", "add-candidate", self.state, "--id", f"cand_{i}", "--operator", "add_synonym",
                       "--candidate-fqn", f"DB.SCH.SALES_SV__GEPA__R1A2B3C__G1__C{i}", "--generation", "1", "--mutations", "add_synonym on col")
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def tearDown(self):
        self.d.cleanup()

    def tournament(self, scores):
        return run("tournament.py", json.dumps(scores), self.state, "--metric-version", "v3")

    def test_unknown_id_is_rejected_and_state_untouched(self):
        before = Path(self.state).read_text()
        proc = self.tournament({"cand_1": 0.6, "cand_2": 0.5, "cand_3": 0.4, "ghost": 0.99})
        self.assertEqual(proc.returncode, 1)
        self.assertIn("ghost", proc.stderr)
        self.assertEqual(Path(self.state).read_text(), before)

    def test_missing_pending_candidate_is_rejected(self):
        proc = self.tournament({"cand_1": 0.6, "cand_2": 0.5})
        self.assertEqual(proc.returncode, 1)
        self.assertIn("cand_3", proc.stderr)

    def test_complete_scores_work(self):
        proc = self.tournament({"cand_1": 0.6, "cand_2": 0.5, "cand_3": 0.4})
        self.assertEqual(proc.returncode, 0, proc.stderr)


class FinalizeTests(unittest.TestCase):
    def state(self):
        return {"candidates": [{"id": "c1", "candidate_fqn": "DB.SCH.SALES_SV__GEPA__R1A2B3C__G1__C1"}],
                "final_runs": [{"id": "c1", "fitness": 0.8, "questions_sha": "a", "metric_version": "v3"}] * 2}

    def test_min_repeats_below_two_is_rejected(self):
        with self.assertRaises(ValueError):
            ps.finalize_winner(self.state(), 1)

    def test_removed_finalist_is_a_clean_error_not_a_crash(self):
        s = self.state()
        s["candidates"] = []
        with self.assertRaises(ValueError):
            ps.finalize_winner(s)

    def test_production_baseline_is_reported_but_never_the_winner(self):
        s = self.state()
        s["final_runs"] += [{"id": "production", "fitness": 0.7, "questions_sha": "a", "metric_version": "v3"}] * 2
        result = ps.finalize_winner(s)
        self.assertEqual(result["winner"], "c1")
        self.assertAlmostEqual(result["delta_vs_production"], 0.1)

    def test_only_production_is_rejected(self):
        s = {"candidates": [], "final_runs": [{"id": "production", "fitness": 0.7, "questions_sha": "a", "metric_version": "v3"}] * 2}
        with self.assertRaises(ValueError):
            ps.finalize_winner(s)



class HoldoutTests(unittest.TestCase):
    QS = [{"question": f"What is metric number {i}?"} for i in range(12)]

    def test_split_is_deterministic_disjoint_and_complete(self):
        import sample_batch as sb
        a = sb.split_holdout(self.QS, 0.25)
        b = sb.split_holdout(list(reversed(self.QS)), 0.25)
        self.assertEqual(a, b)
        self.assertFalse(set(a["train"]) & set(a["holdout"]))
        self.assertEqual(set(a["train"]) | set(a["holdout"]), {q["question"] for q in self.QS})
        self.assertEqual(len(a["holdout"]), 3)

    def test_small_sets_get_no_holdout_and_a_warning(self):
        import sample_batch as sb
        result = sb.split_holdout(self.QS[:5], 0.25)
        self.assertEqual(result["holdout"], [])
        self.assertIn("optimistic", result["note"])

    def test_cli_split_does_not_need_generation_args(self):
        proc = run("sample_batch.py", "--from-stdin", "--holdout-pct", "0.25", stdin=json.dumps(self.QS))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(json.loads(proc.stdout)["holdout"]), 3)

    def test_sampling_still_requires_generation_args(self):
        proc = run("sample_batch.py", "--from-stdin", stdin=json.dumps(self.QS))
        self.assertEqual(proc.returncode, 1)

    def test_validate_rejects_added_vqr_that_repeats_a_holdout_question(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "o.sql").write_text(BASE)
            (d / "m.sql").write_text(BASE.replace("SELECT 1')", "SELECT 1'),\n  vqr_b AS (QUESTION 'What is   TOTAL revenue?' SQL 'SELECT 2')"))
            (d / "h.json").write_text(json.dumps(["what is total revenue?"]))
            proc = run("mutate.py", "validate", str(d / "o.sql"), str(d / "m.sql"), "--operator", "add_vqr", "--holdout-file", str(d / "h.json"))
            self.assertEqual(proc.returncode, 1)
            self.assertIn("hold-out", proc.stdout)
            (d / "h.json").write_text(json.dumps(["an unrelated question"]))
            ok = run("mutate.py", "validate", str(d / "o.sql"), str(d / "m.sql"), "--operator", "add_vqr", "--holdout-file", str(d / "h.json"))
            self.assertEqual(ok.returncode, 0, ok.stdout)


if __name__ == "__main__":
    unittest.main()
