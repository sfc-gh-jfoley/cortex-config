"""Evaluate explicit recovery observations without mutating platform state."""

import argparse
import json
from pathlib import Path


def decide(observation):
    required = ("run", "dispatch", "agent", "task")
    if not isinstance(observation, dict) or any(
        not isinstance(observation.get(key), str) or not observation[key].strip()
        for key in required
    ):
        raise ValueError("explicit framework run, dispatch, agent and task IDs required")
    attempt = observation.get("attempt")
    if type(attempt) is not int or attempt < 1:
        raise ValueError("positive framework attempt required")

    def result(action, retry=False):
        return {"action": action, "retry_allowed": retry,
                "identity": {key: observation[key] for key in required}}

    status = observation.get("agent_status")
    if status == "running":
        return result("WAIT_OR_REQUEST_AUTHORIZED_CANCELLATION")
    if status not in {"cancelled", "failed", "completed"}:
        return result("RECONCILE_AGENT_LIVENESS")
    if observation.get("evidence_checked") is not True:
        return result("COLLECT_AND_VALIDATE_COMMITTED_EVIDENCE")
    if observation.get("terminal_evidence") is True:
        return result("RESUME_FROM_VALIDATED_TERMINAL_EVIDENCE")
    if observation.get("terminal_evidence") is not False:
        return result("RECONCILE_TERMINAL_EVIDENCE")
    if observation.get("children_inventory_complete") is not True:
        return result("RECONCILE_CHILD_INVENTORY")
    children = observation.get("children")
    if not isinstance(children, list):
        raise ValueError("children must be an explicit list")
    seen = set()
    for child in children:
        if not isinstance(child, dict) or not isinstance(child.get("shell"), str) or not child["shell"]:
            raise ValueError("every child requires a shell ID")
        if child["shell"] in seen:
            raise ValueError("duplicate shell observation")
        seen.add(child["shell"])
        if child.get("dispatch") != observation["dispatch"]:
            return result("RECONCILE_CHILD_OWNERSHIP_DO_NOT_KILL")
        if child.get("status") not in {"running", "completed", "killed"}:
            return result("RECONCILE_CHILD_LIVENESS")
    if any(child["status"] == "running" for child in children):
        return result("STOP_OWNED_CHILDREN_AND_CONFIRM_TERMINATION")
    claim = observation.get("framework_claim")
    if not isinstance(claim, dict):
        raise ValueError("explicit framework claim observation required")
    if claim.get("status") == "claimed":
        if claim.get("owner") != observation["agent"]:
            return result("RECONCILE_CLAIM_OWNER_DO_NOT_RELEASE")
        if claim.get("dispatch") != observation["dispatch"] or claim.get("attempt") != attempt:
            return result("STALE_CLAIM_DO_NOT_RELEASE")
        return result("COMMIT_BLOCKED_THEN_ISSUES_FOUND_FOR_SAME_TASK")
    if claim.get("status") == "pending" and claim.get("owner") is None:
        if (claim.get("attempt") != attempt + 1 or claim.get("dispatch") is not None
                or claim.get("released_dispatch") != observation["dispatch"]
                or claim.get("release_committed") is not True):
            return result("VERIFY_COMMITTED_FRAMEWORK_RELEASE")
        return result("DISPATCH_SAME_TASK_WITH_NEW_ATTEMPT", True)
    return result("RECONCILE_CLAIM_STATE")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observations", type=Path)
    args = parser.parse_args()
    try:
        decision = decide(json.loads(args.observations.read_text()))
    except (ValueError, OSError) as error:
        parser.exit(1, f"Invalid recovery observations: {error}\n")
    print(json.dumps(decision, sort_keys=True))
    return 0 if decision["retry_allowed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
