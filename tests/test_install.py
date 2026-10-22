import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "install.sh"


class UninstallTests(unittest.TestCase):
    def run_install(self, home, *args):
        env = dict(os.environ, HOME=str(home))
        return subprocess.run(
            ["bash", str(INSTALL), *args],
            env=env,
            capture_output=True,
            text=True,
        )

    def target(self, home):
        return Path(home) / ".claude" / "skills" / "github-practices"

    def test_foreign_symlink_is_not_deleted(self):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as other:
            target = self.target(home)
            target.parent.mkdir(parents=True)
            target.symlink_to(Path(other))

            result = self.run_install(home, "--uninstall")

            self.assertEqual(result.returncode, 1)
            self.assertTrue(target.is_symlink())
            self.assertEqual(target.resolve(), Path(other).resolve())

    def test_own_symlink_is_deleted(self):
        with tempfile.TemporaryDirectory() as home:
            target = self.target(home)
            target.parent.mkdir(parents=True)
            target.symlink_to(ROOT / "github-practices")

            result = self.run_install(home, "--uninstall")

            self.assertEqual(result.returncode, 0)
            self.assertFalse(target.is_symlink())
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
