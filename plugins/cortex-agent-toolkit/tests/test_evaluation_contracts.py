import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


SCRIPTS = Path(__file__).resolve().parents[1] / "skills/agent-evaluation/scripts"


class ConversionContracts(unittest.TestCase):
    def setUp(self):
        connector = types.ModuleType("snowflake.connector")
        connector.connect = MagicMock()
        snowflake = types.ModuleType("snowflake")
        snowflake.connector = connector
        self.modules = patch.dict(sys.modules, {"snowflake": snowflake, "snowflake.connector": connector})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        spec = importlib.util.spec_from_file_location("converter", SCRIPTS / "convert_eval_dataset.py")
        self.converter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.converter)
        self.connect = connector.connect
        self.cursor = self.connect.return_value.cursor.return_value
        self.cursor.fetchall.return_value = [("Question", 0)]
        self.cursor.fetchone.side_effect = [(1,), None]

    def convert(self, **kwargs):
        self.converter.convert_dataset("DB.SOURCE.INPUT", "DB.TEST.OUTPUT", "question", "answer", None, "default", **kwargs)

    def test_default_is_not_replacement(self):
        self.convert()
        statements = [call.args[0] for call in self.cursor.execute.call_args_list]
        self.assertFalse(any("DROP TABLE" in statement or "CREATE OR REPLACE" in statement for statement in statements))
        self.assertTrue(any("GROUND_TRUTH VARIANT" in statement for statement in statements))

    def test_zero_answer_preserved(self):
        self.convert()
        params = self.cursor.executemany.call_args.args[1]
        self.assertEqual(json.loads(params[0][1])["ground_truth_output"], 0)

    def test_same_object_rejected_before_connect(self):
        with self.assertRaises(ValueError):
            self.converter.convert_dataset("db.schema.table", "DB.SCHEMA.TABLE", "q", "a", None, "default", True)
        self.connect.assert_not_called()

    def test_explicit_replace_reads_first(self):
        self.convert(drop_target=True)
        statements = [call.args[0] for call in self.cursor.execute.call_args_list]
        self.assertTrue(statements[0].startswith("SELECT"))
        self.assertTrue(any("CREATE OR REPLACE TABLE" in statement for statement in statements))

    def test_read_failure_closes_resources_without_ddl(self):
        self.cursor.execute.side_effect = RuntimeError("read failed")
        with self.assertRaises(RuntimeError):
            self.convert()
        self.assertEqual(self.cursor.execute.call_count, 1)
        self.cursor.close.assert_called_once()
        self.connect.return_value.close.assert_called_once()


class CompletionContracts(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("completion", SCRIPTS / "check_eval_completion.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.check = module.check_completion
        self.expected = [["q1", "accuracy"], ["q2", "accuracy"]]
        self.records = [{"question_id": question, "metric": "accuracy", "score": 0.8, "success": True}
                        for question in ["q1", "q2"]]

    def test_complete(self):
        self.assertTrue(self.check("COMPLETED", self.expected, self.records)["ready"])

    def test_partial_or_nonterminal(self):
        self.assertFalse(self.check("COMPLETED", self.expected, self.records[:1])["ready"])
        self.assertFalse(self.check("COMPUTATION_IN_PROGRESS", self.expected, self.records)["ready"])

    def test_duplicate_failed_and_invalid(self):
        self.assertFalse(self.check("COMPLETED", self.expected, self.records + self.records[:1])["ready"])
        for change in [{"success": False}, {"error": "judge failed"}, {"score": None}, {"score": float("nan")}]:
            with self.subTest(change=change):
                records = [dict(self.records[0], **change), self.records[1]]
                self.assertFalse(self.check("COMPLETED", self.expected, records)["ready"])


if __name__ == "__main__":
    unittest.main()
