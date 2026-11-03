"""Correctness tests for the fileguard hook and sandbox.sh."""

import fcntl
import json
import os
import subprocess
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Final
from unittest import mock
from urllib.parse import quote

REPO: Final = Path(__file__).resolve().parent.parent
HOOK: Final = REPO / "fileguard" / "pretoolusewrite.py"
SANDBOX: Final = REPO / "fileguard" / "sandbox.sh"
WRAPPER: Final = "source /dev/null 2>/dev/null || true && eval '# saddler root=%s session=s1 %s\n%s' < /dev/null"
TIMED: Final = "date +%s.%N; sleep 1; date +%s.%N"


def runhook(payload: dict[str, object], home: str) -> dict[str, object]:
    """Run the hook on a payload from a session in this repository, under a
    throwaway home; its parsed output, empty when it prints nothing."""
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(REPO), "HOME": home}
    done = subprocess.run(["python3", str(HOOK)], input=json.dumps(payload), capture_output=True,
                          text=True, env=env, check=True)
    return json.loads(done.stdout) if done.stdout else {}


def runshell(invocation: str, home: str, wait: int = 100) -> subprocess.CompletedProcess[str]:
    """Run sandbox.sh on an invocation as Claude Code would, under a throwaway
    home with an empty registry."""
    box = Path(home, ".claude", "sandbox")
    box.mkdir(parents=True, exist_ok=True)
    (box / "allow").touch()
    env = {**os.environ, "HOME": home, "TMPDIR": "", "SADDLER_WAIT": str(wait)}
    return subprocess.run(["bash", str(SANDBOX), invocation], capture_output=True, text=True,
                          env=env, cwd=home, timeout=30)


def runpair(first: str, second: str, home: str) -> tuple[float, float]:
    """Run TIMED under the first tag and, once it is under way, the second;
    when the first ended and when the second started."""
    root = Path(home, "proj")
    root.mkdir(exist_ok=True)
    with ThreadPoolExecutor(1) as pool:
        early = pool.submit(runshell, WRAPPER % (root, first, TIMED), home)
        time.sleep(0.4)
        late = runshell(WRAPPER % (root, second, TIMED), home)
    return float(early.result().stdout.split()[1]), float(late.stdout.split()[0])


class HookTest(unittest.TestCase):
    """pretoolusewrite.py on hook payloads."""

    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.home = holder.name

    def testbash(self) -> None:
        output = runhook({"tool_name": "Bash", "session_id": "s1", "tool_input": {"command": "ls"}}, self.home)
        command = output["hookSpecificOutput"]["updatedInput"]["command"]
        self.assertEqual(command, "# saddler root=%s session=s1\nls" % quote(str(REPO), safe=""))

    def testmonitor(self) -> None:
        output = runhook({"tool_name": "Monitor", "session_id": "s1", "tool_input": {"command": "ls"}}, self.home)
        command = output["hookSpecificOutput"]["updatedInput"]["command"]
        self.assertEqual(command, "# saddler root=%s session=s1\nls" % quote(str(REPO), safe=""))

    def testagent(self) -> None:
        output = runhook({"tool_name": "Bash", "session_id": "s1", "agent_id": "a1",
                          "tool_input": {"command": "ls"}}, self.home)
        command = output["hookSpecificOutput"]["updatedInput"]["command"]
        self.assertEqual(command, "# saddler root=%s session=s1 agent=a1\nls" % quote(str(REPO), safe=""))

    def testinput(self) -> None:
        tooluse = {"command": "echo 'a'\necho b", "description": "d", "timeout": 5, "run_in_background": True}
        output = runhook({"tool_name": "Bash", "session_id": "s1", "tool_input": tooluse}, self.home)
        updated = output["hookSpecificOutput"]["updatedInput"]
        self.assertEqual(updated["command"].split("\n", 1)[1], tooluse["command"])
        self.assertEqual({**updated, "command": tooluse["command"]}, tooluse)

    def testfiledeny(self) -> None:
        for tool in ("Write", "Edit", "NotebookEdit", "Read", "Grep", "Glob"):
            output = runhook({"tool_name": tool, "agent_id": "a1", "tool_input": {}}, self.home)
            self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny", tool)
        self.assertEqual(runhook({"tool_name": "Read", "tool_input": {"file_path": "/etc/hosts"}}, self.home), {})

    def testoutside(self) -> None:
        output = runhook({"tool_name": "Write", "tool_input": {"file_path": "/outside/x"}}, self.home)
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        inside = {"tool_name": "Write", "session_id": "s1", "tool_use_id": "t1",
                  "tool_input": {"file_path": str(REPO / "x")}}
        self.assertEqual(runhook(inside, self.home), {})
        runhook({**inside, "hook_event_name": "PostToolUse"}, self.home)

    def testhold(self) -> None:
        payload = {"tool_name": "Write", "session_id": "s1", "tool_use_id": "t1",
                   "tool_input": {"file_path": str(REPO / "x")}}
        self.assertEqual(runhook(payload, self.home), {})
        mode = Path(self.home, ".claude", "sandbox", "lock", quote(str(REPO), safe=""), "mode.main.s1")
        self.assertNotEqual(subprocess.run(["flock", "-n", "-x", str(mode), "true"]).returncode, 0)
        self.assertEqual(runhook({**payload, "hook_event_name": "PostToolUse"}, self.home), {})
        self.assertEqual(subprocess.run(["flock", "-w", "2", "-x", str(mode), "true"]).returncode, 0)

    def testwaitdeny(self) -> None:
        lock = Path(self.home, ".claude", "sandbox", "lock", quote(str(REPO), safe=""))
        lock.mkdir(parents=True)
        payload = {"tool_name": "Write", "session_id": "s1", "tool_use_id": "t1",
                   "tool_input": {"file_path": str(REPO / "x")}}
        with open(lock / "mode.sub", "w") as held, mock.patch.dict(os.environ, {"SADDLER_WAIT": "1"}):
            fcntl.flock(held, fcntl.LOCK_SH)
            output = runhook(payload, self.home)
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")


class ShellTest(unittest.TestCase):
    """sandbox.sh on invocations shaped like Claude Code's."""

    def testuntagged(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            Path(home, "seen").write_text("outside\n")
            done = runshell("cat %s/seen" % home, home)
            self.assertEqual(done.stdout, "outside\n", done.stderr)

    def teststrip(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            root = Path(home, "my proj")
            root.mkdir()
            command = "echo $LINENO 'a b'".replace("'", "'\"'\"'")
            done = runshell(WRAPPER % (quote(str(root), safe=""), "", command), home)
            self.assertEqual(done.stdout, "1 a b\n", done.stderr)

    def testconfined(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            root = Path(home, "proj")
            (root / ".claude").mkdir(parents=True)
            Path(home, "hidden").write_text("x\n")
            command = "echo made > %s/made; cat %s/hidden; echo x > %s/.claude/x" % (root, home, root)
            done = runshell(WRAPPER % (root, "", command), home)
            self.assertEqual((root / "made").read_text(), "made\n", done.stderr)
            self.assertIn("No such file", done.stderr)
            self.assertIn("Read-only", done.stderr)
            self.assertFalse((root / ".claude" / "x").exists())

    def testoverlay(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            root = Path(home, "proj")
            root.mkdir()
            (root / "file").write_text("real\n")
            upper = Path(home, ".claude", "sandbox", "overlay", "s1", "a1", "upper", "file")
            done = runshell(WRAPPER % (root, "agent=a1", "echo changed > %s/file" % root), home)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual((root / "file").read_text(), "real\n")
            self.assertEqual(upper.read_text(), "changed\n")
            read = "cat %s/file" % root
            self.assertEqual(runshell(WRAPPER % (root, "agent=a1", read), home).stdout, "changed\n")
            self.assertEqual(runshell(WRAPPER % (root, "agent=a2", read), home).stdout, "real\n")
            self.assertEqual(runshell(WRAPPER % (root, "", read), home).stdout, "real\n")
            done = runshell(WRAPPER % (root, "agent=a2", "cat %s" % upper), home)
            self.assertIn("No such file", done.stderr)

    def testqueue(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            ended, started = runpair("agent=a1", "agent=a1", home)
            self.assertGreaterEqual(started, ended)

    def testshare(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            ended, started = runpair("agent=a1", "agent=a2", home)
            self.assertLess(started, ended)

    def testexclude(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            ended, started = runpair("agent=a1", "", home)
            self.assertGreaterEqual(started, ended)
            ended, started = runpair("", "agent=a1", home)
            self.assertGreaterEqual(started, ended)

    def testmain(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            ended, started = runpair("", "", home)
            self.assertLess(started, ended)

    def testturns(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            root = Path(home, "proj")
            root.mkdir()
            with ThreadPoolExecutor(1) as pool:
                early = pool.submit(runshell, WRAPPER % (root, "", TIMED), home)
                time.sleep(0.4)
                late = runshell((WRAPPER % (root, "", TIMED)).replace("session=s1", "session=s2"), home)
            self.assertGreaterEqual(float(late.stdout.split()[0]), float(early.result().stdout.split()[1]))

    def testheld(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            root = Path(home, "proj")
            root.mkdir()
            start = time.time()
            runshell(WRAPPER % (root, "", "sleep 1 >/dev/null 2>&1 &"), home)
            done = runshell(WRAPPER % (root, "agent=a1", "date +%s.%N"), home)
            self.assertGreaterEqual(float(done.stdout), start + 0.9, done.stderr)

    def testlimit(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            root = Path(home, "proj")
            root.mkdir()
            runshell(WRAPPER % (root, "", "sleep 3 >/dev/null 2>&1 &"), home)
            done = runshell(WRAPPER % (root, "agent=a1", "echo ran"), home, wait=1)
            self.assertNotEqual(done.returncode, 0)
            self.assertEqual(done.stdout, "")
            self.assertIn("waited 1s for main.s1 commands to finish", done.stderr)


if __name__ == "__main__":
    unittest.main()
