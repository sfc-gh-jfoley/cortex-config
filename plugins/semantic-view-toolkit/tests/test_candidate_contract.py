import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import candidate as c  # noqa: E402

SRC = "DB.SCH.SALES_SV"
RUN = "R1A2B3C"


class NamingTests(unittest.TestCase):
    def test_gepa_cand_mat_names(self):
        self.assertEqual(c.build_name(SRC, "gepa", RUN, 2, 3), "DB.SCH.SALES_SV__GEPA__R1A2B3C__G2__C3")
        self.assertEqual(c.build_name(SRC, "cand", RUN), "DB.SCH.SALES_SV__CAND__R1A2B3C")
        self.assertEqual(c.build_name(SRC, "mat", RUN), "DB.SCH.SALES_SV__MAT__R1A2B3C")

    def test_names_are_uppercased(self):
        self.assertEqual(c.build_name("db.sch.sales_sv", "cand", RUN), "DB.SCH.SALES_SV__CAND__R1A2B3C")

    def test_rejects_bad_run_and_missing_gepa_indexes(self):
        with self.assertRaises(c.ContractError):
            c.build_name(SRC, "cand", "run1")
        with self.assertRaises(c.ContractError):
            c.build_name(SRC, "gepa", RUN)

    def test_rejects_deriving_from_a_candidate(self):
        with self.assertRaises(c.ContractError):
            c.build_name("DB.SCH.SALES_SV__CAND__R1A2B3C", "cand", "RFFFFFF")

    def test_rejects_quoted_or_short_fqn(self):
        for bad in ("SALES_SV", 'DB.SCH."my view"', "A.B"):
            with self.assertRaises(c.ContractError):
                c.build_name(bad, "cand", RUN)

    def test_new_run_matches_pattern(self):
        self.assertRegex(c.new_run(), c.RUN_RE.pattern)


class GuardTests(unittest.TestCase):
    def test_refuses_production_name(self):
        with self.assertRaises(c.ContractError):
            c.check_guard(SRC, SRC)

    def test_refuses_non_candidate_target(self):
        with self.assertRaises(c.ContractError):
            c.check_guard(SRC, "DB.SCH.SALES_SV_V2")

    def test_refuses_other_schema_or_foreign_prefix(self):
        with self.assertRaises(c.ContractError):
            c.check_guard(SRC, "DB.OTHER.SALES_SV__CAND__R1A2B3C")
        with self.assertRaises(c.ContractError):
            c.check_guard(SRC, "DB.SCH.OTHER_SV__CAND__R1A2B3C")

    def test_accepts_candidate(self):
        c.check_guard(SRC, "DB.SCH.SALES_SV__CAND__R1A2B3C")


class RewriteTests(unittest.TestCase):
    CAND = "DB.SCH.SALES_SV__CAND__R1A2B3C"

    def test_rewrites_header_and_drops_or_replace(self):
        ddl = "create or replace semantic view DB.SCH.SALES_SV\n  tables (t as DB.SCH.SALES_SV)\n"
        out = c.rewrite_ddl(ddl, SRC, self.CAND)
        self.assertTrue(out.startswith("CREATE SEMANTIC VIEW DB.SCH.SALES_SV__CAND__R1A2B3C\n"))
        self.assertNotRegex(out.upper(), r"OR\s+(REPLACE|ALTER)")
        self.assertIn("t as DB.SCH.SALES_SV)", out)

    def test_handles_or_alter_and_unqualified_header(self):
        out = c.rewrite_ddl("CREATE OR ALTER SEMANTIC VIEW sales_sv TABLES (x)", SRC, self.CAND)
        self.assertTrue(out.startswith("CREATE SEMANTIC VIEW " + self.CAND))

    def test_accepts_parent_candidate_header_for_next_generation(self):
        parent = "DB.SCH.SALES_SV__GEPA__R1A2B3C__G1__C2"
        child = "DB.SCH.SALES_SV__GEPA__R1A2B3C__G2__C1"
        out = c.rewrite_ddl(f"CREATE SEMANTIC VIEW {parent} TABLES (x)", SRC, child)
        self.assertTrue(out.startswith("CREATE SEMANTIC VIEW " + child))

    def test_rejects_header_of_unrelated_or_cross_schema_view(self):
        with self.assertRaises(c.ContractError):
            c.rewrite_ddl("CREATE SEMANTIC VIEW DB.SCH.OTHER_SV__CAND__R1A2B3C TABLES (x)", SRC, self.CAND)
        with self.assertRaises(c.ContractError):
            c.rewrite_ddl("CREATE SEMANTIC VIEW DB.OTHER.SALES_SV TABLES (x)", SRC, self.CAND)

    def test_rejects_wrong_header_name_or_non_ddl(self):
        with self.assertRaises(c.ContractError):
            c.rewrite_ddl("CREATE SEMANTIC VIEW DB.SCH.OTHER TABLES (x)", SRC, self.CAND)
        with self.assertRaises(c.ContractError):
            c.rewrite_ddl("SELECT 1", SRC, self.CAND)


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "m.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_register_rejects_duplicates_and_prod_target(self):
        cand = "DB.SCH.SALES_SV__CAND__R1A2B3C"
        c.register(self.path, RUN, SRC, cand)
        with self.assertRaises(c.ContractError):
            c.register(self.path, RUN, SRC, cand)
        with self.assertRaises(c.ContractError):
            c.register(self.path, RUN, SRC, SRC)

    def test_cleanup_plan_uses_exact_names_and_keeps_winner_and_promoted(self):
        names = [c.build_name(SRC, "gepa", RUN, 1, i) for i in (1, 2, 3, 4)]
        for n in names:
            c.register(self.path, RUN, SRC, n)
        c.set_status(self.path, names[0], "winner")
        c.set_status(self.path, names[1], "promoted")
        c.set_status(self.path, names[2], "discarded")
        plan = c.cleanup_plan(self.path, RUN)
        self.assertEqual(plan["drop_statements"],
                         [f"DROP SEMANTIC VIEW IF EXISTS {names[2]};", f"DROP SEMANTIC VIEW IF EXISTS {names[3]};"])
        self.assertEqual({k["candidate"] for k in plan["kept"]}, {names[0], names[1]})
        for stmt in plan["drop_statements"]:
            self.assertNotIn("%", stmt)
            self.assertNotIn(f" {SRC};", stmt)

    def test_cleanup_ignores_other_runs(self):
        a = c.build_name(SRC, "cand", "RAAAAAA")
        b = c.build_name(SRC, "cand", "RBBBBBB")
        c.register(self.path, "RAAAAAA", SRC, a)
        c.register(self.path, "RBBBBBB", SRC, b)
        self.assertEqual(len(c.cleanup_plan(self.path, "RAAAAAA")["drop_statements"]), 1)

    def test_tampered_manifest_cannot_drop_production(self):
        Path(self.path).write_text(json.dumps({"entries": [
            {"run": RUN, "source": SRC, "candidate": SRC, "status": "failed"}]}))
        with self.assertRaises(c.ContractError):
            c.cleanup_plan(self.path, RUN)

    def test_set_status_validates(self):
        cand = c.build_name(SRC, "cand", RUN)
        c.register(self.path, RUN, SRC, cand)
        with self.assertRaises(c.ContractError):
            c.set_status(self.path, cand, "bogus")
        with self.assertRaises(c.ContractError):
            c.set_status(self.path, "DB.SCH.SALES_SV__CAND__RFFFFFF", "failed")


class NoBareReplaceTests(unittest.TestCase):
    """No skill, reference or script may tell an agent to replace a semantic view in place."""

    ALLOWED = {
        "references/candidate-promotion.md",
        "tests/test_candidate_contract.py",
        "tests/test_candidate_hardening.py",
        "tests/test_vqr_subquery_checks.py",
        "scripts/candidate.py",
    }
    PATTERN = re.compile(r"CREATE\s+OR\s+REPLACE\s+SEMANTIC\s+VIEW", re.IGNORECASE)

    def test_no_bare_create_or_replace_semantic_view(self):
        offenders = []
        for path in ROOT.rglob("*"):
            if path.suffix not in {".md", ".py", ".sql"} or "__pycache__" in path.parts:
                continue
            rel = path.relative_to(ROOT).as_posix()
            if rel in self.ALLOWED:
                continue
            for number, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
                if self.PATTERN.search(line):
                    offenders.append(f"{rel}:{number}")
        self.assertEqual(offenders, [], "bare CREATE OR REPLACE SEMANTIC VIEW found:\n" + "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()


class GateInventoryTests(unittest.TestCase):
    """Every registered gate must be cited by a skill, and every cited gate must be registered."""

    def _inventory_ids(self):
        text = (ROOT / "references" / "gate-inventory.md").read_text()
        return set(re.findall(r"^\| `([A-Z0-9-]+)` \|", text, re.M))

    def _skill_texts(self):
        for path in ROOT.rglob("*"):
            if path.suffix in {".md", ".py"} and "__pycache__" not in path.parts and ".pytest_cache" not in path.parts:
                if path.name != "gate-inventory.md" and "tests" not in path.parts:
                    yield path.relative_to(ROOT).as_posix(), path.read_text(errors="ignore")

    def test_every_registered_gate_is_cited_somewhere(self):
        corpus = "\n".join(text for _, text in self._skill_texts())
        missing = sorted(g for g in self._inventory_ids() if g not in corpus)
        self.assertEqual(missing, [], f"gates in the inventory that no skill cites: {missing}")

    def test_every_cited_gate_is_registered(self):
        known = self._inventory_ids()
        prefixes = ("SV-", "GEPA-", "VQR-", "EVAL-", "AUDIT-", "META-", "WATCH-", "REARCH-")
        cited = {}
        for rel, text in self._skill_texts():
            for gate in re.findall(r"`((?:SV|GEPA|VQR|EVAL|AUDIT|META|WATCH|REARCH)-[A-Z0-9-]+)`", text):
                cited.setdefault(gate, rel)
        unknown = {g: f for g, f in cited.items() if g not in known and g.startswith(prefixes)}
        self.assertEqual(unknown, {}, f"gates cited but not in the inventory: {unknown}")
