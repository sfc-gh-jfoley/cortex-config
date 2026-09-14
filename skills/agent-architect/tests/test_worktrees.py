import os
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from collect_events import collect
from test_manifest import event, dispatch, gates
from manifest import ManifestError, parse, ship_errors


class WorktreeTests(unittest.TestCase):
    def test_collection_dependencies_and_detached_review(self):
        with tempfile.TemporaryDirectory(prefix="architect-integration-") as temporary:
            root = Path(temporary) / "repo"
            worker = Path(temporary) / "worker"
            dependent = Path(temporary) / "dependent"
            review = Path(temporary) / "review"
            environment = dict(os.environ, GIT_AUTHOR_NAME="Fixture",
                               GIT_AUTHOR_EMAIL="fixture@example.invalid",
                               GIT_COMMITTER_NAME="Fixture",
                               GIT_COMMITTER_EMAIL="fixture@example.invalid")

            def git(*arguments, cwd=root, check=True, content=None):
                return subprocess.run(["git", *arguments], cwd=cwd, env=environment,
                                      input=content, text=True, capture_output=True, check=check)

            def stage(path, content, cwd):
                blob = git("hash-object", "-w", "--stdin", content=content).stdout.strip()
                git("update-index", "--add", "--cacheinfo", f"100644,{blob},{path}", cwd=cwd)

            def persist(text):
                stage(".agent-project/manifest.log", text, root)
                git("commit", "-m", "canonical checkpoint")
                return git("show", "HEAD:.agent-project/manifest.log").stdout

            subprocess.run(["git", "init", "-b", "main", str(root)],
                           env=environment, capture_output=True, check=True)
            git("-c", "core.hooksPath=/dev/null", "commit", "--allow-empty", "-m", "baseline")
            git("worktree", "add", "-b", "worker", str(worker))
            git("worktree", "add", "-b", "dependent", str(dependent))
            stage(".agent-project/events/task-01-worker-r1.log", event("CLAIMED", role="worker"), worker)
            git("commit", "-m", "worker claimed", cwd=worker)
            blob = git("hash-object", "-w", "--stdin", content="synthetic dependency\n").stdout.strip()
            git("update-index", "--add", "--cacheinfo", f"100644,{blob},dependency.txt", cwd=worker)
            git("-c", "core.hooksPath=/dev/null", "commit", "-m", "dependency", cwd=worker)
            artifact = git("rev-parse", "HEAD", cwd=worker).stdout.strip()
            event_path = ".agent-project/events/task-01-worker-r1.log"
            evidence = event("CLAIMED", role="worker") + event("CODE_WRITTEN", role="worker", fields=f"sha={artifact}")
            blob = git("hash-object", "-w", "--stdin", content=evidence).stdout.strip()
            git("update-index", "--add", "--cacheinfo", f"100644,{blob},{event_path}", cwd=worker)
            git("-c", "core.hooksPath=/dev/null", "commit", "-m", "evidence", cwd=worker)
            reference = git("rev-parse", "HEAD", cwd=worker).stdout.strip()
            canonical = event("TASK_REGISTERED") + dispatch("task-01", "worker")
            canonical = canonical.replace("task-01-worker.log", "task-01-worker-r1.log")
            candidate = collect(root, canonical, reference, event_path, "task-01", "worker", "test", 1, "task-01-worker-1")
            candidate = persist(candidate)
            self.assertIn("CODE_WRITTEN", candidate)
            self.assertEqual(collect(root, candidate, reference, event_path, "task-01", "worker", "test", 1, "task-01-worker-1"), candidate)
            self.assertNotEqual(git("cat-file", "-e", f"HEAD:{event_path}", check=False).returncode, 0)
            self.assertNotEqual(git("cat-file", "-e", "HEAD:dependency.txt", cwd=dependent, check=False).returncode, 0)
            self.assertNotEqual(git("checkout", "worker", check=False).returncode, 0)
            git("worktree", "add", "--detach", str(review), artifact)
            self.assertEqual(git("rev-parse", "HEAD", cwd=review).stdout.strip(), artifact)
            for role, requested, verdict in [("secarch", "REVIEW_REQUESTED", "REVIEW_PASSED"),
                                              ("tester", "TESTER_ASSIGNED", "VERIFIED")]:
                if role == "tester":
                    review = Path(temporary) / "tester"
                    git("worktree", "add", "--detach", str(review), artifact)
                candidate += event(requested, fields=f"sha={artifact}") + dispatch("task-01", role, artifact)
                candidate = persist(candidate)
                report_path = f".agent-project/events/task-01-{role}.log"
                record = event(verdict, role=role, fields=f"sha={artifact}")
                if role == "secarch":
                    record = event("CONDITION_OPEN", role=role, fields="id=C1") + record
                else:
                    output = subprocess.run([sys.executable, "-c", "from pathlib import Path; assert Path('dependency.txt').read_text() == 'synthetic dependency\\n'; print('PASS')"],
                                            cwd=review, text=True, capture_output=True, check=True).stdout
                    report = {"task": "task-01", "run": "test", "attempt": 1,
                              "dispatch": "task-01-tester-1", "sha": artifact,
                              "criteria": {"C1": {"status": "PASS", "command": "python dependency assertion", "output": output}}}
                    stage(".agent-project/reports/test.json", json.dumps(report), review)
                blob = git("hash-object", "-w", "--stdin", content=record).stdout.strip()
                git("update-index", "--add", "--cacheinfo", f"100644,{blob},{report_path}", cwd=review)
                git("-c", "core.hooksPath=/dev/null", "commit", "-m", f"{role} evidence", cwd=review)
                evidence_sha = git("rev-parse", "HEAD", cwd=review).stdout.strip()
                git("branch", f"evidence-{role}", evidence_sha)
                if role == "tester":
                    invalid = dict(report)
                    invalid["criteria"] = {"C1": {"status": "SKIPPED", "command": "check", "output": "no runtime"}}
                    stage(".agent-project/reports/test.json", json.dumps(invalid), review)
                    git("commit", "-m", "skipped test evidence", cwd=review)
                    invalid_sha = git("rev-parse", "HEAD", cwd=review).stdout.strip()
                    with self.assertRaises(ManifestError):
                        collect(root, candidate, invalid_sha, report_path, "task-01", role,
                                "test", 1, "task-01-tester-1")
                candidate = collect(root, candidate, evidence_sha, report_path, "task-01", role,
                                    "test", 1, f"task-01-{role}-1")
                candidate = persist(candidate)
            candidate += event("DONE", fields=f"sha={artifact}")
            self.assertTrue(ship_errors(*parse(candidate)))
            self.assertEqual(collect(root, candidate, reference, event_path, "task-01", "worker",
                                     "test", 1, "task-01-worker-1"), candidate)
            candidate += event("TASK_REGISTERED", "remediation")
            from test_manifest import build
            candidate += build("remediation", sha=artifact) + gates("remediation", sha=artifact)
            candidate = persist(candidate)
            closure = event("CONDITION_CLOSED", role="secarch", fields=f"id=C1 | sha={artifact} | pointer=.agent-project/reports/closure.json | remediation=remediation")
            closure_report = {"task": "task-01", "run": "test", "attempt": 1,
                              "dispatch": "task-01-secarch-1", "sha": artifact, "condition": "C1",
                              "remediation": "remediation", "status": "PASS", "output": "Verified remediation"}
            stage(".agent-project/reports/closure.json", json.dumps(closure_report), review)
            closure_path = ".agent-project/events/task-01-secarch.log"
            original = git("show", f"evidence-secarch:{closure_path}").stdout
            blob = git("hash-object", "-w", "--stdin", content=original + closure).stdout.strip()
            git("update-index", "--add", "--cacheinfo", f"100644,{blob},{closure_path}", cwd=review)
            git("-c", "core.hooksPath=/dev/null", "commit", "-m", "condition closure", cwd=review)
            closure_sha = git("rev-parse", "HEAD", cwd=review).stdout.strip()
            candidate = collect(root, candidate, closure_sha, closure_path, "task-01", "secarch",
                                "test", 1, "task-01-secarch-1")
            self.assertEqual(ship_errors(*parse(candidate)), [])
            git("-c", "core.hooksPath=/dev/null", "cherry-pick", artifact, cwd=dependent)
            self.assertEqual(git("show", "HEAD:dependency.txt", cwd=dependent).stdout, "synthetic dependency\n")
            self.assertNotEqual(git("cat-file", "-e", f"HEAD:{event_path}", cwd=dependent, check=False).returncode, 0)


if __name__ == "__main__":
    unittest.main()
