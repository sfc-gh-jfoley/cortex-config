import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def frontmatter(path):
    text = path.read_text()
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert match, f"{path} has no frontmatter"
    return dict(line.split(":", 1) for line in match.group(1).splitlines() if ":" in line)


class SkillStructure(unittest.TestCase):
    def test_skill_frontmatter(self):
        meta = frontmatter(ROOT / "SKILL.md")
        self.assertEqual(meta["name"].strip(), "agent-architect")
        self.assertIn("team-workflow", meta["description"])
        self.assertIn("Triggers:", meta["description"])

    def test_role_frontmatter_matches_team_workflow_format(self):
        meta = frontmatter(ROOT / "roles" / "security-reviewer.md")
        for key in ("name", "description", "agent_type", "phase", "teammate"):
            self.assertIn(key, meta)
        self.assertEqual(meta["phase"].strip(), "Verify")
        self.assertEqual(meta["teammate"].strip(), "true")

    def test_role_name_matches_skill_usage(self):
        role = frontmatter(ROOT / "roles" / "security-reviewer.md")["name"].strip()
        skill = (ROOT / "SKILL.md").read_text()
        self.assertEqual(role, "security-reviewer")
        self.assertIn(f"`{role}`", skill)
        self.assertNotIn("agent-security-reviewer", skill)

    def test_role_follows_bundled_role_structure(self):
        text = (ROOT / "roles" / "security-reviewer.md").read_text()
        for section in ("## Authorized", "## Prohibited", "## Output Contract", "## Claim Loop"):
            self.assertIn(section, text)
        self.assertIn("cortex ctx step claim -t {task_id} --role security-reviewer", text)
        self.assertIn("cortex ctx step done", text)
        self.assertIn("Step <step_id> complete:", text)
        self.assertIn("Step <step_id> FAILED:", text)
        self.assertIn("git worktree add --detach", text)

    def test_role_does_not_depend_on_a_skill_relative_path(self):
        text = (ROOT / "roles" / "security-reviewer.md").read_text()
        for line in text.splitlines():
            if "security-checklist.md" in line:
                self.assertTrue("~/.snowflake" in line or "references/security-checklist.md" in line, line)
        self.assertNotIn("](../", text)

    def test_skill_forbids_verifier_edits_and_task_tool_roles(self):
        skill = (ROOT / "SKILL.md").read_text()
        self.assertIn("do not edit implementation files", skill)
        self.assertIn("`spawn_teammate`", skill)
        self.assertNotIn("worktree_isolation", skill)

    def test_every_referenced_path_exists(self):
        for doc in [ROOT / "SKILL.md", *(ROOT / "roles").glob("*.md"), *(ROOT / "references").glob("*.md")]:
            for ref in re.findall(r"`((?:roles|references)/[\w./-]+\.md)`", doc.read_text()):
                self.assertTrue((ROOT / ref).exists(), f"{doc.name} references missing {ref}")

    def test_no_leftover_ledger_vocabulary(self):
        banned = ["manifest.py", "collect_events", "event.py", "recovery.py", "manifest.log", "ARCH_SKILL_ROOT", "model-map"]
        for doc in ROOT.rglob("*.md"):
            text = doc.read_text()
            for word in banned:
                self.assertNotIn(word, text, f"{doc.relative_to(ROOT)} still mentions {word}")

    def test_has_stopping_points_and_no_force_flags(self):
        text = (ROOT / "SKILL.md").read_text()
        self.assertIn("## Stopping points", text)
        self.assertNotIn("--force", text.replace("without `--force`", "").replace("without --force", ""))


if __name__ == "__main__":
    unittest.main()
