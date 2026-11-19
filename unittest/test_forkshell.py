"""Correctness tests for forkshell.sh, run as a person would in a terminal."""

import os
import subprocess
import unittest

from test_fileguard import SandboxCase, git


class ForkShellTest(SandboxCase):
    """forkshell.sh from the project folder, with the throwaway home."""

    def forkshell(self, name: str, *words: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        """Run forkshell.sh on the view of branch name, with the given words and input."""
        environ = {name: value for name, value in os.environ.items()
                   if name not in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_AGENT", "CLAUDE_PROJECT_DIR", "CLAUDE_PID",
                                   "SADDLER_VIEW")}
        environ.update({"HOME": str(self.home), "TMPDIR": str(self.home / "tmp"), "TERM": "dumb"})
        return subprocess.run([str(self.saddler / "forkshell.sh"), name, *words], input=stdin, capture_output=True,
                              text=True, env=environ, cwd=self.root, timeout=60)

    def branch(self) -> str:
        """The branch of the person's view human-h1."""
        return "human-h1"

    def testcommand(self) -> None:
        done = self.forkshell("human-h1", "bash", "-c", "echo mine > a.txt && git commit -qam 'mine too'")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual((self.root / "a.txt").read_text(), "two\n")
        self.assertEqual(git(self.root, "show", self.branch() + ":a.txt"), "mine")

    def testinteractive(self) -> None:
        done = self.forkshell("human-h1", stdin="echo inside $SADDLER_VIEW\ncat a.txt\nexit\n")
        self.assertIn("inside human-h1\ntwo\n", done.stdout, done.stderr)
        self.assertIn("(fork human-h1)", done.stderr)

    def testreuse(self) -> None:
        self.forkshell("human-h1", "bash", "-c", "echo kept > k.txt")
        self.assertEqual(self.forkshell("human-h1", "cat", "k.txt").stdout, "kept\n")
        self.assertFalse((self.root / "k.txt").exists())

    def testwritable(self) -> None:
        done = self.forkshell("human-h1", "bash", "-c", "echo x > .claude/x && echo y >> ~/.ssh/config && cat ~/hidden")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout, "hidden\n")
        self.assertFalse((self.root / ".claude" / "x").exists())
        self.assertEqual((self.home / ".ssh" / "config").read_text(), "real\ny\n")

    def testbadname(self) -> None:
        done = self.forkshell("bad name", "true")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("usage", done.stderr)

    def testagent(self) -> None:
        self.shell("echo agent > w.txt")
        done = self.forkshell("session-s-1", "bash", "-c", "cat w.txt && echo person > p.txt")
        self.assertEqual(done.stdout, "agent\n", done.stderr)
        self.assertEqual(self.shell("cat p.txt").stdout, "person\n")

    def testsubagent(self) -> None:
        done = self.forkshell("session-s-1-agent-a1", "git", "branch", "--show-current")
        self.assertEqual(done.stdout, "session-s-1-agent-a1\n", done.stderr)

    def testdefault(self) -> None:
        done = self.forkshell("main", "true")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("default branch", done.stderr)

    def testexisting(self) -> None:
        git(self.root, "branch", "feature-x", "main~1")
        done = self.forkshell("feature-x", "bash", "-c", "git branch --show-current && cat a.txt")
        self.assertEqual(done.stdout, "feature-x\none\n", done.stderr)


if __name__ == "__main__":
    unittest.main()
