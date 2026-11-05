"""Correctness tests for forkshell.sh, run as a person would in a terminal."""

import os
import subprocess
import unittest

from test_fileguard import SandboxCase, git


class ForkShellTest(SandboxCase):
    """forkshell.sh from the project folder, with the throwaway home."""

    def forkshell(self, *words: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        """Run forkshell.sh with the given words and input."""
        return subprocess.run([str(self.saddler / "forkshell.sh"), *words], input=stdin, capture_output=True, text=True,
                              env={**os.environ, "HOME": str(self.home), "TMPDIR": str(self.home / "tmp"), "TERM": "dumb"},
                              cwd=self.root, timeout=60)

    def branch(self) -> str:
        """The branch of the only person session, session-human-<name>-<hash>/agent-master."""
        names = [name for name in git(self.root, "for-each-ref", "--format=%(refname:short)", "refs/heads/").split()
                 if name.startswith("session-human-")]
        self.assertEqual(len(names), 1, names)
        return names[0]

    def testcommand(self) -> None:
        done = self.forkshell("h1", "bash", "-c", "echo mine > a.txt && git commit -qam 'mine too'")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual((self.root / "a.txt").read_text(), "two\n")
        self.assertTrue(self.branch().startswith("session-human-h1-"))
        self.assertEqual(git(self.root, "show", self.branch() + ":a.txt"), "mine")

    def testinteractive(self) -> None:
        done = self.forkshell("h1", stdin="echo inside $SADDLER_FORK\ncat a.txt\nexit\n")
        self.assertIn("inside h1\ntwo\n", done.stdout, done.stderr)
        self.assertIn("(fork h1)", done.stderr)

    def testreuse(self) -> None:
        self.forkshell("h1", "bash", "-c", "echo kept > k.txt")
        self.assertEqual(self.forkshell("h1", "cat", "k.txt").stdout, "kept\n")
        self.assertFalse((self.root / "k.txt").exists())

    def testbadname(self) -> None:
        done = self.forkshell("bad name", "true")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("usage", done.stderr)


if __name__ == "__main__":
    unittest.main()
