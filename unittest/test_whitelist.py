"""Correctness tests for whitelist.sh."""

import os
import socket
import subprocess
import time
import unittest
from unittest import mock

from test_fileguard import SandboxCase


class AllowTest(SandboxCase):
    """whitelist.sh called directly, as a function."""

    def allow(self, command: str, *lines: str, options: tuple[str, ...] | None = None) -> subprocess.CompletedProcess[str]:
        """Run a command with whitelist.txt and the real project read-write and guarded, then the given lines,
        with the bwrap options given, else --chdir to the project."""
        listed = self.home / "lines.txt"
        listed.write_text("rw %s\nguard %s\n" % (self.root, self.root) + "".join(line + "\n" for line in lines))
        bwrap = list(options) if options is not None else ["--chdir", str(self.root)]
        return subprocess.run([str(self.saddler / "whitelist.sh"), str(self.box / "whitelist.txt"), str(listed),
                               "--", *bwrap, "--", "bash", "-c", command],
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

    def testssh(self) -> None:
        listener = socket.socket(socket.AF_UNIX)
        self.addCleanup(listener.close)
        listener.bind(str(self.home / ".ssh" / "cm"))
        listener.listen(1)
        done = self.allow("cat ~/.ssh/config; echo x > ~/.ssh/x;"
                          " python3 -c 'import socket; socket.socket(socket.AF_UNIX).connect(\"%s\")' && echo reached"
                          % (self.home / ".ssh" / "cm"))
        self.assertEqual(done.stdout, "real\nreached\n", done.stderr)
        self.assertIn("Read-only", done.stderr)
        self.assertFalse((self.home / ".ssh" / "x").exists())

    def testsocket(self) -> None:
        listener = socket.socket(socket.AF_UNIX)
        self.addCleanup(listener.close)
        listener.bind(str(self.home / "sock"))
        with (self.box / "whitelist.txt").open("a") as whitelist:
            whitelist.write("ro ~/sock\n")
        done = self.allow("test -e ~/sock && echo seen")
        self.assertEqual(done.stdout, "")
        self.assertIn("is a socket", done.stderr)

    def testprivate(self) -> None:
        state = self.home / ".local" / "state" / "tool"
        state.mkdir(parents=True)
        (state / "old").write_text("real\n")
        with (self.box / "whitelist.txt").open("a") as whitelist:
            whitelist.write("private ~/.local/state/tool\nprivate ~/hidden\n")
        done = self.allow("cat ~/.local/state/tool/old; echo new > ~/.local/state/tool/new && cat ~/.local/state/tool/new")
        self.assertEqual(done.stdout, "real\nnew\n", done.stderr)
        self.assertFalse((state / "new").exists())
        self.assertIn("not a folder", done.stderr)

    def testdbus(self) -> None:
        address = "unix:path=%s" % (self.home / "bus")
        bus = {**os.environ, "DBUS_SESSION_BUS_ADDRESS": address}
        for words in (["dbus-daemon", "--session", "--nofork", "--address=" + address],
                      ["dbus-test-tool", "echo", "--name=com.example.Echo"]):
            daemon = subprocess.Popen(words, env=bus, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.addCleanup(daemon.wait)
            self.addCleanup(daemon.kill)
            time.sleep(0.3)
        with (self.box / "whitelist.txt").open("a") as whitelist:
            whitelist.write("dbus-system com.example.Echo com.example.Iface.Allowed@/\n")
        call = "dbus-send --system --print-reply --dest=com.example.Echo / com.example.Iface.%s"
        with mock.patch.dict(os.environ, {"DBUS_SYSTEM_BUS_ADDRESS": address}):
            done = self.allow("%s; %s; test -e ~/bus || echo hidden" % (call % "Allowed", call % "Other"))
        self.assertIn("method return", done.stdout, done.stderr)
        self.assertIn("AccessDenied", done.stderr)
        self.assertIn("hidden", done.stdout)

    def testrefuse(self) -> None:
        (self.box / "whitelist.txt").unlink()
        done = self.allow("echo ran")
        self.assertNotEqual(done.returncode, 0)
        self.assertNotIn("ran", done.stdout)
        (self.box / "whitelist.txt").write_text("ro /usr\n")
        locked = self.root / "locked"
        locked.mkdir()
        locked.chmod(0)
        self.addCleanup(locked.chmod, 0o755)
        done = self.allow("echo ran")
        self.assertIn("cannot scan", done.stderr)
        self.assertNotIn("ran", done.stdout)

    def testguardlast(self) -> None:
        done = self.allow("ls -A '%s'; cat '%s/.claude/settings.json'; echo x > '%s/.claude/x'" % ((self.root,) * 3),
                          options=("--tmpfs", str(self.root)))
        self.assertEqual(done.stdout, ".claude\n{}\n", done.stderr)
        self.assertIn("Read-only", done.stderr)

    def testusage(self) -> None:
        done = subprocess.run([str(self.saddler / "whitelist.sh"), str(self.box / "whitelist.txt"), "--", "bash", "-c", "echo ran"],
                              capture_output=True, text=True, env=self.environ("s-1", self.first), timeout=30)
        self.assertIn("usage", done.stderr)
        self.assertNotIn("ran", done.stdout)


if __name__ == "__main__":
    unittest.main()
