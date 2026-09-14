"""Read-only, fail-closed manifest checks for agent-architect."""

import argparse
import json
from pathlib import Path
import re
import sys


class ManifestError(ValueError):
    pass


TASK_PHASES = {
    "TASK_REGISTERED", "CLAIMED", "CODE_WRITTEN", "REVIEW_REQUESTED",
    "REVIEW_PASSED", "REVIEW_FAILED", "ISSUES_FOUND", "TESTER_ASSIGNED",
    "VERIFIED", "TESTER_FAILED", "DONE", "BLOCKED", "REARCHITECT",
}
RUN_PHASES = {
    "INTAKE_COMPLETE", "RESEARCH_COMPLETE", "PLAN_APPROVED", "CHARTERS_DEFINED",
    "TEAMS_LAUNCHED", "TEAM_SHIPPED", "SHIPPED", "ESCALATED",
    "ASSUMPTION_LOGGED", "RUN_STARTED",
}
TRANSITIONS = {
    "CLAIMED": {"TASK_REGISTERED", "ISSUES_FOUND"},
    "CODE_WRITTEN": {"CLAIMED", "ISSUES_FOUND"},
    "REVIEW_REQUESTED": {"CODE_WRITTEN"},
    "REVIEW_PASSED": {"REVIEW_REQUESTED"},
    "REVIEW_FAILED": {"REVIEW_REQUESTED"},
    "TESTER_ASSIGNED": {"REVIEW_PASSED"},
    "VERIFIED": {"TESTER_ASSIGNED"},
    "TESTER_FAILED": {"TESTER_ASSIGNED"},
    "DONE": {"VERIFIED"},
    "ISSUES_FOUND": {"REVIEW_FAILED", "TESTER_FAILED", "BLOCKED"},
}
EVIDENCE_PHASES = {
    "REVIEW_REQUESTED", "REVIEW_PASSED", "REVIEW_FAILED", "TESTER_ASSIGNED",
    "VERIFIED", "TESTER_FAILED", "DONE",
}
WRITERS = {
    "CLAIMED": {"worker"}, "CODE_WRITTEN": {"worker"},
    "REVIEW_PASSED": {"secarch"}, "REVIEW_FAILED": {"secarch"},
    "VERIFIED": {"tester"}, "TESTER_FAILED": {"tester"},
}


def parse(text):
    tasks = {}
    conditions = {}
    run_id = None
    dispatch_ids = set()
    escalations = {}
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 4:
            raise ManifestError(f"line {number}: expected timestamp, task, phase, role")
        timestamp, task_id, phase, role = parts[:4]
        fields = {}
        for part in parts[4:]:
            if "=" in part:
                key, value = part.split("=", 1)
                if key in fields:
                    raise ManifestError(f"line {number}: duplicate field {key}")
                fields[key] = value
        if phase in {"ESCALATED", "ESCALATION_RESOLVED"}:
            if role != "orchestrator" or not fields.get("run") or not fields.get("id"):
                raise ManifestError("escalation requires coordinator, run and id")
            if run_id is not None and run_id != fields["run"]:
                raise ManifestError("escalation belongs to another run")
            run_id = fields["run"]
            identifier = fields["id"]
            if phase == "ESCALATED":
                if identifier in escalations or not fields.get("reason"):
                    raise ManifestError("duplicate escalation or missing reason")
                escalations[identifier] = fields["reason"]
            else:
                if identifier not in escalations or not fields.get("pointer"):
                    raise ManifestError("resolution requires active escalation and evidence")
                del escalations[identifier]
            continue
        if phase in RUN_PHASES:
            continue
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", fields.get("run", "")):
            raise ManifestError(f"line {number}: explicit run identity required")
        if run_id is None:
            run_id = fields["run"]
        if fields["run"] != run_id:
            raise ManifestError(f"line {number}: event belongs to another run")
        if not re.fullmatch(r"[1-9][0-9]*", fields.get("attempt", "")):
            raise ManifestError(f"line {number}: positive attempt required")
        attempt = int(fields["attempt"])
        if task_id in tasks:
            expected_attempt = tasks[task_id]["attempt"] + (phase == "ISSUES_FOUND")
            if phase == "CONDITION_CLOSED":
                origin = tasks[task_id].get("condition_origins", {}).get(fields.get("id"))
                if origin:
                    expected_attempt = origin["attempt"]
            if attempt != expected_attempt:
                raise ManifestError(f"line {number}: stale or unexpected attempt")
        elif phase != "TASK_REGISTERED" or attempt != 1:
            raise ManifestError(f"line {number}: register task at attempt 1 first")
        if phase in {"DISPATCH_REQUESTED", "DISPATCH_STARTED", "DISPATCH_CANCELLED"}:
            task = tasks[task_id]
            if role != "orchestrator":
                raise ManifestError(f"line {number}: only coordinator dispatches")
            dispatch_id = fields.get("dispatch", "")
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", dispatch_id):
                raise ManifestError(f"line {number}: dispatch identity required")
            if phase == "DISPATCH_REQUESTED":
                if escalations:
                    raise ManifestError("unresolved escalation blocks dispatch")
                target = {"TASK_REGISTERED": "worker", "ISSUES_FOUND": "worker",
                          "REVIEW_REQUESTED": "secarch", "TESTER_ASSIGNED": "tester"}.get(task["phase"])
                if not target or fields.get("target") != target:
                    raise ManifestError(f"line {number}: invalid dispatch target or phase")
                if target == "worker":
                    for dependency in task["depends_on"]:
                        if tasks[dependency]["phase"] != "DONE":
                            raise ManifestError(f"dependency {dependency} is not DONE")
                if task["dispatch"] is not None or dispatch_id in dispatch_ids:
                    raise ManifestError(f"line {number}: duplicate or overlapping dispatch")
                if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", fields.get("base", "")):
                    raise ManifestError(f"line {number}: full dispatch base SHA required")
                if target != "worker" and fields["base"] != task["sha"]:
                    raise ManifestError(f"line {number}: review base must match artifact")
                if not fields.get("worktree") or not fields.get("event_path"):
                    raise ManifestError(f"line {number}: dispatch worktree and event path required")
                dispatch_ids.add(dispatch_id)
                task["dispatch"] = {"id": dispatch_id, "target": target, "state": "requested",
                                    "base": fields["base"], "worktree": fields["worktree"],
                                    "event_path": fields["event_path"], "agent": None}
            else:
                dispatch = task["dispatch"]
                if not dispatch or dispatch["id"] != dispatch_id:
                    raise ManifestError(f"line {number}: dispatch not active")
                if phase == "DISPATCH_STARTED":
                    if dispatch["state"] != "requested" or not fields.get("agent"):
                        raise ManifestError(f"line {number}: invalid launch acknowledgement")
                    dispatch.update(state="started", agent=fields["agent"])
                else:
                    if not fields.get("pointer") or dispatch["state"] == "completed":
                        raise ManifestError(f"line {number}: cancellation requires reconciliation evidence")
                    if task["phase"] == "CLAIMED":
                        raise ManifestError(f"line {number}: claimed worker must become BLOCKED first")
                    task["dispatch"] = None
            continue
        if role in {"worker", "secarch", "tester"}:
            dispatch = tasks[task_id]["dispatch"]
            if phase == "CONDITION_OPEN":
                dispatch = tasks[task_id]["dispatch"]
            elif phase == "CONDITION_CLOSED":
                dispatch = tasks[task_id].get("condition_origins", {}).get(fields.get("id"))
            if (not dispatch or dispatch["id"] != fields.get("dispatch")
                    or dispatch["target"] != role
                    or (dispatch["state"] == "completed" and phase not in {"CONDITION_OPEN", "CONDITION_CLOSED"})):
                raise ManifestError(f"line {number}: evidence does not match active dispatch")
        if phase in {"CONDITION_OPEN", "CONDITION_CLOSED"}:
            condition_id = fields.get("id")
            if task_id not in tasks or not condition_id:
                raise ManifestError(f"line {number}: condition requires registered task and id")
            key = (task_id, condition_id)
            if phase == "CONDITION_OPEN":
                if key in conditions or role != "secarch":
                    raise ManifestError(f"line {number}: duplicate or invalid condition opening")
                conditions[key] = False
                tasks[task_id].setdefault("condition_origins", {})[condition_id] = {
                    **dispatch, "attempt": attempt,
                }
            else:
                if key not in conditions or conditions[key] or role != "secarch":
                    raise ManifestError(f"line {number}: invalid condition closure")
                if not fields.get("sha") or not fields.get("pointer"):
                    raise ManifestError(f"line {number}: closure requires sha and evidence pointer")
                remediation = tasks.get(fields.get("remediation"))
                if (not remediation or remediation["phase"] != "DONE"
                        or remediation["sha"] != fields["sha"] or fields.get("remediation") == task_id):
                    raise ManifestError("closure requires distinct DONE remediation task and its SHA")
                conditions[key] = True
            continue
        if phase not in TASK_PHASES:
            raise ManifestError(f"line {number}: unknown phase {phase}")
        coordinator = role == "orchestrator"
        if phase in WRITERS:
            if role not in WRITERS[phase]:
                raise ManifestError(f"line {number}: invalid writer for {phase}")
        elif phase != "BLOCKED" and not coordinator:
            raise ManifestError(f"line {number}: coordinator must write {phase}")
        if phase == "TASK_REGISTERED":
            if task_id in tasks:
                raise ManifestError(f"line {number}: duplicate registration {task_id}")
            dependencies = [] if fields.get("depends_on", "none") == "none" else fields["depends_on"].split(",")
            if task_id in dependencies or any(dependency not in tasks for dependency in dependencies):
                raise ManifestError("register dependencies first; self and unknown dependencies forbidden")
            criteria = fields.get("criteria", "").split(",")
            if not all(criteria) or len(set(criteria)) != len(criteria):
                raise ManifestError("unique acceptance criterion IDs required")
            tasks[task_id] = {"phase": phase, "team": fields.get("team", role),
                              "depends_on": dependencies, "criteria": criteria,
                              "sha": None, "successor": None, "pointer": None,
                              "run": run_id, "attempt": attempt, "dispatch": None}
            continue
        if task_id not in tasks:
            raise ManifestError(f"line {number}: unregistered task {task_id}")
        task = tasks[task_id]
        previous = task["phase"]
        if phase == "BLOCKED" and role == "orchestrator":
            active_dispatch = task["dispatch"]
            if (not active_dispatch or fields.get("dispatch") != active_dispatch["id"]
                    or not active_dispatch.get("agent")
                    or fields.get("owner") != active_dispatch["agent"]
                    or not fields.get("pointer")):
                raise ManifestError("recovery BLOCKED requires current dispatch, recorded owner and reconciliation pointer")
        if previous in {"DONE", "REARCHITECT"}:
            raise ManifestError(f"line {number}: transition after terminal state")
        if phase in TRANSITIONS and previous not in TRANSITIONS[phase]:
            raise ManifestError(f"line {number}: invalid transition {previous} -> {phase}")
        if phase == "CODE_WRITTEN":
            if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", fields.get("sha", "")):
                raise ManifestError(f"line {number}: code requires artifact sha")
            task["sha"] = fields["sha"]
        if phase in EVIDENCE_PHASES:
            if not task["sha"] or fields.get("sha") != task["sha"]:
                raise ManifestError(f"line {number}: verdict does not match current artifact sha")
        if phase == "VERIFIED":
            if not fields.get("pointer") or fields.get("criteria_passed", "").split(",") != task["criteria"]:
                raise ManifestError("VERIFIED requires report pointer and all required criteria")
        if phase in {"REVIEW_FAILED", "TESTER_FAILED"}:
            if not fields.get("pointer"):
                raise ManifestError(f"line {number}: failed gate requires findings pointer")
            task["pointer"] = fields["pointer"]
        if phase == "ISSUES_FOUND":
            task["released_dispatch"] = task["dispatch"]["id"] if task["dispatch"] else None
            task["sha"] = None
            task["attempt"] = attempt
            task["dispatch"] = None
        if phase in {"REVIEW_REQUESTED", "TESTER_ASSIGNED"}:
            task["dispatch"] = None
        if phase in {"CODE_WRITTEN", "REVIEW_PASSED", "REVIEW_FAILED", "VERIFIED", "TESTER_FAILED", "BLOCKED"}:
            if task["dispatch"]:
                task["dispatch"]["state"] = "completed"
                if role == "secarch":
                    task["security_dispatch"] = dict(task["dispatch"])
        if phase == "REARCHITECT":
            successor = fields.get("successor")
            if not successor or successor == task_id:
                raise ManifestError(f"line {number}: invalid successor")
            if successor != "none" and successor not in tasks:
                raise ManifestError(f"line {number}: register successor first")
            task["successor"] = successor
        task["phase"] = phase
    for task in tasks.values():
        task["escalations"] = dict(escalations)
    return tasks, conditions


def ship_errors(tasks, conditions, team=None):
    selected = {task_id for task_id, task in tasks.items() if team is None or task["team"] == team}
    errors = []
    if not selected:
        errors.append("no registered tasks in scope")
    if any(task.get("escalations") for task in tasks.values()):
        errors.append("unresolved run escalation")
    evidence_scope = set(selected)

    def completed(task_id, visited):
        evidence_scope.add(task_id)
        if task_id in visited:
            return False
        task = tasks[task_id]
        if task["phase"] == "DONE":
            return True
        if task["phase"] == "REARCHITECT":
            successor = task["successor"]
            return successor == "none" or completed(successor, visited | {task_id})
        return False

    for task_id in sorted(selected):
        if not completed(task_id, set()):
            errors.append(f"{task_id}: incomplete task or successor")
    for (task_id, condition_id), closed in conditions.items():
        if task_id in evidence_scope and not closed:
            errors.append(f"{task_id}: open condition {condition_id}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["status", "ready", "ship", "recover"])
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--team")
    parser.add_argument("--phase", choices=sorted(TASK_PHASES))
    args = parser.parse_args()
    try:
        tasks, conditions = parse(args.manifest.read_text())
        selected = {key: value for key, value in tasks.items()
                    if args.team is None or value["team"] == args.team}
        if args.command == "recover":
            waiting = {key: value for key, value in selected.items()
                       if value["phase"] in {"TASK_REGISTERED", "ISSUES_FOUND", "REVIEW_REQUESTED", "TESTER_ASSIGNED", "CLAIMED"}}
            print(json.dumps(waiting, sort_keys=True))
        elif args.command == "ready":
            if not args.phase:
                parser.error("ready requires --phase")
            print(json.dumps({key: value for key, value in selected.items()
                              if value["phase"] == args.phase}, sort_keys=True))
        elif args.command == "ship":
            errors = ship_errors(tasks, conditions, args.team)
            print(json.dumps({"ok": not errors, "errors": errors}))
            return int(bool(errors))
        else:
            print(json.dumps({"tasks": selected, "open_conditions": [
                {"task": task, "id": condition} for (task, condition), closed in conditions.items()
                if not closed and task in selected]}, sort_keys=True))
    except (OSError, ManifestError) as error:
        print(json.dumps({"ok": False, "error": str(error)}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
