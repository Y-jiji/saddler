"""Correctness tests for overlayowner.sh, run through sandbox.sh."""

import json
import os
import shutil
import signal
import subprocess
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from test_fileguard import HOOK, WRAPPER, SandboxCase


class OwnerCase(SandboxCase):
    """An owner whose first command has listed target/ as an ignored folder."""

    def setUp(self) -> None:
        super().setUp()
        done = self.shell("true")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.target = self.root / "target"

    def upper(self) -> Path:
        """The owner's upper over target/."""
        return self.root / ".git" / "saddler" / "owner" / "target" / "upper"

    def generation(self) -> int:
        """The number of checkpoints so far."""
        return int((self.lock / "generation").read_text())

    def settle(self) -> None:
        """Make the checkpoint period look elapsed."""
        os.utime(self.lock / "lastcheckpoint", (1, 1))

    def alive(self, pid: int) -> bool:
        """Whether a process exists."""
        return subprocess.run(["kill", "-0", str(pid)], capture_output=True).returncode == 0

    def start(self, command: str) -> subprocess.Popen[str]:
        """Start a command as a tool call would, without waiting for it."""
        return subprocess.Popen([str(self.saddler / "sandbox.sh"), WRAPPER % command.replace("'", "'\\''")],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                env=self.environ("s-1", self.first), cwd=self.root)

    def configured(self, command: str, **settings: str) -> subprocess.CompletedProcess[str]:
        """Run a command with values from the settings env block."""
        return subprocess.run([str(self.saddler / "sandbox.sh"), WRAPPER % command.replace("'", "'\\''")],
                              capture_output=True, text=True, env={**self.environ("s-1", self.first), **settings},
                              cwd=self.root, timeout=60)


class OwnerTest(OwnerCase):
    """What an owner command sees and changes."""

    def testtracked(self) -> None:
        self.shell("# saddler agent=a1\ntrue")
        done = self.shell("echo changed > a.txt")
        self.assertEqual((self.root / "a.txt").read_text(), "changed\n", done.stderr)

    def testignored(self) -> None:
        self.shell("# saddler agent=a1\ntrue")
        done = self.shell("echo new > target/art; echo made > target/made; cat target/art")
        self.assertEqual(done.stdout, "new\n", done.stderr)
        self.assertEqual((self.target / "art").read_text(), "art\n")
        self.assertFalse((self.target / "made").exists())
        self.assertEqual((self.upper() / "made").read_text(), "made\n")
        self.assertEqual(self.shell("cat target/made").stdout, "made\n")

    def testbackground(self) -> None:
        start = time.monotonic()
        self.shell("(sleep 1; echo bg > bg.txt) >/dev/null 2>&1 </dev/null &")
        self.assertLess(time.monotonic() - start, 0.9)
        self.assertEqual(self.shell("echo next").stdout, "next\n")
        time.sleep(1.2)
        self.assertEqual((self.root / "bg.txt").read_text(), "bg\n")
        self.shell("sleep 3 >/dev/null 2>&1 </dev/null &")
        holder = int((self.lock / "ownerholder").read_text().split()[0])
        self.first.kill()
        self.first.wait()
        time.sleep(1.3)
        self.assertTrue(self.alive(holder))
        self.session("s-2")
        second = self.newclaude()
        done = self.shell("echo real > f.txt; cat target/art", "s-2", second)
        self.assertEqual(done.stdout, "art\n", done.stderr)
        self.assertEqual((self.root / "f.txt").read_text(), "real\n")
        time.sleep(2)
        second.kill()
        second.wait()
        self.assertTrue(self.alive(holder))
        time.sleep(2.2)
        self.assertFalse(self.alive(holder))

    def testinterrupt(self) -> None:
        shim = self.home / "shim"
        shim.mkdir()
        (shim / "sed").write_text("#!/bin/bash\nkill -KILL $PPID\n")
        (shim / "sed").chmod(0o755)
        script = [str(self.saddler / "overlayowner.sh"), str(self.root), str(self.lock), str(self.first.pid), "true",
                  "bwrap", "--dev-bind", "/", "/", "--", "true"]
        killed = subprocess.run(script, capture_output=True, cwd=self.root, timeout=30,
                                env={**self.environ("s-1", self.first), "PATH": "%s:%s" % (shim, os.environ["PATH"])})
        self.assertEqual(killed.returncode, -signal.SIGKILL)
        time.sleep(0.3)
        done = self.shell("echo ran")
        self.assertEqual(done.stdout, "ran\n", done.stderr)

    def testreused(self) -> None:
        other = self.newclaude()
        (self.lock / "ownerholder").write_text("%d 1\n" % other.pid)
        done = self.shell("echo ran")
        self.assertEqual(done.stdout, "ran\n", done.stderr)
        self.assertIsNone(other.poll())
        self.assertNotEqual((self.lock / "ownerholder").read_text().split()[0], str(other.pid))

    def testhidden(self) -> None:
        self.assertNotIn("300", self.shell("cat /proc/%d/cmdline" % self.first.pid).stdout)

    def testnogit(self) -> None:
        shutil.rmtree(self.root / ".git")
        done = self.shell("echo x > made; cat target/art")
        self.assertEqual(done.stdout, "art\n", done.stderr)
        self.assertEqual((self.root / "made").read_text(), "x\n")

    def testexitcode(self) -> None:
        self.assertEqual(self.shell("echo x > target/x; exit 7").returncode, 7)
        self.assertEqual((self.target / "x").read_text(), "x\n")


class TriggerTest(OwnerCase):
    """When an owner command's end checkpoints, and what that does to forks."""

    def testunchanged(self) -> None:
        before = self.generation()
        self.shell("ls")
        holder = (self.lock / "ownerholder").read_text()
        self.assertEqual(self.shell("ls; cat target/art").stdout.split()[-1], "art")
        self.assertEqual((self.lock / "ownerholder").read_text(), holder)
        self.assertEqual(self.generation(), before)

    def testnofork(self) -> None:
        before = self.generation()
        self.shell("echo x > target/x")
        self.assertEqual((self.target / "x").read_text(), "x\n")
        self.assertFalse(self.upper().exists())
        self.assertEqual(self.generation(), before + 1)
        self.assertFalse((self.lock / "checkpointing").exists())

    def testperiod(self) -> None:
        self.shell("# saddler agent=a1\ntrue")
        fork = self.holder("s-1", "a1")
        self.shell("echo x > target/x")
        self.assertFalse((self.target / "x").exists())
        self.assertTrue(self.alive(fork))
        self.settle()
        self.shell("true")
        self.assertEqual((self.target / "x").read_text(), "x\n")
        self.assertFalse(self.alive(fork))

    def testconfig(self) -> None:
        self.shell("# saddler agent=a1\ntrue")
        self.configured("echo x > target/x", SADDLER_CHECKPOINT_PERIOD="nonsense")
        self.assertFalse((self.target / "x").exists())
        self.configured("true", SADDLER_CHECKPOINT_PERIOD="0")
        self.assertEqual((self.target / "x").read_text(), "x\n")

    def testowner(self) -> None:
        late = self.start("sleep 1.5")
        time.sleep(0.5)
        self.shell("echo x > target/x")
        self.assertFalse((self.target / "x").exists())
        late.communicate(timeout=30)
        self.assertEqual((self.target / "x").read_text(), "x\n")

    def testdaemon(self) -> None:
        self.shell("(sleep 1; echo d > target/d) >/dev/null 2>&1 </dev/null &")
        self.shell("echo x > target/x")
        self.assertFalse((self.target / "x").exists())
        time.sleep(1.2)
        self.shell("true")
        self.assertEqual((self.target / "x").read_text(), "x\n")
        self.assertEqual((self.target / "d").read_text(), "d\n")

    def testreused(self) -> None:
        self.shell("# saddler agent=a1\ntrue")
        os.kill(self.holder("s-1", "a1"), signal.SIGKILL)
        time.sleep(0.1)
        other = self.newclaude()
        record = (self.lock / "s-1-a1").read_text().split()
        (self.lock / "s-1-a1").write_text(" ".join([str(other.pid)] + record[1:]) + "\n")
        self.settle()
        self.shell("echo x > target/x")
        self.assertEqual((self.target / "x").read_text(), "x\n")
        self.assertIsNone(other.poll())

    def testnested(self) -> None:
        self.shell("(unshare -Urm bash -c 'sleep 1; echo n > target/n') >/dev/null 2>&1 </dev/null & "
                   "sleep 0.2; echo x > target/x")
        self.assertFalse((self.target / "x").exists())
        time.sleep(1.2)
        self.shell("true")
        self.assertEqual((self.target / "x").read_text(), "x\n")
        self.assertEqual((self.target / "n").read_text(), "n\n")

    def testfdclosed(self) -> None:
        program = "import os; os.closerange(3, 256); os.execvp('bash', ['bash', '-c', 'sleep 1; echo f > target/f'])"
        self.shell('python3 -c "%s" >/dev/null 2>&1 </dev/null & sleep 0.2; echo x > target/x' % program)
        self.assertFalse((self.target / "x").exists())
        time.sleep(1.2)
        self.shell("true")
        self.assertEqual((self.target / "x").read_text(), "x\n")
        self.assertEqual((self.target / "f").read_text(), "f\n")

    def testwait(self) -> None:
        self.shell("# saddler agent=a1\ntrue")
        self.settle()
        running = self.start("# saddler agent=a1\nsleep 1.5; echo slept")
        time.sleep(0.5)
        queue = str(self.lock / "checkpoint" / "queue")
        with ThreadPoolExecutor(1) as pool:
            owner = pool.submit(self.shell, "echo x > target/x")
            while subprocess.run(["flock", "-n", queue, "true"]).returncode == 0:
                time.sleep(0.01)
            self.assertFalse(owner.done())
            late = self.shell("# saddler agent=a2\ncat target/x")
            owner.result()
        self.assertEqual(late.stdout, "x\n", late.stderr)
        out, err = running.communicate(timeout=30)
        self.assertEqual((running.returncode, out), (0, "slept\n"), err)

    def testpreempt(self) -> None:
        foreground = self.start("# saddler agent=a1\nsleep 30")
        background = self.start("# saddler agent=a2 nolock\nsleep 30")
        time.sleep(0.5)
        begin = time.monotonic()
        done = self.configured("echo x > target/x", SADDLER_CHECKPOINT_PERIOD="0", SADDLER_PREEMPT_WAIT="1")
        self.assertLess(time.monotonic() - begin, 10, done.stderr)
        self.assertEqual(done.returncode, 0, done.stderr)
        for killed in (foreground, background):
            _, err = killed.communicate(timeout=10)
            self.assertNotEqual(killed.returncode, 0)
            self.assertIn("preempted", err)
        self.assertEqual((self.target / "x").read_text(), "x\n")
        self.assertEqual(self.shell("# saddler agent=a1\ncat target/x").stdout, "x\n")


class MoveTest(OwnerCase):
    """What a checkpoint leaves in the real folders."""

    def testwhiteout(self) -> None:
        self.shell("rm target/art")
        self.assertFalse((self.target / "art").exists())

    def testopaque(self) -> None:
        (self.target / "old").mkdir()
        (self.target / "old" / "o").write_text("o\n")
        self.shell("rm -rf target/old; mkdir target/old; echo n > target/old/n")
        self.assertEqual([p.name for p in (self.target / "old").iterdir()], ["n"])

    def testreplace(self) -> None:
        (self.target / "file").write_text("f\n")
        (self.target / "dir").mkdir()
        (self.target / "dir" / "in").write_text("i\n")
        done = self.shell("echo new > target/art; rm target/file; mkdir target/file; echo c > target/file/c; "
                          "rm -rf target/dir; echo f > target/dir; mkdir -p target/a/b; echo s > target/a/b/s; "
                          "ln target/art target/link")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual((self.target / "art").read_text(), "new\n")
        self.assertEqual((self.target / "file" / "c").read_text(), "c\n")
        self.assertEqual((self.target / "dir").read_text(), "f\n")
        self.assertEqual((self.target / "a" / "b" / "s").read_text(), "s\n")
        self.assertEqual((self.target / "art").stat().st_ino, (self.target / "link").stat().st_ino)

    def testxattr(self) -> None:
        self.shell("echo new > target/art; mkdir target/d; echo x > target/d/x")
        marks = [mark for folder, folders, files in os.walk(self.target) for name in folders + files
                 for mark in os.listxattr(os.path.join(folder, name)) if mark.startswith("user.overlay.")]
        self.assertEqual(marks, [])
        self.assertEqual(self.shell("echo again > target/art; cat target/d/x").stdout, "x\n")
        self.assertEqual((self.target / "art").read_text(), "again\n")

    def testresume(self) -> None:
        self.shell("# saddler agent=a1\ntrue")
        self.shell("echo x > target/x; echo y > target/art")
        os.link(self.upper() / "x", self.target / "x")
        (self.lock / "checkpointing").touch()
        trash = self.root / ".git" / "saddler" / "trash"
        trash.mkdir()
        (trash / "junk").write_text("junk\n")
        done = self.shell("true")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual((self.target / "x").read_text(), "x\n")
        self.assertEqual((self.target / "art").read_text(), "y\n")
        self.assertFalse((self.lock / "checkpointing").exists())
        self.assertFalse(trash.exists())

    def testlist(self) -> None:
        (self.root / ".gitignore").write_text("target/\nbuild/\n*.log\nlocal.json\n")
        (self.root / "build").mkdir()
        (self.root / "build" / "b").write_text("b\n")
        (self.root / "x.log").write_text("x\n")
        (self.root / ".claude" / "local.json").write_text("{}\n")
        self.shell("true")
        entries = set((self.lock / "ignored").read_bytes().split(b"\0")) - {b""}
        self.assertEqual(entries, {b"build/", b"target/", b"x.log"})
        self.shell("echo z > build/z")
        self.assertEqual((self.root / "build" / "z").read_text(), "z\n")
        for path, denied in ((self.target / "x", True), (self.root / "target2", False), (self.root / "x.log", False)):
            done = subprocess.run(["python3", str(HOOK)], capture_output=True, text=True, check=True,
                                  input=json.dumps({"session_id": "s-1", "tool_name": "Write",
                                                    "tool_input": {"file_path": str(path)}}),
                                  env=self.environ("s-1", self.first))
            self.assertEqual("deny" in done.stdout, denied, path)


if __name__ == "__main__":
    unittest.main()
