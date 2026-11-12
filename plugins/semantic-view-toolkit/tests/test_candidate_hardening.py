"""Regression tests for the cold-critic findings against candidate.py."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import candidate as c  # noqa: E402

SRC = "DB.SCH.SALES_SV"
RUN = "R1A2B3C"
CAND = "DB.SCH.SALES_SV__CAND__R1A2B3C"


def rewrite(body):
    return c.rewrite_ddl("CREATE SEMANTIC VIEW DB.SCH.SALES_SV\n" + body, SRC, CAND)


class InjectionTests(unittest.TestCase):
    def test_rejects_trailing_drop_of_production(self):
        with self.assertRaises(c.ContractError):
            rewrite("TABLES (t AS DB.SCH.T);\nDROP SEMANTIC VIEW DB.SCH.SALES_SV;")

    def test_rejects_trailing_statement_after_comments(self):
        with self.assertRaises(c.ContractError):
            rewrite("TABLES (t AS DB.SCH.T); -- ok\n\n/* hi */ DROP TABLE DB.SCH.T")

    def test_rejects_second_statement_without_whitespace(self):
        with self.assertRaises(c.ContractError):
            rewrite("TABLES (t AS DB.SCH.T);DROP SEMANTIC VIEW X")

    def test_allows_trailing_semicolon_and_comments(self):
        self.assertIn("CREATE SEMANTIC VIEW " + CAND, rewrite("TABLES (t AS DB.SCH.T);  -- done\n/* end */\n"))

    def test_semicolons_in_strings_comments_and_dollar_quotes_are_not_terminators(self):
        body = (
            "TABLES (t AS DB.SCH.T COMMENT = 'a; b ''c; d''')\n"
            "COMMENT = $$x; DROP VIEW y$$\n"
            "-- note; with semicolon\n"
            "/* block; semicolon */\n"
        )
        self.assertIn(CAND, rewrite(body))

    def test_escaped_quote_cannot_hide_a_second_statement(self):
        with self.assertRaises(c.ContractError):
            rewrite("TABLES (t AS DB.SCH.T COMMENT = 'it''s'); DROP VIEW v")

    def test_unbalanced_quote_still_rejected(self):
        with self.assertRaises(c.ContractError):
            rewrite('TABLES (t AS DB.SCH.T); DROP VIEW "unterminated')

    def test_cli_rewrite_exits_nonzero_on_injection(self):
        import subprocess
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "candidate.py"), "rewrite-ddl", "--source", SRC, "--candidate", CAND],
            input="CREATE SEMANTIC VIEW DB.SCH.SALES_SV TABLES (x); DROP SEMANTIC VIEW DB.SCH.SALES_SV;",
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, "")


class GuardStrictnessTests(unittest.TestCase):
    def test_sibling_view_candidate_is_not_writable_by_source_run(self):
        with self.assertRaises(c.ContractError):
            c.check_guard(SRC, "DB.SCH.SALES_SV__EU__CAND__R1A2B3C")

    def test_header_of_sibling_views_candidate_is_rejected(self):
        with self.assertRaises(c.ContractError):
            c.rewrite_ddl("CREATE SEMANTIC VIEW DB.SCH.SALES_SV__EU__CAND__R111111 TABLES (x)", SRC, CAND)

    def test_two_part_header_in_other_schema_is_rejected(self):
        with self.assertRaises(c.ContractError):
            c.rewrite_ddl("CREATE SEMANTIC VIEW OTHER.SALES_SV TABLES (x)", SRC, CAND)

    def test_quoted_lowercase_header_is_a_different_object(self):
        with self.assertRaises(c.ContractError):
            c.rewrite_ddl('CREATE SEMANTIC VIEW DB.SCH."sales_sv" TABLES (x)', SRC, CAND)

    def test_own_header_forms_still_accepted(self):
        for header in ("DB.SCH.SALES_SV", "SCH.SALES_SV", "SALES_SV", "db.sch.sales_sv"):
            self.assertIn(CAND, c.rewrite_ddl(f"CREATE OR REPLACE SEMANTIC VIEW {header} TABLES (x)", SRC, CAND))


class AdoptedCandidateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "m.json")
        self.cand = c.build_name(SRC, "cand", RUN)
        c.register(self.path, RUN, SRC, self.cand)

    def tearDown(self):
        self.tmp.cleanup()

    def test_promoted_candidate_is_protected_from_writes_and_cleanup(self):
        c.set_status(self.path, self.cand, "promoted")
        with self.assertRaises(c.ContractError):
            c.check_guard(SRC, self.cand, self.path)
        self.assertEqual(c.cleanup_plan(self.path, RUN)["drop_statements"], [])

    def test_promoted_candidate_can_seed_new_candidates(self):
        with self.assertRaises(c.ContractError):
            c.build_name(self.cand, "cand", "RBBBBBB")
        c.set_status(self.path, self.cand, "promoted")
        self.assertEqual(c.build_name(self.cand, "cand", "RBBBBBB", manifest=self.path), self.cand + "__CAND__RBBBBBB")

    def test_only_promoted_status_allows_seeding(self):
        c.set_status(self.path, self.cand, "winner")
        with self.assertRaises(c.ContractError):
            c.build_name(self.cand, "cand", "RBBBBBB", manifest=self.path)


class CleanupRunConsistencyTests(unittest.TestCase):
    def test_entry_run_must_match_run_in_candidate_name(self):
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "m.json")
            Path(path).write_text(json.dumps({"entries": [{
                "run": "R000001", "source": SRC, "candidate": "DB.SCH.SALES_SV__CAND__R999999", "status": "failed"}]}))
            with self.assertRaises(c.ContractError):
                c.cleanup_plan(path, "R000001")


class VqrDiffTests(unittest.TestCase):
    BASE = (
        "CREATE SEMANTIC VIEW DB.SCH.SALES_SV TABLES (t AS DB.SCH.T)\n"
        "AI_VERIFIED_QUERIES (\n"
        "  vqr_a AS (QUESTION 'a; b?' SQL 'SELECT 1'),\n"
        "  vqr_b AS (QUESTION 'second' SQL 'SELECT 2')\n)"
    )

    def test_no_clause(self):
        plain = "CREATE SEMANTIC VIEW x TABLES (t)"
        self.assertEqual(c.vqr_diff(plain, plain), {"added": [], "removed": [], "changed": []})

    def test_whitespace_only_change_is_not_a_change(self):
        self.assertEqual(c.vqr_diff(self.BASE, self.BASE.replace("SELECT 1", "SELECT   1")),
                         {"added": [], "removed": [], "changed": []})

    def test_added_and_changed(self):
        mutated = self.BASE.replace(
            "vqr_b AS (QUESTION 'second' SQL 'SELECT 2')",
            "vqr_b AS (QUESTION 'second' SQL 'SELECT 3'),\n  vqr_c AS (QUESTION 'x' SQL 'SELECT 4')")
        self.assertEqual(c.vqr_diff(self.BASE, mutated), {"added": ["VQR_C"], "removed": [], "changed": ["VQR_B"]})

    def test_removed(self):
        mutated = self.BASE.replace(",\n  vqr_b AS (QUESTION 'second' SQL 'SELECT 2')", "")
        self.assertEqual(c.vqr_diff(self.BASE, mutated)["removed"], ["VQR_B"])


if __name__ == "__main__":
    unittest.main()
