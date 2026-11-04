"""Correctness tests for gitlock.sh and gitwrap.sh."""

import os
import shlex
import shutil
import subprocess
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

from test_fileguard import SandboxCase, git


class LockTest(SandboxCase):
    """gitlock.sh called directly, as a function."""

    def setUp(self) -> None:
        super().setUp()
        self.lock.mkdir(parents=True)
        (self.lock / "queue").touch()
        (self.lock / "mode").touch()

    def locked(self, mode: str, *command: str, wait: str = "30") -> subprocess.CompletedProcess[str]:
        """Run a command under the lock."""
        return subprocess.run([str(self.saddler / "gitlock.sh"), str(self.lock), mode, wait, *command],
                              capture_output=True, text=True, timeout=30)

    def testshare(self) -> None:
        start = time.monotonic()
        with ThreadPoolExecutor(2) as pool:
            list(pool.map(lambda _: self.locked("read", "sleep", "0.5"), range(2)))
        self.assertLess(time.monotonic() - start, 0.95)

    def testwait(self) -> None:
        with ThreadPoolExecutor(1) as pool:
            start = time.monotonic()
            early = pool.submit(self.locked, "read", "sleep", "0.6")
            time.sleep(0.2)
            self.locked("write", "true")
            self.assertGreaterEqual(time.monotonic() - start, 0.55)
            early.result()

    def testbackground(self) -> None:
        done = self.locked("read", "bash", "-c", "sleep 2 >/dev/null 2>&1 </dev/null & exit 7")
        self.assertEqual(done.returncode, 7)
        self.assertEqual(self.locked("write", "true", wait="0.2").returncode, 0)

    def testlimit(self) -> None:
        with ThreadPoolExecutor(1) as pool:
            early = pool.submit(self.locked, "read", "sleep", "0.8")
            time.sleep(0.2)
            done = self.locked("write", "echo", "ran", wait="0.2")
            early.result()
        self.assertEqual(done.returncode, 1)
        self.assertEqual(done.stdout, "")
        self.assertIn("waited 0.2s", done.stderr)

    def testwrap(self) -> None:
        real = os.path.realpath(shutil.which("git"))
        hook = self.root / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\ngit rev-parse HEAD >/dev/null\n")
        hook.chmod(0o755)
        wrapper = shlex.join([str(self.saddler / "gitlock.sh"), str(self.lock), "write", "30", "/.realgit"])
        (self.root / "n.txt").write_text("n\n")
        done = subprocess.run([str(self.saddler / "allowlist.sh"), str(self.root), str(self.root),
                               "--bind", str(self.root), str(self.root),
                               "--ro-bind", real, "/.realgit", "--ro-bind", str(self.saddler / "gitwrap.sh"), real,
                               "--setenv", "GIT_WRAPPER", wrapper, "--chdir", str(self.root), "--", "bash", "-c",
                               "git add n.txt; git commit -qm n; echo rc=$?; git rev-parse -q --verify nope; echo rc=$?"],
                              capture_output=True, text=True, env=self.environ("s-1", self.first), timeout=30)
        self.assertEqual(done.stdout.split(), ["rc=0", "rc=1"], done.stderr)

    def testnames(self) -> None:
        real = os.path.realpath(shutil.which("git"))
        wrapper = shlex.join([str(self.saddler / "gitlock.sh"), str(self.lock), "write", "30", "/.realgit"])
        done = subprocess.run([str(self.saddler / "allowlist.sh"), str(self.root), str(self.root),
                               "--bind", str(self.root), str(self.root),
                               "--ro-bind", real, "/.realgit", "--ro-bind", str(self.saddler / "gitwrap.sh"), real,
                               "--setenv", "GIT_WRAPPER", wrapper, "--chdir", str(self.root), "--", "bash", "-c",
                               "git push -q . HEAD:pushed; echo rc=$?; git fetch -q . HEAD:fetched; echo rc=$?; git clone -q . copy; echo rc=$?"],
                              capture_output=True, text=True, env=self.environ("s-1", self.first), timeout=30)
        self.assertEqual(done.stdout.split(), ["rc=0", "rc=0", "rc=0"], done.stderr)
        self.assertEqual(git(self.root, "rev-parse", "pushed"), self.base)
        self.assertEqual(git(self.root, "rev-parse", "fetched"), self.base)
        self.assertTrue((self.root / "copy" / "a.txt").exists())


if __name__ == "__main__":
    unittest.main()
