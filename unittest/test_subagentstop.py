"""Correctness tests for subagentstop.sh, run in a confined hook shell."""

import subprocess
import time
import unittest

from test_fileguard import SandboxCase, git


class StopTest(SandboxCase):
    """Ending a fork leaves its work on its branch, with no merge."""

    def stopped(self, session: str = "s-1", agent: str = "a1") -> None:
        """A SubagentStop for one agent."""
        done = self.event({"hook_event_name": "SubagentStop", "session_id": session, "agent_id": agent}, session)
        self.assertEqual(done.returncode, 0, done.stderr)

    def testbranchkept(self) -> None:
        self.shell("# saddler agent=a1\necho edit > a.txt; rm del.txt")
        pid = self.holder("s-1", "a1")
        self.stopped()
        self.assertEqual(sorted(git(self.root, "diff", "--name-status", self.base, "saddler/s-1/a1").split("\n")),
                         ["D\tdel.txt", "M\ta.txt"])
        self.assertEqual((self.root / "a.txt").read_text(), "two\n")
        self.assertTrue((self.root / "del.txt").exists())
        self.assertEqual(git(self.root, "log", "-1", "--format=%s"), "base")
        self.assertFalse((self.state / "session-s-1" / "agent-a1").exists())
        self.assertFalse((self.lock / "s-1-a1").exists())
        self.assertFalse((self.state / "session-s-1" / ("commit-" + self.base)).exists())
        self.assertNotEqual(subprocess.run(["kill", "-0", str(pid)], capture_output=True).returncode, 0)
        done = self.shell("git merge -q --no-edit saddler/s-1/a1; echo rc=$?; cat a.txt")
        self.assertEqual(done.stdout.split(), ["rc=0", "edit"], done.stderr)

    def testnochange(self) -> None:
        self.shell("# saddler agent=a1\ntrue")
        self.stopped()
        self.assertEqual(git(self.root, "branch", "--list", "saddler/*"), "")

    def testlatefile(self) -> None:
        self.shell("# saddler agent=a1\n(sleep 0.2; echo late > late.txt) >/dev/null 2>&1 </dev/null &")
        time.sleep(0.5)
        self.stopped()
        self.assertEqual(git(self.root, "show", "saddler/s-1/a1:late.txt"), "late")

    def testsessionend(self) -> None:
        self.shell("true")
        self.session("s-2")
        second = self.newclaude()
        self.shell("echo mine > m.txt", "s-2", second)
        done = self.event({"hook_event_name": "SessionEnd", "session_id": "s-2"}, "s-2", second)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(git(self.root, "show", "saddler/s-2/master:m.txt"), "mine")
        self.assertFalse((self.root / "m.txt").exists())
        self.assertFalse((self.state / "session-s-2").exists())

    def testrecover(self) -> None:
        self.session("s-2")
        second = self.newclaude()
        self.shell("true")
        self.shell("echo mine > m.txt", "s-2", second)
        second.kill()
        second.wait()
        time.sleep(1.3)
        done = self.event({"hook_event_name": "SessionStart", "session_id": "s-1"})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(git(self.root, "show", "saddler/s-2/master:m.txt"), "mine")
        self.assertFalse((self.lock / "s-2-master").exists())

    def testlivekept(self) -> None:
        self.shell("# saddler agent=a1\necho live > l.txt")
        pid = self.holder("s-1", "a1")
        done = self.event({"hook_event_name": "SessionStart", "session_id": "s-1"})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((self.lock / "s-1-a1").exists())
        self.assertEqual(subprocess.run(["kill", "-0", str(pid)], capture_output=True).returncode, 0)
        self.assertEqual(self.shell("# saddler agent=a1\ncat l.txt").stdout, "live\n")

    def testkeepfail(self) -> None:
        self.shell("# saddler agent=a1\necho k > k.txt")
        (self.box / "whitelist.txt").rename(self.box / "off")
        try:
            subprocess.run(["bash", str(self.saddler / "subagentstop.sh")], capture_output=True, text=True,
                           input='{"hook_event_name":"SubagentStop","session_id":"s-1","agent_id":"a1"}',
                           env=self.environ("s-1", self.first), cwd=self.root, timeout=60)
        finally:
            (self.box / "off").rename(self.box / "whitelist.txt")
        self.assertTrue((self.state / "session-s-1" / "agent-a1" / "fork").is_dir())
        self.assertTrue((self.lock / "s-1-a1").exists())


if __name__ == "__main__":
    unittest.main()
