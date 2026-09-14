"""Validate committed role evidence and emit a candidate canonical manifest."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

from manifest import ManifestError, parse


def collect(repository, canonical, reference, event_path, task_id, role, run_id, attempt, dispatch_id):
    tasks, _ = parse(canonical)
    task = tasks.get(task_id)
    if not task or task["run"] != run_id:
        raise ManifestError("collection must match registered task and run")
    receipt = "# COLLECTED " + json.dumps({"commit": reference, "path": event_path,
        "task": task_id, "role": role, "run": run_id, "attempt": attempt,
        "dispatch": dispatch_id}, sort_keys=True)
    if receipt in canonical.splitlines():
        return canonical
    dispatch = task["dispatch"]
    active = (task["attempt"] == attempt and dispatch and dispatch["id"] == dispatch_id
              and dispatch["target"] == role and dispatch["event_path"] == event_path)
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", reference):
        raise ManifestError("reference must be a pinned full commit SHA")
    if not re.fullmatch(r"\.agent-project/events/[A-Za-z0-9_.-]+\.log", event_path):
        raise ManifestError("event path must be a task-scoped events/*.log file")
    result = subprocess.run(
        ["git", "-C", str(repository), "show", f"{reference}:{event_path}"],
        capture_output=True, text=True, check=True,
    )
    existing = {line.strip() for line in canonical.splitlines() if line.strip()}
    additions = []
    permitted = {
        "worker": {"CLAIMED", "CODE_WRITTEN", "BLOCKED"},
        "secarch": {"REVIEW_PASSED", "REVIEW_FAILED", "CONDITION_OPEN", "CONDITION_CLOSED"},
        "tester": {"VERIFIED", "TESTER_FAILED"},
    }
    if role not in permitted:
        raise ManifestError("invalid publisher role")
    for line in result.stdout.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 4 or parts[1] != task_id or parts[3] != role or parts[2] not in permitted[role]:
            raise ManifestError("event outside assigned task, role, or phase scope")
        fields = dict(part.split("=", 1) for part in parts[4:] if "=" in part)
        if fields.get("run") != run_id or fields.get("attempt") != str(attempt) or fields.get("dispatch") != dispatch_id:
            raise ManifestError("event belongs to another run, attempt, or dispatch")
        if line.strip() not in existing:
            if parts[2] in {"VERIFIED", "CONDITION_CLOSED"}:
                pointer = fields.get("pointer", "")
                if not re.fullmatch(r"\.agent-project/reports/[A-Za-z0-9_.-]+\.json", pointer):
                    raise ManifestError("structured committed report path required")
                report_result = subprocess.run(["git", "-C", str(repository), "show", f"{reference}:{pointer}"],
                                               capture_output=True, text=True, check=True)
                try:
                    report = json.loads(report_result.stdout)
                except ValueError as error:
                    raise ManifestError("invalid JSON evidence report") from error
                expected = {"task": task_id, "run": run_id, "attempt": attempt,
                            "dispatch": dispatch_id, "sha": fields.get("sha")}
                if not isinstance(report, dict) or any(report.get(key) != value for key, value in expected.items()):
                    raise ManifestError("report identity does not match event")
                if parts[2] == "VERIFIED":
                    results = report.get("criteria")
                    if not isinstance(results, dict) or set(results) != set(task["criteria"]):
                        raise ManifestError("report must cover exactly the required criteria")
                    if any(not isinstance(value, dict) or value.get("status") != "PASS"
                           or not value.get("command") or not value.get("output") for value in results.values()):
                        raise ManifestError("mandatory criteria require passing execution evidence")
                elif (report.get("condition") != fields.get("id")
                      or report.get("remediation") != fields.get("remediation")
                      or report.get("status") != "PASS" or not report.get("output")):
                    raise ManifestError("closure report requires verified remediation evidence")
            if not active:
                origin = task.get("condition_origins", {}).get(fields.get("id"))
                if (parts[2] != "CONDITION_CLOSED" or role != "secarch" or not origin
                        or origin["id"] != dispatch_id or origin["attempt"] != attempt
                        or origin["event_path"] != event_path):
                    raise ManifestError("new evidence does not match active dispatch or condition origin")
            additions.append(line)
            existing.add(line.strip())
    candidate = canonical.rstrip() + "\n" + "\n".join(additions)
    candidate = candidate.rstrip() + "\n"
    parse(candidate)
    return candidate + receipt + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("commit")
    parser.add_argument("event_path")
    parser.add_argument("task_id")
    parser.add_argument("role", choices=["worker", "secarch", "tester"])
    parser.add_argument("run_id")
    parser.add_argument("attempt", type=int)
    parser.add_argument("dispatch_id")
    args = parser.parse_args()
    try:
        candidate = collect(args.repository, args.manifest.read_text(), args.commit,
                            args.event_path, args.task_id, args.role, args.run_id,
                            args.attempt, args.dispatch_id)
    except (OSError, ManifestError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        return 1
    sys.stdout.write(candidate)
    return 0


if __name__ == "__main__":
    sys.exit(main())
