"""Correctness tests for forkshell.sh, run as a person would in a terminal."""

import os
import subprocess
import unittest

from test_fileguard import SandboxCase, git


class ForkShellTest(SandboxCase):
    """forkshell.sh from the project folder, with the throwaway home."""

    def forkshell(self, session: str, *words: str, agent: str | None = None,
                  stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        """Run forkshell.sh in a session, on an agent if given, with the given words and input."""
        environ = {name: value for name, value in os.environ.items()
                   if name not in ("CLAUDE_AGENT", "CLAUDE_PROJECT_DIR", "CLAUDE_PID")}
        environ.update({"HOME": str(self.home), "TMPDIR": str(self.home / "tmp"), "TERM": "dumb",
                        "CLAUDE_CODE_SESSION_ID": session})
        if agent is not None:
            environ["CLAUDE_AGENT"] = agent
        return subprocess.run([str(self.saddler / "forkshell.sh"), *words], input=stdin, capture_output=True,
                              text=True, env=environ, cwd=self.root, timeout=60)

    def branch(self) -> str:
        """The branch of the person session human-h1."""
        return "session-human-h1/agent-master"

    def testcommand(self) -> None:
        done = self.forkshell("human-h1", "bash", "-c", "echo mine > a.txt && git commit -qam 'mine too'")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual((self.root / "a.txt").read_text(), "two\n")
        self.assertEqual(git(self.root, "show", self.branch() + ":a.txt"), "mine")

    def testinteractive(self) -> None:
        done = self.forkshell("human-h1", stdin="echo inside $CLAUDE_CODE_SESSION_ID $CLAUDE_AGENT\ncat a.txt\nexit\n")
        self.assertIn("inside human-h1 master\ntwo\n", done.stdout, done.stderr)
        self.assertIn("(fork human-h1/master)", done.stderr)

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
        done = self.forkshell("s-1", "bash", "-c", "cat w.txt && echo person > p.txt")
        self.assertEqual(done.stdout, "agent\n", done.stderr)
        self.assertEqual(self.shell("cat p.txt").stdout, "person\n")

    def testsubagent(self) -> None:
        done = self.forkshell("s-1", "git", "branch", "--show-current", agent="a1")
        self.assertEqual(done.stdout, "session-s-1/agent-a1\n", done.stderr)


if __name__ == "__main__":
    unittest.main()
