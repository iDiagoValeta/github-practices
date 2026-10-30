import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "install.sh"

AGENT_DIRS = {
    "claude-code": ".claude/skills",
    "codex": ".agents/skills",
    "cursor": ".cursor/skills",
    "gemini-cli": ".gemini/skills",
    "github-copilot": ".copilot/skills",
    "opencode": ".config/opencode/skills",
    "windsurf": ".codeium/windsurf/skills",
    "zcode": ".zcode/skills",
}


def run_install(home, *args, script=INSTALL):
    env = dict(os.environ, HOME=str(home))
    return subprocess.run(
        ["bash", str(script), *args],
        env=env,
        capture_output=True,
        text=True,
    )


def target(home, agent):
    return Path(home) / AGENT_DIRS[agent] / "github-practices"


class InstallTests(unittest.TestCase):
    def test_each_agent_installs_its_own_dir(self):
        for agent in AGENT_DIRS:
            with self.subTest(agent=agent), tempfile.TemporaryDirectory() as home:
                result = run_install(home, agent)

                self.assertEqual(result.returncode, 0, result.stderr)
                link = target(home, agent)
                self.assertTrue(link.is_symlink(), "%s missing: %s" % (agent, link))
                self.assertEqual(link.resolve(), (ROOT / "github-practices").resolve())

    def test_installing_twice_returns_zero(self):
        with tempfile.TemporaryDirectory() as home:
            first = run_install(home, "claude-code")
            second = run_install(home, "claude-code")

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)

    def test_several_agents_in_one_call(self):
        with tempfile.TemporaryDirectory() as home:
            result = run_install(home, "claude-code", "opencode")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(target(home, "claude-code").is_symlink())
            self.assertTrue(target(home, "opencode").is_symlink())

    def test_no_agent_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as home:
            result = run_install(home)

            self.assertEqual(result.returncode, 2)
            self.assertIn("usage", result.stderr)

    def test_unknown_agent_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as home:
            result = run_install(home, "not-an-agent")

            self.assertEqual(result.returncode, 2)
            self.assertIn("usage", result.stderr)
            self.assertEqual(list(Path(home).rglob("github-practices")), [])

    def test_list_mentions_every_agent(self):
        with tempfile.TemporaryDirectory() as home:
            result = run_install(home, "--list")

            self.assertEqual(result.returncode, 0, result.stderr)
            for agent in AGENT_DIRS:
                with self.subTest(agent=agent):
                    self.assertIn(agent, result.stdout)

    def test_list_prints_one_exact_line_per_agent(self):
        with tempfile.TemporaryDirectory() as home:
            result = run_install(home, "--list")

            self.assertEqual(result.returncode, 0, result.stderr)
            expected = [
                "%s\t%s" % (agent, Path(home) / directory / "github-practices")
                for agent, directory in AGENT_DIRS.items()
            ]
            self.assertEqual(sorted(result.stdout.splitlines()), sorted(expected))

    def test_install_fails_when_agent_dir_is_a_file(self):
        with tempfile.TemporaryDirectory() as home:
            Path(home, ".copilot").write_text("not a directory\n")

            result = run_install(home, "github-copilot")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertNotIn("installed:", result.stdout)

    def test_install_refuses_foreign_symlink(self):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as other:
            link = target(home, "claude-code")
            link.parent.mkdir(parents=True)
            link.symlink_to(Path(other))

            result = run_install(home, "claude-code")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertTrue(link.is_symlink())
            self.assertEqual(link.resolve(), Path(other).resolve())

    def test_install_and_uninstall_refuse_real_directory(self):
        with tempfile.TemporaryDirectory() as home:
            link = target(home, "claude-code")
            link.mkdir(parents=True)
            sentinel = link / "sentinel.txt"
            sentinel.write_text("keep me\n")

            install = run_install(home, "claude-code")
            uninstall = run_install(home, "--uninstall", "claude-code")

            self.assertEqual(install.returncode, 1, install.stdout + install.stderr)
            self.assertEqual(uninstall.returncode, 1, uninstall.stdout + uninstall.stderr)
            self.assertFalse(link.is_symlink())
            self.assertTrue(sentinel.exists())
            self.assertEqual(sentinel.read_text(), "keep me\n")

    def test_installing_twice_keeps_the_existing_link(self):
        with tempfile.TemporaryDirectory() as home:
            first = run_install(home, "claude-code")
            self.assertEqual(first.returncode, 0, first.stderr)
            link = target(home, "claude-code")
            before = os.lstat(link)

            second = run_install(home, "claude-code")

            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertTrue(link.is_symlink())
            self.assertEqual(link.resolve(), (ROOT / "github-practices").resolve())
            # The second run has to recognise its own link and leave it alone.
            # Removing and recreating it would still resolve to the same place
            # here, so the identity of the link itself is what proves it.
            after = os.lstat(link)
            self.assertEqual(
                (after.st_ino, after.st_mtime_ns),
                (before.st_ino, before.st_mtime_ns),
            )


class UninstallTests(unittest.TestCase):
    def test_uninstall_removes_only_that_agent(self):
        for agent in AGENT_DIRS:
            with self.subTest(agent=agent), tempfile.TemporaryDirectory() as home:
                install = run_install(home, *AGENT_DIRS)
                self.assertEqual(install.returncode, 0, install.stderr)

                result = run_install(home, "--uninstall", agent)

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(target(home, agent).is_symlink(), agent)
                for other in AGENT_DIRS:
                    if other == agent:
                        continue
                    self.assertTrue(target(home, other).is_symlink(), other)

    def test_uninstall_through_symlinked_repo_path(self):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as tmp:
            install = run_install(home, "claude-code")
            self.assertEqual(install.returncode, 0, install.stderr)
            link = target(home, "claude-code")
            self.assertTrue(link.is_symlink())

            shadow_root = Path(tmp) / "shadow"
            shadow_root.symlink_to(ROOT)

            result = run_install(
                home, "--uninstall", "claude-code", script=shadow_root / "install.sh"
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(link.is_symlink())
            self.assertFalse(link.exists())

    def test_foreign_symlink_is_not_deleted(self):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as other:
            link = target(home, "claude-code")
            link.parent.mkdir(parents=True)
            link.symlink_to(Path(other))

            result = run_install(home, "--uninstall", "claude-code")

            self.assertEqual(result.returncode, 1)
            self.assertTrue(link.is_symlink())
            self.assertEqual(link.resolve(), Path(other).resolve())

    def test_own_symlink_is_deleted(self):
        with tempfile.TemporaryDirectory() as home:
            link = target(home, "claude-code")
            link.parent.mkdir(parents=True)
            link.symlink_to(ROOT / "github-practices")

            result = run_install(home, "--uninstall", "claude-code")

            self.assertEqual(result.returncode, 0)
            self.assertFalse(link.is_symlink())
            self.assertFalse(link.exists())


if __name__ == "__main__":
    unittest.main()
