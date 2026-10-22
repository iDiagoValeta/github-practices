import subprocess
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "github-practices" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from branch_name import check_branch  # noqa: E402


class CheckBranchTests(unittest.TestCase):
    def test_valid_branch_with_gh_issue(self):
        self.assertEqual(check_branch("feature/GH-12-login", "my-repo"), [])

    def test_valid_branch_with_project_key(self):
        self.assertEqual(check_branch("bugfix/ABC-123-crash-on-start", "my-repo"), [])

    def test_internal_may_go_without_issue(self):
        self.assertEqual(check_branch("internal/fix-ci", "my-repo"), [])

    def test_revert_may_go_without_issue(self):
        self.assertEqual(check_branch("revert/undo-login", "my-repo"), [])

    def test_automated_may_go_without_issue(self):
        self.assertEqual(check_branch("automated/sync-main", "my-repo"), [])

    def test_missing_prefix_is_an_error(self):
        problems = check_branch("main", "my-repo")
        self.assertTrue(problems)
        self.assertTrue(any("prefix" in p for p in problems))

    def test_unknown_prefix_is_an_error(self):
        problems = check_branch("chore/GH-1-x", "my-repo")
        self.assertTrue(any("prefix" in p for p in problems))

    def test_missing_issue_is_an_error(self):
        problems = check_branch("feature/login", "my-repo")
        self.assertTrue(any("issue" in p for p in problems))

    def test_lowercase_issue_is_an_error(self):
        problems = check_branch("feature/gh-12-login", "my-repo")
        self.assertTrue(any("issue" in p for p in problems))

    def test_missing_context_after_issue(self):
        problems = check_branch("hotfix/GH-1", "my-repo")
        self.assertTrue(any("context" in p for p in problems))

    def test_does_not_start_with_a_letter(self):
        problems = check_branch("feature/12_bad", "my-repo")
        self.assertTrue(any("letter" in p for p in problems))
        self.assertTrue(any("[A-Za-z0-9-]" in p for p in problems))

    def test_invalid_characters(self):
        problems = check_branch("feature/GH-1-login_new", "my-repo")
        self.assertTrue(any("[A-Za-z0-9-]" in p for p in problems))

    def test_length_63_exactly_passes(self):
        repo = "r" * 54
        self.assertEqual(check_branch("feature/GH-1-abc", repo), [])

    def test_length_64_fails(self):
        repo = "r" * 55
        problems = check_branch("feature/GH-1-abc", repo)
        self.assertTrue(any("63" in p for p in problems))


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "branch_name.py"), *args],
            capture_output=True,
            text=True,
        )

    def test_cli_valid_branch_exits_0(self):
        result = self.run_cli("feature/GH-12-login", "my-repo")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")

    def test_cli_invalid_branch_exits_1(self):
        result = self.run_cli("feature/12_bad", "my-repo")
        self.assertEqual(result.returncode, 1)
        self.assertIn("feature/12_bad", result.stdout)


if __name__ == "__main__":
    unittest.main()
