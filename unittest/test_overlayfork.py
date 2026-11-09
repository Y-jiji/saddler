"""Correctness tests for overlayfork.sh, called directly."""

import os
import shutil
import signal
import socket
import subprocess
import time
import unittest
from pathlib import Path
from unittest import mock

from test_fileguard import SandboxCase, git


class ForkTest(SandboxCase):
    """overlayfork.sh called directly, as a function."""

    def setUp(self) -> None:
        super().setUp()
        self.lock.mkdir(parents=True)
        (self.lock / "base").write_text(self.base + "\n")
        self.folder = self.state / "session-s-1"

    def branch(self, agent: str) -> str:
        """The branch of an agent of session s-1."""
        return "session-s-1/agent-" + agent

    def fork(self, *command: str, agent: str = "a1", claude: int = 0,
             cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        """Run a command through overlayfork.sh, registering the agent and making its branch from the base if missing."""
        ref = "refs/heads/" + self.branch(agent)
        if subprocess.run(["git", "-C", str(self.root), "rev-parse", "-q", "--verify", ref]).returncode != 0:
            git(self.root, "update-ref", ref, self.base)
        record = self.lock / ("s-1-" + agent)
        if not record.exists():
            record.write_text("- 0 %s %d\n" % (self.branch(agent), self.first.pid))
        return subprocess.run([str(self.saddler / "overlayfork.sh"), str(self.root), str(record),
                               str(claude or self.first.pid), *command],
                              capture_output=True, text=True, env=self.environ("s-1", self.first),
                              cwd=cwd or self.root, timeout=60)

    @unittest.skipUnless(shutil.which("Xvfb"), "no Xvfb")
    def testdisplay(self) -> None:
        with (self.box / "whitelist.txt").open("a") as whitelist:
            whitelist.write("rw /tmp\n")
        done = self.fork("bash", "-c", "echo $DISPLAY ${WAYLAND_DISPLAY:-none} ${XDG_SESSION_TYPE:-none}")
        number, wayland, session = done.stdout.split()
        self.assertEqual((wayland, session), ("none", "none"), done.stderr)
        self.assertRegex(number, r"^:\d+$")
        with socket.socket(socket.AF_UNIX) as client:
            client.connect("\0/tmp/.X11-unix/X" + number[1:])

    def testview(self) -> None:
        done = self.fork("bash", "-c", 'echo "[$(git status --short)]"; git log --format=%s | tr "\\n" " "; cat target/art')
        self.assertEqual(done.stdout, "[]\nbase old art\n", done.stderr)

    def testreadonly(self) -> None:
        done = self.fork("bash", "-c", "echo x > %s/evil || echo refused; git update-ref refs/remotes/saddler/main HEAD"
                         " || echo refused; git commit -q --allow-empty -m mine && echo committed" % (self.state / "realgit"))
        self.assertEqual(done.stdout.split(), ["refused", "refused", "committed"], done.stderr)
        self.assertFalse((self.root / ".git" / "evil").exists())
        self.assertEqual(git(self.root, "log", "-1", "--format=%s", "main"), "base")

    def testshared(self) -> None:
        self.fork("bash", "-c", "echo n > n.txt; git add n.txt; git commit -qm a1")
        done = self.fork("git", "show", "saddler/%s:n.txt" % self.branch("a1"), agent="a2")
        self.assertEqual(done.stdout, "n\n", done.stderr)
        self.assertEqual(git(self.root, "show", self.branch("a1") + ":n.txt"), "n")
        self.assertFalse((self.root / "n.txt").exists())

    def testpublish(self) -> None:
        self.fork("bash", "-c", "echo n > n.txt; git add n.txt; git commit -qm a1")
        self.assertEqual(git(self.root, "log", "-1", "--format=%s", self.branch("a1")), "a1")
        self.assertEqual(list((self.folder / "agent-a1" / "git" / "objects").glob("??/*")), [])

    def testrewrite(self) -> None:
        self.fork("git", "commit", "-q", "--allow-empty", "-m", "one")
        self.fork("git", "commit", "-q", "--amend", "--allow-empty", "-m", "two")
        self.assertEqual(git(self.root, "log", "-1", "--format=%s", self.branch("a1")), "two")

    def testdropmain(self) -> None:
        self.fork("git", "commit", "-q", "--allow-empty", "-m", "kept")
        git(self.root, "update-ref", "refs/heads/main", git(self.root, "rev-parse", self.branch("a1")))
        done = self.fork("bash", "-c", "git reset -q --hard HEAD~ && git commit -q --allow-empty -m other")
        self.assertIn("not published", done.stderr)
        self.assertEqual(git(self.root, "log", "-1", "--format=%s", self.branch("a1")), "kept")

    def teststrict(self) -> None:
        done = self.fork("bash", "-c", "echo n > n.txt; git add n.txt; k=$(git rev-parse :n.txt); f=.git/objects/${k:0:2}/${k:2};"
                         " chmod u+w $f; printf x > $f; git commit -qm bad")
        self.assertIn("publishing", done.stderr)
        self.assertEqual(git(self.root, "rev-parse", self.branch("a1")), self.base)

    def testalias(self) -> None:
        done = self.fork("bash", "-c", "echo d > a.txt; git checkpoint")
        self.assertIn("commit or discard", done.stderr)

    def testreset(self) -> None:
        self.fork("bash", "-c", "echo kept > k.txt; git add k.txt; git commit -qm kept; echo lost > lost.txt")
        (self.lock / "generation").write_text("1\n")
        done = self.fork("bash", "-c", "cat k.txt; ls lost.txt")
        self.assertIn("checkpoint reset", done.stderr)
        self.assertIn("lost.txt", done.stderr)
        self.assertEqual(done.stdout, "kept\n")

    def testfresh(self) -> None:
        self.fork("bash", "-c", "echo fresh > a.txt; git commit -qam fresh", agent="a3")
        git(self.root, "update-ref", "refs/heads/" + self.branch("a4"), git(self.root, "rev-parse", self.branch("a3")))
        done = self.fork("bash", "-c", "cat a.txt; git status --short", agent="a4")
        self.assertEqual(done.stdout, "fresh\n", done.stderr)
        upper = self.folder / "agent-a4" / "fork"
        self.assertEqual(sorted(str(p.relative_to(upper)) for p in upper.rglob("*") if not p.is_dir()), ["a.txt"])

    def testsizelog(self) -> None:
        self.fork("bash", "-c", "head -c 100000 /dev/zero > big")
        self.fork("true")
        lines = (self.state / "uppersize.log").read_text().splitlines()
        self.assertEqual(len(lines), 1, lines)
        words = lines[0].split()
        self.assertEqual(words[1], "0")
        self.assertTrue(words[2].endswith("agent-a1/fork"), words)
        self.assertGreaterEqual(int(words[3]), 100000)

    def testignored(self) -> None:
        done = self.fork("bash", "-c", "cat target/art; echo w > target/art; echo n > target/n")
        self.assertEqual(done.stdout, "art\n", done.stderr)
        self.assertEqual((self.root / "target" / "art").read_text(), "art\n")
        self.assertFalse((self.root / "target" / "n").exists())
        self.assertEqual(self.fork("cat", "target/art", agent="a2").stdout, "art\n")

    def testcargoclean(self) -> None:
        done = self.fork("bash", "-c", "rm -rf target && ls target")
        self.assertIn("No such file", done.stderr)
        self.assertEqual((self.root / "target" / "art").read_text(), "art\n")

    def testcwd(self) -> None:
        (self.root / "sub").mkdir()
        self.assertEqual(self.fork("pwd", cwd=self.root / "sub").stdout, "%s\n" % (self.root / "sub"))

    def testbackground(self) -> None:
        start = time.monotonic()
        first = self.fork("bash", "-c", "(sleep 1; echo bg > bg.txt) >/dev/null 2>&1 </dev/null &")
        self.assertLess(time.monotonic() - start, 0.9, first.stderr)
        time.sleep(1.1)
        self.assertEqual(self.fork("cat", "bg.txt").stdout, "bg\n")

    def testexitcode(self) -> None:
        self.assertEqual(self.fork("bash", "-c", "exit 7").returncode, 7)

    def testclaudedies(self) -> None:
        claude = self.newclaude()
        self.fork("bash", "-c", "sleep 30 >/dev/null 2>&1 </dev/null &", claude=claude.pid)
        pid = self.holder("s-1", "a1")
        claude.kill()
        claude.wait()
        time.sleep(1.6)
        self.assertNotEqual(subprocess.run(["kill", "-0", str(pid)], capture_output=True).returncode, 0)

    def testreused(self) -> None:
        self.fork("true")
        os.kill(self.holder("s-1", "a1"), signal.SIGKILL)
        time.sleep(0.1)
        other = self.newclaude()
        record = (self.lock / "s-1-a1").read_text().split()
        (self.lock / "s-1-a1").write_text(" ".join([str(other.pid)] + record[1:]) + "\n")
        done = self.fork("echo", "ran")
        self.assertEqual(done.stdout, "ran\n", done.stderr)
        self.assertIsNone(other.poll())

    def testpreempted(self) -> None:
        self.fork("true")
        late = subprocess.Popen([str(self.saddler / "overlayfork.sh"), str(self.root), str(self.lock / "s-1-a1"),
                                 str(self.first.pid), "sleep", "30"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                env=self.environ("s-1", self.first), cwd=self.root)
        self.fork("true")
        time.sleep(0.3)
        os.kill(self.holder("s-1", "a1"), signal.SIGKILL)
        _, err = late.communicate(timeout=10)
        self.assertNotEqual(late.returncode, 0)
        self.assertIn("preempted", err)
        self.assertEqual(self.fork("echo", "again").stdout, "again\n")

    def testinterrupt(self) -> None:
        shim = self.home / "shim"
        shim.mkdir()
        (shim / "sed").write_text("#!/bin/bash\nkill -KILL $PPID\n")
        (shim / "sed").chmod(0o755)
        with mock.patch.dict(os.environ, {"PATH": "%s:%s" % (shim, os.environ["PATH"])}):
            self.assertEqual(self.fork("echo", "ran").returncode, -signal.SIGKILL)
        time.sleep(0.3)
        done = self.fork("echo", "ran")
        self.assertEqual(done.stdout, "ran\n", done.stderr)


if __name__ == "__main__":
    unittest.main()
