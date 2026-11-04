"""Correctness tests for overlayfork.sh, with plain bwrap as the holder's wrapper."""

import os
import shutil
import signal
import subprocess
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

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

    def testignored(self) -> None:
        (self.lock / "ignored").write_bytes(b"target/\0")
        done = self.fork("bash", "-c", "cat target/art; echo w > target/art; echo n > target/n")
        self.assertEqual(done.stdout, "art\n", done.stderr)
        self.assertEqual((self.root / "target" / "art").read_text(), "art\n")
        self.assertFalse((self.root / "target" / "n").exists())
        self.assertEqual(self.fork("cat", "target/n").stdout, "n\n")
        self.assertEqual(self.fork("cat", "target/art", agent="a2").stdout, "art\n")

    def testexclude(self) -> None:
        (self.lock / "ignored").write_bytes(b"target/\0secret.log\0")
        (self.root / "secret.log").write_text("s\n")
        done = self.fork("bash", "-c", "cat secret.log; rm .gitignore; echo n > target/n; echo k > kept.txt")
        self.assertEqual(done.stdout, "s\n", done.stderr)
        tree = git(self.root, "ls-tree", "-r", "--name-only", self.branch).split("\n")
        self.assertIn("kept.txt", tree)
        self.assertNotIn(".gitignore", tree)
        self.assertNotIn("target/n", tree)
        self.assertNotIn("secret.log", tree)

    def testmtime(self) -> None:
        (self.root / "del.txt").write_text("edited\n")
        self.fork("true")
        tree = self.basedir / "tree"
        self.assertEqual((tree / "a.txt").stat().st_mtime_ns, (self.root / "a.txt").stat().st_mtime_ns)
        self.assertNotEqual((tree / "del.txt").stat().st_mtime_ns, (self.root / "del.txt").stat().st_mtime_ns)
        self.assertEqual((tree / "del.txt").read_text(), "gone\n")

    def testremount(self) -> None:
        (self.lock / "ignored").write_bytes(b"target/\0")
        (self.lock / "generation").write_text("1\n")
        self.fork("true")
        os.kill(self.holder("s-1", "a1"), signal.SIGKILL)
        time.sleep(0.1)
        (self.root / "a.txt").write_text("owner\n")
        (self.lock / "generation").write_text("2\n")
        before = time.time_ns()
        done = self.fork("stat", "-c", "%.9Y", "a.txt", "del.txt")
        edited, kept = [int(word.replace(".", "")) for word in done.stdout.split()]
        self.assertGreaterEqual(edited, before - 1_000_000_000, done.stderr)
        self.assertEqual(kept, (self.root / "del.txt").stat().st_mtime_ns)
        self.assertEqual(self.fork("cat", "a.txt").stdout, "two\n")

    def testpreempted(self) -> None:
        with ThreadPoolExecutor(1) as pool:
            late = pool.submit(self.fork, "sleep", "30")
            time.sleep(0.5)
            os.kill(self.holder("s-1", "a1"), signal.SIGKILL)
            done = late.result()
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("preempted", done.stderr)
        self.assertEqual(self.fork("echo", "again").stdout, "again\n")

    def testinterrupted(self) -> None:
        (self.lock / "checkpointing").touch()
        done = self.fork("echo", "ran")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("interrupted", done.stderr)
        self.assertNotIn("ran", done.stdout)

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

    def testgeneration(self) -> None:
        (self.lock / "ignored").write_bytes(b"target/\0")
        (self.lock / "generation").write_text("1\n")
        self.fork("true")
        (self.root / "a.txt").write_text("owner\n")
        (self.lock / "generation").write_text("2\n")
        before = time.time_ns()
        done = self.fork("stat", "-c", "%.9Y", "a.txt")
        self.assertGreaterEqual(int(done.stdout.strip().replace(".", "")), before, done.stderr)
        self.assertEqual((self.folder / "agent-a1" / "generation").read_text(), "2\n")

    @unittest.skipUnless(shutil.which("cargo"), "cargo is not installed")
    def testcargo(self) -> None:
        rustup = Path(os.environ["HOME"]) / ".rustup"
        with (self.box / "whitelist.txt").open("a") as f:
            f.write("ro %s\n" % rustup)
        (self.root / "Cargo.toml").write_text('[package]\nname = "probe"\nversion = "0.1.0"\nedition = "2021"\n')
        (self.root / "src").mkdir()
        (self.root / "src" / "main.rs").write_text('fn main() { println!("BASE"); }\n')
        settings = {"RUSTUP_HOME": str(rustup), "CARGO_HOME": str(self.home / "tmp" / "cargo")}
        with mock.patch.dict(os.environ, settings):
            os.environ.pop("CARGO_TARGET_DIR", None)
            built = self.shell("cargo build --offline -q")
            self.assertEqual(built.returncode, 0, built.stderr)
            git(self.root, "add", "-A")
            git(self.root, "commit", "-qm", "crate")
            done = self.shell("# saddler agent=c1\ncargo run --offline -v")
            self.assertEqual(done.stdout, "BASE\n", done.stderr)
            self.assertIn("Fresh", done.stderr)
            (self.root / "src" / "main.rs").write_text('fn main() { println!("OWNER"); }\n')
            self.assertEqual(self.shell("cargo build --offline -q").returncode, 0)
            os.utime(self.lock / "lastcheckpoint", (1, 1))
            self.shell("true")
            self.assertTrue((self.root / "target" / "debug" / "probe").exists())
            done = self.shell("# saddler agent=c1\ncargo run --offline -q")
            self.assertEqual(done.stdout, "BASE\n", done.stderr)


if __name__ == "__main__":
    unittest.main()
