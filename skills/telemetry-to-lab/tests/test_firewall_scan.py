import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "firewall_scan.py"


def run(labdir):
    return subprocess.run([sys.executable, str(SCRIPT), str(labdir)], capture_output=True, text=True)


class FirewallScanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lab = Path(self.tmp.name)
        internal = self.lab / "internal"
        internal.mkdir()
        (internal / "account.json").write_text(json.dumps({
            "customer": "Acme Purchasing Corp", "account_name": "XYZ12345", "account_id": 424242,
            "warehouse_classes": {"WH_LOAD_X": "etl"}}))
        (internal / "findings.json").write_text(json.dumps({"etl": [{
            "evidence_ref": "CALL ACME_DB.MKT.SP_LOAD_REVIEWS",
            "user": "jane.doe@acme.com"}]}))

    def tearDown(self):
        self.tmp.cleanup()

    def write_facing(self, text):
        (self.lab / "t-lab-intake.md").write_text(text)
        (self.lab / "data_spec.yaml").write_text("domain: telecom customer care\ncolumns: [CUSTOMER_ID, CONTACT_ID]\n")
        (self.lab / "remap.md").write_text("Find tables with one row per interaction.\n")

    def test_clean_passes(self):
        self.write_facing("# Contact intelligence lab\nA telecom organization enriches contacts with AI_CLASSIFY.\n")
        r = run(self.lab)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_customer_name_fails(self):
        self.write_facing("Built for Acme teams.\n")
        r = run(self.lab)
        self.assertEqual(r.returncode, 1)
        self.assertIn("ACME", r.stdout)

    def test_object_name_fails(self):
        self.write_facing("Rewrite SP_LOAD_REVIEWS as a dynamic table.\n")
        self.assertEqual(run(self.lab).returncode, 1)

    def test_warehouse_and_email_fail(self):
        self.write_facing("Run on WH_LOAD_X, contact jane.doe@acme.com\n")
        r = run(self.lab)
        self.assertEqual(r.returncode, 1)
        self.assertIn("email", r.stdout)

    def test_phrase_fails(self):
        self.write_facing("We noticed your jobs time out.\n")
        r = run(self.lab)
        self.assertEqual(r.returncode, 1)
        self.assertIn("phrase", r.stdout)

    def test_generic_suffix_not_denied(self):
        self.write_facing("A purchasing team at a large corp.\n")
        r = run(self.lab)
        # 'Purchasing' is a name token (denied); 'Corp' is a generic suffix (allowed)
        self.assertIn("PURCHASING", r.stdout)
        self.assertNotIn("[identifier] CORP\n", r.stdout)

    def test_lab_owned_names_allowed_even_if_in_internal(self):
        (self.lab / "internal" / "evidence_map.md").write_text(
            "| WEB_EVENTS_RAW | ACME_DB.MKT.CLICKS_RAW |\n")
        self.write_facing("Build a dynamic table over WEB_EVENTS_RAW.\n")
        (self.lab / "data_spec.yaml").write_text("archetypes:\n  - name: WEB_EVENTS_RAW\n")
        r = run(self.lab)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.write_facing("Build a dynamic table over CLICKS_RAW.\n")
        (self.lab / "data_spec.yaml").write_text("archetypes:\n  - name: WEB_EVENTS_RAW\n")
        self.assertEqual(run(self.lab).returncode, 1)

    def test_punctuated_brand_caught(self):
        acct = json.loads((self.lab / "internal" / "account.json").read_text())
        acct["customer"] = "Acme&Co (Global)"
        (self.lab / "internal" / "account.json").write_text(json.dumps(acct))
        self.write_facing("Built for Acme&Co marketers in a global org.\n")
        r = run(self.lab)
        self.assertEqual(r.returncode, 1)
        self.assertIn("ACME&CO", r.stdout)
        self.assertNotIn("[identifier] GLOBAL", r.stdout)

    def test_missing_internal_errors(self):
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        self.assertEqual(run(empty).returncode, 2)


if __name__ == "__main__":
    unittest.main()
