import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1] / "skills"


def load_script(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tournament = load_script("tournament", "agent-gepa-optimizer/scripts/tournament.py")
state = load_script("population_state", "agent-gepa-optimizer/scripts/population_state.py")
builder = load_script("builder", "agent-instruction-optimizer/scripts/build_candidate.py")


class OptimizerContracts(unittest.TestCase):
    def test_builder_preserves_instruction_fields(self):
        for target, field in [("orchestration_instructions.md", "orchestration"),
                              ("response_instructions.md", "response")]:
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                base = {"instructions": {"orchestration": "original", "response": "style",
                                         "sample_questions": [{"question": "hello"}]}, "tools": []}
                for name, value in [("base", base), ("pool", [{"text": "candidate", "target_file": target}]),
                                    ("traces", [])]:
                    (folder / f"{name}.json").write_text(json.dumps(value))
                result = subprocess.run([sys.executable, str(ROOT / "agent-instruction-optimizer/scripts/build_candidate.py"),
                    "--base-spec", str(folder / "base.json"), "--instruction-pool", str(folder / "pool.json"),
                    "--trace-pool", str(folder / "traces.json"), "--instruction-idx", "0", "--fewshot-indices", "",
                    "--output", str(folder / "out.json")], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                expected = json.loads(json.dumps(base))
                expected["instructions"][field] = "candidate"
                self.assertEqual(json.loads((folder / "out.json").read_text()), expected)

    def test_demo_extracts_answer(self):
        output = builder.format_few_shot_section([{"input": "Q", "expected_output": {
            "ground_truth_output": "Answer", "ground_truth_invocations": [{"tool_name": "tool"}]}}])
        self.assertIn("**A:** Answer", output)
        self.assertNotIn("ground_truth_invocations", output)

    def test_invalid_scores_fail_before_selection(self):
        population = [{"id": "alpha"}, {"id": "beta"}]
        for invalid in [{},
                        {"alpha": {"EVAL_AGG_SCORE": 0.5}},
                        *[{"alpha": record, "beta": {"EVAL_AGG_SCORE": 0.8}}
                          for record in [{"EVAL_AGG_SCORE": None},
                                         {"EVAL_AGG_SCORE": float("nan")},
                                         {"EVAL_AGG_SCORE": float("inf")},
                                         {"EVAL_AGG_SCORE": True},
                                         0.5]]]:
            with self.subTest(scores=invalid), self.assertRaises(ValueError):
                tournament.run_tournament(population, invalid)

    def test_valid_scores_select_better(self):
        winners, losers = tournament.run_tournament([{"id": "alpha"}, {"id": "beta"}],
            {"alpha": {"EVAL_AGG_SCORE": 0.9}, "beta": {"EVAL_AGG_SCORE": 0.2}})
        self.assertEqual(winners[0]["id"], "alpha")
        self.assertEqual(losers[0]["id"], "beta")

    def test_root_lineage_controls_diversity(self):
        population = [{"id": str(index), "parent_id": f"parent{index}", "original_parent": "root"}
                      for index in range(4)]
        self.assertFalse(tournament.check_diversity(population))

    def test_offspring_inherit_root(self):
        children = tournament.fill_population([{"id": "parent", "original_parent": "root"}], 3, 2)
        self.assertTrue(all(child.get("original_parent") == "root" for child in children))

    def test_state_inherits_root(self):
        current = state.init_state(4, "agent", 0.5)
        state.add_candidate(current, "root", [], 0)
        state.add_candidate(current, "child", [], 1, parent_id="root")
        state.add_candidate(current, "grandchild", [], 2, parent_id="child")
        self.assertEqual(current["population"][-1].get("original_parent"), "root")

    def test_legacy_ancestry_is_not_guessed(self):
        legacy = [{"id": str(index), "parent_id": "unknown"} for index in range(4)]
        with self.assertRaises(ValueError):
            tournament.check_diversity(legacy)
        with self.assertRaises(ValueError):
            tournament.fill_population(legacy[:1], 3, 2)

    def test_unknown_parent_does_not_modify_population(self):
        current = state.init_state(4, "agent", 0.5)
        with self.assertRaises(ValueError):
            state.add_candidate(current, "child", [], 1, parent_id="missing")
        self.assertEqual(current["population"], [])

    def test_plain_demo_answer_is_preserved(self):
        self.assertIn("**A:** Plain answer", builder.format_few_shot_section([
            {"input": "Q", "expected_output": "Plain answer"}]))

    def test_tournament_cli_rejects_missing_scores_without_state_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            state_path = folder / "state.json"
            scores_path = folder / "scores.json"
            original = json.dumps({"population": [{"id": "alpha"}, {"id": "beta"}]})
            state_path.write_text(original)
            scores_path.write_text("{}")
            result = subprocess.run([
                sys.executable, str(ROOT / "agent-gepa-optimizer/scripts/tournament.py"),
                str(scores_path), str(state_path),
            ], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Missing or invalid fitness", result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertEqual(state_path.read_text(), original)


if __name__ == "__main__":
    unittest.main()
