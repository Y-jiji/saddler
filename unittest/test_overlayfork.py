"""Correctness tests for overlayfork.sh, with plain bwrap as the holder's wrapper."""

import subprocess
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

from test_fileguard import SandboxCase, git


class ForkTest(SandboxCase):
    """overlayfork.sh called directly, as a function."""

    def setUp(self) -> None:
        super().setUp()
        self.lock.mkdir(parents=True)
        self.folder = self.state / "session-s-1"
        self.basedir = self.folder / ("commit-" + self.base)
        self.branch = "saddler/s-1/a1"
        git(self.root, "update-ref", "refs/heads/" + self.branch, self.base)

    def fork(self, *command: str, agent: str = "a1", base: str = "", claude: int = 0) -> subprocess.CompletedProcess[str]:
        """Run a command through overlayfork.sh."""
        env = self.environ("s-1", self.first)
        return subprocess.run([str(self.saddler / "overlayfork.sh"), str(self.root), base or self.base, str(self.basedir),
                               str(self.folder / ("agent-" + agent)), str(self.lock / ("s-1-" + agent)),
                               "saddler/s-1/" + agent, str(claude or self.first.pid),
                               "bwrap", "--dev-bind", "/", "/", "--", *command],
                              capture_output=True, text=True, env=env, cwd=self.root, timeout=60)

    def testview(self) -> None:
        (self.root / "b.txt").write_text("main\n")
        git(self.root, "add", "b.txt")
        git(self.root, "commit", "-qm", "main")
        done = self.fork("bash", "-c", 'echo "[$(git status --short)]"; git log --format=%s | tr "\\n" " "; ls b.txt; cat target/art')
        self.assertEqual(done.stdout.split("\n")[:2], ["[]", "base old "], done.stderr)
        self.assertIn("b.txt", done.stderr)
        self.assertIn("target/art", done.stderr)

    def testreadonly(self) -> None:
        done = self.fork("bash", "-c", "git add -A; echo add=$?; git commit -qm x; echo commit=$?; git merge master; echo merge=$?; echo x > .git/evil; echo write=$?; ls %s; echo see=$?" % self.basedir)
        words = dict(line.split("=") for line in done.stdout.split() if "=" in line)
        for key in ("add", "commit", "merge", "write"):
            self.assertNotEqual(words[key], "0", key)
        self.assertEqual(git(self.root, "log", "-1", "--format=%s"), "base")
        self.assertFalse((self.root / ".git" / "evil").exists())

    def testcommit(self) -> None:
        (self.root / ".gitignore").write_text("target/\n*.lock\n")
        (self.root / "Cargo.lock").write_text("pinned\n")
        git(self.root, "add", "-A")
        git(self.root, "add", "-f", "Cargo.lock")
        git(self.root, "commit", "-qm", "more")
        self.base = git(self.root, "rev-parse", "HEAD")
        self.basedir = self.folder / ("commit-" + self.base)
        git(self.root, "update-ref", "refs/heads/" + self.branch, self.base)
        self.fork("bash", "-c", "echo edit > a.txt; rm del.txt; echo n > 'x y.txt'; mkdir target; echo o > target/out")
        diff = git(self.root, "diff", "--name-status", self.base, self.branch)
        self.assertEqual(sorted(diff.split("\n")), ["A\tx y.txt", "D\tdel.txt", "M\ta.txt"])
        self.assertEqual(git(self.root, "rev-parse", self.branch + "^"), self.base)
        self.assertEqual((self.root / "a.txt").read_text(), "two\n")
        self.assertEqual(git(self.root, "status", "--short"), "")
        self.fork("bash", "-c", "echo more > m.txt")
        self.assertEqual(git(self.root, "rev-list", "--count", "%s..%s" % (self.base, self.branch)), "1")
        tip = git(self.root, "rev-parse", self.branch)
        self.fork("true")
        self.assertEqual(git(self.root, "rev-parse", self.branch), tip)
        self.fork("bash", "-c", "git checkout -q -- 2>/dev/null; cp .git/HEAD /dev/null; rm m.txt 'x y.txt'; echo two > a.txt; git show HEAD:del.txt > del.txt")
        self.assertEqual(git(self.root, "rev-parse", self.branch), self.base)

    def testbase(self) -> None:
        with ThreadPoolExecutor(4) as pool:
            done = list(pool.map(lambda n: self.fork("bash", "-c", "ls | wc -l", agent="r%d" % n), range(4)))
        self.assertEqual([d.stdout.strip() for d in done], ["2"] * 4, [d.stderr for d in done])
        self.assertEqual([p.name for p in self.folder.iterdir() if p.name.startswith("commit-") and "." in p.name], [])
        bad = self.folder / "commit-bad"
        self.basedir = bad
        done = self.fork("echo", "ran", base="nosuchcommit", agent="b")
        self.assertNotEqual(done.returncode, 0)
        self.assertNotIn("ran", done.stdout)
        self.assertFalse(bad.exists())

    def testbackground(self) -> None:
        start = time.monotonic()
        first = self.fork("bash", "-c", "(sleep 1; echo bg > bg.txt) >/dev/null 2>&1 </dev/null &")
        self.assertLess(time.monotonic() - start, 0.9, first.stderr)
        done = self.fork("bash", "-c", "echo next > next.txt; ls next.txt")
        self.assertEqual(done.stdout, "next.txt\n", done.stderr)
        self.assertIn("next.txt", git(self.root, "ls-tree", "-r", "--name-only", self.branch))
        time.sleep(1.1)
        self.assertEqual(self.fork("cat", "bg.txt").stdout, "bg\n")
        with ThreadPoolExecutor(2) as pool:
            start = time.monotonic()
            list(pool.map(lambda _: self.fork("sleep", "0.5"), range(2)))
        self.assertLess(time.monotonic() - start, 0.95)

    def testexitcode(self) -> None:
        self.assertEqual(self.fork("bash", "-c", "echo e > e.txt; exit 7").returncode, 7)
        self.assertIn("e.txt", git(self.root, "ls-tree", "-r", "--name-only", self.branch))

    def testclaudedies(self) -> None:
        claude = self.newclaude()
        self.fork("bash", "-c", "sleep 30 >/dev/null 2>&1 </dev/null &", claude=claude.pid)
        pid = self.holder("s-1", "a1")
        claude.kill()
        claude.wait()
        time.sleep(1.6)
        self.assertEqual(subprocess.run(["kill", "-0", str(pid)], capture_output=True).returncode != 0, True)


if __name__ == "__main__":
    unittest.main()
