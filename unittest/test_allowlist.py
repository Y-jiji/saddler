"""Correctness tests for allowlist.sh."""

import subprocess
import unittest

from test_fileguard import SandboxCase


class AllowTest(SandboxCase):
    """allowlist.sh called directly, as a function."""

    def allow(self, command: str, root: str = "") -> subprocess.CompletedProcess[str]:
        """Run a command with the real project mounted writable."""
        return subprocess.run([str(self.saddler / "allowlist.sh"), root or str(self.root),
                               "--bind", str(self.root), str(self.root), "--chdir", str(self.root),
                               "--", "bash", "-c", command],
                              capture_output=True, text=True, env=self.environ("s-1", self.first), timeout=30)

    def testmachine(self) -> None:
        done = self.allow("cat '%s/hidden'; echo x > /usr/evil; echo x > /evil; echo ok > made; git --version" % self.home)
        self.assertIn("No such file", done.stderr)
        self.assertIn("Read-only", done.stderr)
        self.assertEqual((self.root / "made").read_text(), "ok\n")
        self.assertIn("git version", done.stdout)

    def testguard(self) -> None:
        self.assertIn("Read-only", self.allow("echo x > .claude/x").stderr)
        (self.root / "sub" / ".claude").mkdir(parents=True)
        self.assertIn("Read-only", self.allow("echo x > sub/.claude/x").stderr)
        done = self.allow("echo x >> .git/config; touch .git/hooks/x; echo x > .git/fine; echo rc=$?")
        self.assertEqual(done.stdout, "rc=0\n", done.stderr)
        self.assertEqual(done.stderr, "")

    def testprivate(self) -> None:
        done = self.allow("echo sock > ~/.ssh/sock; cat ~/.ssh/config; echo x >> ~/.ssh/config")
        self.assertEqual(done.stdout, "real\n", done.stderr)
        self.assertIn("Read-only", done.stderr)
        self.assertEqual((self.box / "ssh" / "sock").read_text(), "sock\n")
        self.assertFalse((self.home / ".ssh" / "sock").exists())
        self.assertEqual((self.home / ".ssh" / "config").read_text(), "real\n")

    def testrefuse(self) -> None:
        (self.box / "whitelist.txt").unlink()
        done = self.allow("echo ran")
        self.assertNotEqual(done.returncode, 0)
        self.assertNotIn("ran", done.stdout)
        (self.box / "whitelist.txt").write_text("ro /usr\n")
        done = self.allow("echo ran", root=str(self.home / "missing"))
        self.assertNotEqual(done.returncode, 0)
        self.assertNotIn("ran", done.stdout)


if __name__ == "__main__":
    unittest.main()
