"""Correctness tests for git checkpoint: requestcheckpoint.sh and checkpoint.sh, through sandbox.sh."""

import fcntl
import os
import subprocess
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

from test_fileguard import SandboxCase, git


class CheckpointCase(SandboxCase):
    """Agents of session s-1 on the throwaway project."""

    def agent(self, command: str, agent: str = "a1", **env: str) -> subprocess.CompletedProcess[str]:
        """Run a command as one subagent, with extra environment."""
        with mock.patch.dict(os.environ, env):
            return self.shell("# saddler agent=%s\n%s" % (agent, command))

    def exists(self, ref: str) -> bool:
        """Whether a ref or object exists in the real project."""
        return subprocess.run(["git", "-C", str(self.root), "cat-file", "-e", ref],
                              capture_output=True).returncode == 0


class RequestTest(CheckpointCase):
    """requestcheckpoint.sh refusals, inside an agent's view."""

    def testunclean(self) -> None:
        done = self.agent("echo d > a.txt; git checkpoint")
        self.assertIn("commit or discard", done.stderr)
        self.assertEqual(git(self.root, "rev-parse", "main"), self.base)

    def testnotfastforward(self) -> None:
        self.agent("true")
        ahead = git(self.root, "commit-tree", self.base + "^{tree}", "-p", self.base, "-m", "ahead")
        git(self.root, "update-ref", "refs/heads/main", ahead)
        done = self.agent("git commit -q --allow-empty -m mine; git checkpoint")
        self.assertIn("merge saddler/main first", done.stderr)
        self.assertEqual(git(self.root, "rev-parse", "main"), ahead)

    def testbuildfails(self) -> None:
        done = self.agent("git commit -q --allow-empty -m mine; git checkpoint", SADDLER_BUILD="exit 3")
        self.assertIn("SADDLER_BUILD failed", done.stderr)
        self.assertEqual(git(self.root, "rev-parse", "main"), self.base)


class CheckpointTest(CheckpointCase):
    """checkpoint.sh, run when a command that asked for it ends."""

    def testmove(self) -> None:
        done = self.agent("echo moved > a.txt; git commit -qam moved; git checkpoint",
                          SADDLER_BUILD="mkdir -p target && echo built > target/out")
        self.assertIn("every agent's base", done.stderr)
        tip = git(self.root, "rev-parse", "main")
        self.assertEqual(git(self.root, "log", "-1", "--format=%s", tip), "moved")
        self.assertEqual((self.root / "a.txt").read_text(), "moved\n")
        self.assertEqual((self.root / "target" / "out").read_text(), "built\n")
        self.assertEqual((self.root / "target" / "art").read_text(), "art\n")
        self.assertEqual(git(self.root, "status", "--porcelain", "--untracked-files=no"), "")
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), tip)
        self.assertFalse(self.exists("refs/heads/session-s-1/agent-a1"))
        self.assertEqual((self.lock / "base").read_text().strip(), tip)
        self.assertEqual((self.lock / "generation").read_text().strip(), "1")
        self.assertFalse((self.lock / "checkpointing").exists())

    def testreset(self) -> None:
        self.agent("echo lost > lost.txt; echo kept > k.txt; git add k.txt; git commit -qm kept", agent="a2")
        self.agent("echo moved > a.txt; git commit -qam moved; git checkpoint")
        done = self.agent("cat a.txt k.txt; git log -1 --format=%s saddler/main; ls lost.txt", agent="a2")
        self.assertIn("checkpoint reset", done.stderr)
        self.assertIn("lost.txt", done.stderr)
        self.assertEqual(done.stdout, "two\nkept\nmoved\n")

    def teststale(self) -> None:
        self.agent("true")
        (self.state / "session-s-1" / "agent-a1" / "git" / "checkpoint").write_text(self.base + "\n")
        (self.lock / "generation").write_text("5\n")
        done = subprocess.run([str(self.saddler / "checkpoint.sh"), str(self.root), str(self.state), str(self.lock / "s-1-a1")],
                              capture_output=True, text=True, env=self.environ("s-1", self.first), timeout=30)
        self.assertIn("ran first", done.stderr)

    def testsingle(self) -> None:
        self.agent("true")
        with open(self.lock / "checkpoint", "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            done = self.agent("git commit -q --allow-empty -m mine; git checkpoint")
        self.assertIn("another checkpoint is running", done.stderr)
        self.assertFalse((self.state / "session-s-1" / "agent-a1" / "git" / "checkpoint").exists())
        self.assertEqual(git(self.root, "rev-parse", "main"), self.base)

    def testpreempt(self) -> None:
        self.agent("true", agent="a2")
        with ThreadPoolExecutor(1) as pool:
            late = pool.submit(self.agent, "sleep 30", "a2")
            time.sleep(0.5)
            start = time.monotonic()
            self.agent("git commit -q --allow-empty -m mine; git checkpoint", SADDLER_PREEMPT_WAIT="1")
            self.assertLess(time.monotonic() - start, 10)
            self.assertIn("preempted", late.result().stderr)

    def testrescue(self) -> None:
        self.agent("echo mine > a.txt; git commit -qam mine")
        (self.root / "a.txt").write_text("edited\n")
        done = self.agent("git checkpoint")
        rescued = [r for r in git(self.root, "for-each-ref", "--format=%(refname:short)", "refs/heads/").split() if r.startswith("rescue-")]
        self.assertEqual(len(rescued), 1, done.stderr)
        self.assertEqual(git(self.root, "show", rescued[0] + ":a.txt"), "edited")
        self.assertEqual((self.root / "a.txt").read_text(), "mine\n")

    def testrecover(self) -> None:
        self.agent("echo moved > a.txt; git commit -qam moved")
        tip = git(self.root, "rev-parse", "session-s-1/agent-a1")
        (self.lock / "request").write_text("%s\nrefs/heads/main\n1\n%s\n" % (tip, self.state / "session-s-1" / "agent-a1"))
        (self.lock / "checkpointing").touch()
        done = self.shell("echo ran")
        self.assertEqual(done.stdout, "ran\n", done.stderr)
        self.assertEqual((self.root / "a.txt").read_text(), "moved\n")
        self.assertEqual(git(self.root, "rev-parse", "main"), tip)
        self.assertFalse((self.lock / "checkpointing").exists())

    def testgc(self) -> None:
        self.agent("true")
        loose = subprocess.run(["git", "-C", str(self.root), "hash-object", "-w", "--stdin"], input="unreachable\n",
                               capture_output=True, text=True, check=True).stdout.strip()
        self.agent("git commit -q --allow-empty -m mine; git checkpoint")
        self.assertFalse(self.exists(loose))


if __name__ == "__main__":
    unittest.main()
