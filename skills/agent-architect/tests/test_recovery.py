import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("recovery", Path(__file__).resolve().parents[1] / "scripts/recovery.py")
recovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recovery)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.observation = dict(run="run-1", dispatch="dispatch-1", agent="agent-1",
                                task="task-1", attempt=1, agent_status="cancelled",
                                evidence_checked=True, terminal_evidence=False,
                                children_inventory_complete=True, children=[],
                                framework_claim={"status": "claimed", "owner": "agent-1", "dispatch": "dispatch-1", "attempt": 1})

    def test_live_probe_surviving_shell_blocks_retry(self):
        self.observation["children"] = [{"shell": "14ce5", "dispatch": "dispatch-1", "status": "running"}]
        decision = recovery.decide(self.observation)
        self.assertFalse(decision["retry_allowed"])
        self.assertEqual(decision["action"], "STOP_OWNED_CHILDREN_AND_CONFIRM_TERMINATION")

    def test_unknown_agent_blocks(self):
        self.observation["agent_status"] = "unknown"
        self.assertFalse(recovery.decide(self.observation)["retry_allowed"])

    def test_incomplete_inventory_blocks(self):
        self.observation["children_inventory_complete"] = False
        self.assertEqual(recovery.decide(self.observation)["action"], "RECONCILE_CHILD_INVENTORY")

    def test_foreign_shell_not_killed(self):
        self.observation["children"] = [{"shell": "other", "dispatch": "other", "status": "running"}]
        self.assertEqual(recovery.decide(self.observation)["action"], "RECONCILE_CHILD_OWNERSHIP_DO_NOT_KILL")

    def test_release_is_not_reassignment(self):
        self.assertFalse(recovery.decide(self.observation)["retry_allowed"])
        self.observation["framework_claim"] = {"status": "pending", "owner": None,
            "attempt": 2, "dispatch": None, "released_dispatch": "dispatch-1", "release_committed": True}
        self.assertTrue(recovery.decide(self.observation)["retry_allowed"])

    def test_stale_dispatch_cannot_release_new_owner(self):
        self.observation["framework_claim"]["dispatch"] = "new-dispatch"
        self.assertEqual(recovery.decide(self.observation)["action"], "STALE_CLAIM_DO_NOT_RELEASE")

    def test_platform_claim_does_not_control_release(self):
        self.observation["claim"] = {"status": "claimed", "owner": "unrelated-platform-owner"}
        self.assertEqual(recovery.decide(self.observation)["action"], "COMMIT_BLOCKED_THEN_ISSUES_FOUND_FOR_SAME_TASK")

    def test_other_claim_owner_blocks(self):
        self.observation["framework_claim"]["owner"] = "other-agent"
        self.assertEqual(recovery.decide(self.observation)["action"], "RECONCILE_CLAIM_OWNER_DO_NOT_RELEASE")

    def test_terminal_evidence_prevents_duplicate_execution(self):
        self.observation["terminal_evidence"] = True
        self.assertFalse(recovery.decide(self.observation)["retry_allowed"])

    def test_missing_identity_rejected(self):
        del self.observation["task"]
        with self.assertRaises(ValueError):
            recovery.decide(self.observation)
