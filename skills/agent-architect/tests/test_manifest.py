import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("manifest", ROOT / "scripts/manifest.py")
manifest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manifest)


def event(phase, task="task-01", role="orchestrator", fields=""):
    if phase == "TASK_REGISTERED" and "criteria=" not in fields:
        fields += " | criteria=C1"
    if phase == "VERIFIED":
        fields += " | criteria_passed=C1 | pointer=.agent-project/reports/test.json"
    attempt = 2 if "attempt=2" in fields else 1
    fields = fields.replace("attempt=2", "")
    for short in ["abc", "def", "old", "new"]:
        fields = fields.replace(f"sha={short}", "sha=" + {"abc": "a", "def": "d", "old": "b", "new": "c"}[short] * 40)
    return f"2026-09-14T00:00:00Z | {task} | {phase} | {role} | run=test | attempt={attempt} | dispatch={task}-{role}-{attempt} | {fields}\n"


def dispatch(task, role, sha="a" * 40, attempt=1):
    marker = " | attempt=2" if attempt == 2 else ""
    return event("DISPATCH_REQUESTED", task, fields=f"dispatch={task}-{role}-{attempt} | target={role} | base={sha} | worktree=/tmp/fixture | event_path=.agent-project/events/{task}-{role}.log{marker}").replace(f" | dispatch={task}-orchestrator-{attempt}", "")


def build(task="task-01", sha="abc", attempt=1):
    marker = " | attempt=2" if attempt == 2 else ""
    return (dispatch(task, "worker", attempt=attempt) + event("CLAIMED", task, "worker", marker)
            + event("CODE_WRITTEN", task, "worker", f"sha={sha}{marker}"))


def gates(task="task-01", sha="abc", attempt=1):
    marker = " | attempt=2" if attempt == 2 else ""
    full_sha = {"abc": "a", "def": "d"}.get(sha, sha) * (40 if sha in {"abc", "def"} else 1)
    text = ""
    for phase, role in [
        ("REVIEW_REQUESTED", "orchestrator"), ("REVIEW_PASSED", "secarch"),
        ("TESTER_ASSIGNED", "orchestrator"), ("VERIFIED", "tester"),
        ("DONE", "orchestrator")]:
        if role in {"secarch", "tester"}:
            text += dispatch(task, role, full_sha, attempt)
        text += event(phase, task, role, f"sha={sha}{marker}")
    return text


class ManifestTests(unittest.TestCase):
    def test_interrupted_framework_task_releases_same_identity(self):
        text = event("TASK_REGISTERED") + dispatch("task-01", "worker")
        acknowledgement = event("DISPATCH_STARTED", fields="agent=agent-1").replace(
            "dispatch=task-01-orchestrator-1", "dispatch=task-01-worker-1")
        text += acknowledgement + event("CLAIMED", role="worker")
        blocked = event("BLOCKED", fields="owner=agent-1 | pointer=recovery.json").replace(
            "dispatch=task-01-orchestrator-1", "dispatch=task-01-worker-1")
        with self.assertRaises(manifest.ManifestError):
            manifest.parse(text + blocked.replace("owner=agent-1", "owner=stale-agent"))
        text += blocked + event("ISSUES_FOUND", fields="attempt=2")
        tasks, _ = manifest.parse(text)
        self.assertEqual(list(tasks), ["task-01"])
        self.assertIsNone(tasks["task-01"]["dispatch"])
        self.assertEqual(tasks["task-01"]["released_dispatch"], "task-01-worker-1")
        text += build(attempt=2) + gates(attempt=2)
        self.assertFalse(manifest.ship_errors(*manifest.parse(text)))

    def test_cancelled_dispatch_relaunch_and_late_evidence(self):
        text = event("TASK_REGISTERED") + dispatch("task-01", "worker")
        text += event("DISPATCH_CANCELLED", fields="dispatch=task-01-worker-1 | pointer=reconciliation.md").replace(" | dispatch=task-01-orchestrator-1", "")
        text += dispatch("task-01", "worker").replace("dispatch=task-01-worker-1", "dispatch=relaunch-1")
        with self.assertRaises(manifest.ManifestError):
            manifest.parse(text + event("CLAIMED", role="worker"))
        text += event("CLAIMED", role="worker").replace("dispatch=task-01-worker-1", "dispatch=relaunch-1")
        self.assertEqual(manifest.parse(text)[0]["task-01"]["phase"], "CLAIMED")

    def test_escalation_blocks_ship_and_dispatch(self):
        escalation = event("ESCALATED", fields="id=E1 | reason=operator decision")
        text = event("TASK_REGISTERED") + build() + gates() + escalation
        self.assertTrue(manifest.ship_errors(*manifest.parse(text)))
        text += event("ESCALATION_RESOLVED", fields="id=E1 | pointer=decision.md")
        self.assertFalse(manifest.ship_errors(*manifest.parse(text)))
        with self.assertRaises(manifest.ManifestError):
            manifest.parse(event("TASK_REGISTERED") + escalation + dispatch("task-01", "worker"))

    def test_dependency_order_and_dispatch(self):
        for dependency in ["missing", "task-01"]:
            with self.assertRaises(manifest.ManifestError):
                manifest.parse(event("TASK_REGISTERED", fields=f"depends_on={dependency}"))
        text = event("TASK_REGISTERED") + event("TASK_REGISTERED", "task-02", fields="depends_on=task-01")
        with self.assertRaises(manifest.ManifestError):
            manifest.parse(text + dispatch("task-02", "worker"))

    def test_verified_requires_criterion_evidence(self):
        text = event("TASK_REGISTERED") + build() + gates()
        with self.assertRaises(manifest.ManifestError):
            manifest.parse(text.replace("criteria_passed=C1", "criteria_passed=SKIPPED"))

    def test_missing_spawn_ack_survives_restart(self):
        text = event("TASK_REGISTERED") + dispatch("task-01", "worker")
        self.assertEqual(manifest.parse(text)[0]["task-01"]["dispatch"]["state"], "requested")
        text += event("CLAIMED", role="worker") + event("CODE_WRITTEN", role="worker", fields="sha=abc")
        self.assertEqual(manifest.parse(text)[0]["task-01"]["phase"], "CODE_WRITTEN")

    def test_same_sha_stale_attempt_rejected(self):
        text = event("TASK_REGISTERED") + build()
        text += event("REVIEW_REQUESTED", fields="sha=abc") + dispatch("task-01", "secarch")
        text += event("REVIEW_FAILED", role="secarch", fields="sha=abc | pointer=report")
        text += event("ISSUES_FOUND", fields="attempt=2") + build(attempt=2)
        text += event("REVIEW_REQUESTED", fields="sha=abc | attempt=2") + dispatch("task-01", "secarch", attempt=2)
        with self.assertRaises(manifest.ManifestError):
            manifest.parse(text + event("REVIEW_PASSED", role="secarch", fields="sha=abc"))

    def test_wrong_run_rejected(self):
        with self.assertRaises(manifest.ManifestError):
            manifest.parse(event("TASK_REGISTERED") + build().replace("run=test", "run=other"))

    def test_only_primary_dispatches(self):
        with self.assertRaises(manifest.ManifestError):
            manifest.parse(event("TASK_REGISTERED") + dispatch("task-01", "worker").replace("| orchestrator |", "| team-arch-1 |"))

    def test_template_and_valid_run(self):
        text = (ROOT / "templates/manifest.log").read_text()
        text += event("TASK_REGISTERED") + build() + gates()
        self.assertEqual(manifest.ship_errors(*manifest.parse(text)), [])

    def test_empty_cannot_ship(self):
        self.assertTrue(manifest.ship_errors(*manifest.parse("")))

    def test_retry_is_ready_again(self):
        text = event("TASK_REGISTERED") + build()
        text += event("REVIEW_REQUESTED", fields="sha=abc")
        text += dispatch("task-01", "secarch")
        text += event("REVIEW_FAILED", role="secarch", fields="sha=abc | pointer=review.md")
        text += event("ISSUES_FOUND", fields="attempt=2") + build(sha="def", attempt=2)
        tasks, _ = manifest.parse(text)
        self.assertEqual(tasks["task-01"]["phase"], "CODE_WRITTEN")
        self.assertEqual(manifest.ship_errors(*manifest.parse(text + gates(sha="def", attempt=2))), [])

    def test_stale_sha_rejected(self):
        text = event("TASK_REGISTERED") + build(sha="new")
        text += event("REVIEW_REQUESTED", fields="sha=old")
        with self.assertRaises(manifest.ManifestError):
            manifest.parse(text)

    def test_duplicate_completion_rejected(self):
        text = event("TASK_REGISTERED") + build() + gates()
        with self.assertRaises(manifest.ManifestError):
            manifest.parse(text + event("DONE", fields="sha=abc"))

    def test_replacement_and_team_scope(self):
        text = event("TASK_REGISTERED", fields="team=team-arch-1")
        text += event("TASK_REGISTERED", "task-02", fields="team=team-arch-1")
        text += event("TASK_REGISTERED", "task-03", fields="team=team-arch-2")
        text += event("REARCHITECT", fields="successor=task-02")
        self.assertTrue(manifest.ship_errors(*manifest.parse(text), team="team-arch-1"))
        text += build("task-02") + gates("task-02")
        self.assertEqual(manifest.ship_errors(*manifest.parse(text), team="team-arch-1"), [])
        self.assertTrue(manifest.ship_errors(*manifest.parse(text)))

    def test_conditions_match_ids(self):
        text = event("TASK_REGISTERED", fields="team=team-arch-1")
        text += event("TASK_REGISTERED", "task-02", fields="team=team-arch-2")
        text += event("REARCHITECT", fields="successor=task-02")
        gate_text = gates("task-02")
        opening = event("CONDITION_OPEN", "task-02", "secarch", "id=C1")
        lines = gate_text.splitlines(keepends=True)
        gate_text = "".join(opening + line if "| REVIEW_PASSED |" in line else line for line in lines)
        text += build("task-02") + gate_text
        self.assertTrue(manifest.ship_errors(*manifest.parse(text), team="team-arch-1"))

    def test_condition_closure_identity(self):
        opening = event("CONDITION_OPEN", role="secarch", fields="id=C1")
        gate_text = "".join(opening + line if "| REVIEW_PASSED |" in line else line
                            for line in gates().splitlines(keepends=True))
        text = event("TASK_REGISTERED") + build() + gate_text
        self.assertTrue(manifest.ship_errors(*manifest.parse(text)))
        with self.assertRaises(manifest.ManifestError):
            manifest.parse(text + event("CONDITION_CLOSED", role="secarch", fields="id=C2 | sha=abc | pointer=proof.md"))
        text += event("TASK_REGISTERED", "remediation") + build("remediation") + gates("remediation")
        text += event("CONDITION_CLOSED", role="secarch", fields="id=C1 | sha=abc | pointer=proof.md | remediation=remediation")
        self.assertEqual(manifest.ship_errors(*manifest.parse(text)), [])

    def test_tester_findings_preserved(self):
        text = event("TASK_REGISTERED") + build()
        text += event("REVIEW_REQUESTED", fields="sha=abc")
        text += dispatch("task-01", "secarch")
        text += event("REVIEW_PASSED", role="secarch", fields="sha=abc")
        text += event("TESTER_ASSIGNED", fields="sha=abc")
        text += dispatch("task-01", "tester")
        text += event("TESTER_FAILED", role="tester", fields="sha=abc | pointer=tester.md")
        self.assertEqual(manifest.parse(text)[0]["task-01"]["pointer"], "tester.md")

    def test_malformed_and_unknown_rejected(self):
        for text in ["0\n", event("BOGUS"), event("DONE", fields="sha=abc")]:
            with self.assertRaises(manifest.ManifestError):
                manifest.parse(text)


if __name__ == "__main__":
    unittest.main()
