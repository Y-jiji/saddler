"""Correctness tests for the fileguard hooks and sandbox.sh."""

import json
import os
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from typing import Final
from urllib.parse import quote

REPO: Final = Path(__file__).resolve().parent.parent
FILEGUARD: Final = REPO / "fileguard"
HOOK: Final = FILEGUARD / "pretoolusewrite.py"
SCRIPTS: Final = ("sandbox.sh", "allowlist.sh", "gitlock.sh", "gitwrap.sh", "overlayfork.sh", "subagentstop.sh")
WRAPPER: Final = "source /dev/null 2>/dev/null || true && eval '%s' < /dev/null"
WHITELIST: Final = "ro /usr\nro /etc\nprivate ~/.ssh ~/.claude/sandbox/ssh\n"


def git(root: Path, *words: str) -> str:
    """Run git in a project and return its output."""
    return subprocess.run(["git", "-C", str(root), *words], capture_output=True, text=True, check=True).stdout.strip()


class SandboxCase(unittest.TestCase):
    """A throwaway home with the scripts installed, and a project with one session folder."""

    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.home = Path(holder.name)
        self.saddler = self.home / ".claude" / "saddler"
        self.saddler.mkdir(parents=True)
        for name in SCRIPTS:
            shutil.copy2(FILEGUARD / name, self.saddler / name)
            (self.saddler / name).chmod(0o755)
        self.box = self.home / ".claude" / "sandbox"
        self.box.mkdir()
        (self.box / "whitelist.txt").write_text(WHITELIST)
        (self.home / "tmp").mkdir()
        (self.home / "hidden").write_text("hidden\n")
        (self.home / ".ssh").mkdir()
        (self.home / ".ssh" / "config").write_text("real\n")
        self.root = self.home / "my proj"
        self.root.mkdir()
        git(self.root, "init", "-q")
        git(self.root, "config", "user.name", "t")
        git(self.root, "config", "user.email", "t@t")
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "settings.json").write_text("{}\n")
        (self.root / ".gitignore").write_text("target/\n")
        (self.root / "a.txt").write_text("one\n")
        (self.root / "del.txt").write_text("gone\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "old")
        (self.root / "a.txt").write_text("two\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "base")
        self.base = git(self.root, "rev-parse", "HEAD")
        (self.root / "target").mkdir()
        (self.root / "target" / "art").write_text("art\n")
        self.state = self.box / ("project-" + quote(str(self.root), safe=""))
        self.lock = self.state / "lock"
        self.claudes: list[subprocess.Popen[bytes]] = []
        self.first = self.newclaude()
        self.session("s-1")
        self.addCleanup(self.stopall)

    def newclaude(self) -> subprocess.Popen[bytes]:
        """A process standing in for one running Claude Code."""
        claude = subprocess.Popen(["sleep", "300"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        self.claudes.append(claude)
        return claude

    def session(self, name: str) -> Path:
        """The folder the session hook makes."""
        folder = self.state / ("session-" + name)
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def environ(self, session: str, claude: subprocess.Popen[bytes]) -> dict[str, str]:
        """The environment Claude Code would give a shell."""
        return {**os.environ, "HOME": str(self.home), "TMPDIR": str(self.home / "tmp"),
                "CLAUDE_CODE_SESSION_ID": session, "CLAUDE_PID": str(claude.pid),
                "CLAUDE_PROJECT_DIR": str(self.root),
                "CLAUDE_CODE_SHELL_PREFIX": str(self.saddler / "sandbox.sh")}

    def shell(self, command: str, session: str = "s-1", claude: subprocess.Popen[bytes] | None = None,
              cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        """Run a command as a Claude Code tool call would."""
        invocation = WRAPPER % command.replace("'", "'\\''")
        return subprocess.run([str(self.saddler / "sandbox.sh"), invocation], capture_output=True, text=True,
                              env=self.environ(session, claude or self.first), cwd=cwd or self.root, timeout=60)

    def event(self, payload: dict[str, object], session: str = "s-1",
              claude: subprocess.Popen[bytes] | None = None) -> subprocess.CompletedProcess[str]:
        """Run subagentstop.sh in a hook shell, confined as Claude Code would."""
        return subprocess.run([str(self.saddler / "sandbox.sh"), "bash %s" % (self.saddler / "subagentstop.sh")],
                              input=json.dumps(payload), capture_output=True, text=True,
                              env=self.environ(session, claude or self.first), cwd=self.root, timeout=60)

    def holder(self, session: str, agent: str) -> int:
        """The holder PID in a fork's lock file."""
        return int((self.lock / ("%s-%s" % (session, agent))).read_text().split()[0])

    def stopall(self) -> None:
        """End every stand-in Claude and every holder."""
        for claude in self.claudes:
            claude.kill()
            claude.wait()
        for path in self.lock.glob("*-*"):
            word = path.read_text().split()[0]
            if word.isdigit():
                try:
                    os.kill(int(word), signal.SIGKILL)
                except OSError:
                    pass
        time.sleep(0.05)


class HookTest(SandboxCase):
    """pretoolusewrite.py and sessionstartsandbox.py on hook payloads."""

    def runhook(self, payload: dict[str, object], claude: subprocess.Popen[bytes] | None = None) -> dict[str, object]:
        """The hook's parsed output, empty when it prints nothing."""
        done = subprocess.run(["python3", str(HOOK)], input=json.dumps({"session_id": "s-1", **payload}),
                              capture_output=True, text=True, check=True,
                              env=self.environ("s-1", claude or self.first))
        return json.loads(done.stdout) if done.stdout else {}

    def testbash(self) -> None:
        self.assertEqual(self.runhook({"tool_name": "Bash", "tool_input": {"command": "ls"}}), {})

    def testmonitor(self) -> None:
        output = self.runhook({"tool_name": "Monitor", "tool_input": {"command": "ls"}})
        self.assertEqual(output["hookSpecificOutput"]["updatedInput"]["command"], "# saddler nolock\nls")

    def testagent(self) -> None:
        output = self.runhook({"tool_name": "Bash", "agent_id": "a1", "tool_input": {"command": "ls"}})
        self.assertEqual(output["hookSpecificOutput"]["updatedInput"]["command"], "# saddler agent=a1\nls")

    def testinput(self) -> None:
        tooluse = {"command": "echo 'a'\necho b", "description": "d", "timeout": 5, "run_in_background": True}
        output = self.runhook({"tool_name": "Bash", "agent_id": "a1", "tool_input": tooluse})
        updated = output["hookSpecificOutput"]["updatedInput"]
        self.assertEqual(updated["command"].split("\n", 1)[1], tooluse["command"])
        self.assertEqual({**updated, "command": tooluse["command"]}, tooluse)

    def testnolock(self) -> None:
        output = self.runhook({"tool_name": "Bash", "tool_input": {"command": "ls", "run_in_background": True}})
        self.assertEqual(output["hookSpecificOutput"]["updatedInput"]["command"], "# saddler nolock\nls")
        output = self.runhook({"tool_name": "Monitor", "agent_id": "a1", "tool_input": {"command": "ls"}})
        self.assertEqual(output["hookSpecificOutput"]["updatedInput"]["command"], "# saddler agent=a1 nolock\nls")

    def testfiledeny(self) -> None:
        for tool in ("Write", "Edit", "NotebookEdit", "Read", "Grep", "Glob"):
            output = self.runhook({"tool_name": tool, "agent_id": "a1", "tool_input": {}})
            self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny", tool)

    def testoutside(self) -> None:
        output = self.runhook({"tool_name": "Write", "tool_input": {"file_path": "/outside/x"}})
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(self.runhook({"tool_name": "Write", "tool_input": {"file_path": str(self.root / "x")}}), {})

    def testrecord(self) -> None:
        self.runhook({"session_id": "s-9", "tool_name": "Read", "tool_input": {}})
        self.assertTrue((self.state / "session-s-9").is_dir())
        subprocess.run(["python3", str(FILEGUARD / "sessionstartsandbox.py")], check=True, text=True,
                       input=json.dumps({"session_id": "s-8"}), env=self.environ("s-8", self.first))
        self.assertTrue((self.state / "session-s-8").is_dir())

    def testclaim(self) -> None:
        self.runhook({"tool_name": "Read", "tool_input": {"file_path": str(self.root / "a.txt")}})
        self.assertFalse((self.lock / "owner.info").exists())
        write = {"tool_name": "Write", "tool_input": {"file_path": str(self.root / "x")}}
        self.assertEqual(self.runhook(write), {})
        self.assertEqual((self.lock / "owner.info").read_text().split()[1], "s-1")
        self.assertEqual(self.runhook(write), {})
        output = self.runhook({**write, "session_id": "s-2"}, self.newclaude())
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("s-1", output["hookSpecificOutput"]["permissionDecisionReason"])

    def testforkdeny(self) -> None:
        self.lock.mkdir(parents=True, exist_ok=True)
        (self.lock / "s-1-master").write_text("- x y 1\n")
        for tool in ("Write", "Read", "Grep", "Glob", "Agent"):
            output = self.runhook({"tool_name": tool, "tool_input": {}})
            self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny", tool)
        self.assertEqual(self.runhook({"tool_name": "Bash", "tool_input": {"command": "ls"}}), {})

    def testspawn(self) -> None:
        spawn = {"tool_name": "Agent", "tool_input": {}}
        self.assertEqual(self.runhook(spawn), {})
        self.assertFalse((self.lock / "owner.info").exists())
        self.runhook({"tool_name": "Write", "tool_input": {"file_path": str(self.root / "x")}})
        output = self.runhook({**spawn, "session_id": "s-2"}, self.newclaude())
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        git(self.root, "checkout", "-q", "--orphan", "empty")
        output = self.runhook(spawn)
        self.assertIn("not a git repository", output["hookSpecificOutput"]["permissionDecisionReason"])


class ShellTest(SandboxCase):
    """sandbox.sh on invocations shaped like Claude Code's."""

    def testnorecord(self) -> None:
        done = subprocess.run([str(self.saddler / "sandbox.sh"), "cat %s/hidden" % self.home], capture_output=True,
                              text=True, env=self.environ("none", self.first))
        self.assertEqual(done.stdout, "hidden\n", done.stderr)

    def teststrip(self) -> None:
        done = self.shell("# saddler agent=a1\necho $LINENO 'a b'")
        self.assertEqual(done.stdout, "1 a b\n", done.stderr)

    def testconfined(self) -> None:
        done = self.shell("echo made > made; cat '%s/hidden'; cat target/art" % self.home)
        self.assertEqual((self.root / "made").read_text(), "made\n", done.stderr)
        self.assertIn("No such file", done.stderr)
        self.assertEqual(done.stdout, "art\n")

    def testoverlay(self) -> None:
        done = self.shell("# saddler agent=a1\necho changed > a.txt; cat target/art")
        self.assertIn("No such file", done.stderr)
        self.assertEqual((self.root / "a.txt").read_text(), "two\n")
        self.assertEqual(self.shell("# saddler agent=a1\ncat a.txt").stdout, "changed\n")
        self.assertEqual(self.shell("# saddler agent=a2\ncat a.txt").stdout, "two\n")
        self.assertEqual(self.shell("cat a.txt").stdout, "two\n")

    def testlayout(self) -> None:
        self.shell("# saddler agent=a1\ntrue")
        fork = self.state / "session-s-1"
        self.assertEqual({p.name for p in (fork / "agent-a1").iterdir()}, {"fork", "work"})
        self.assertEqual({p.name for p in (fork / ("commit-" + self.base)).iterdir()}, {"HEAD", "index", "tree"})
        self.assertEqual({p.name for p in self.state.iterdir()}, {"lock", "session-s-1"})
        words = (self.lock / "s-1-a1").read_text().split()
        self.assertEqual(words[1:3], [self.base, "saddler/s-1/a1"])
        self.assertEqual(git(self.root, "rev-parse", "saddler/s-1/a1"), self.base)

    def testotherfork(self) -> None:
        self.assertEqual(self.shell("echo mine > a.txt").returncode, 0)
        self.session("s-2")
        second = self.newclaude()
        done = self.shell("cat a.txt; echo theirs > a.txt", "s-2", second)
        self.assertEqual(done.stdout, "two\n", done.stderr)
        self.assertEqual((self.root / "a.txt").read_text(), "mine\n")
        self.assertEqual(git(self.root, "show", "saddler/s-2/master:a.txt"), "theirs")
        self.assertTrue((self.state / "session-s-2" / "agent-master" / "fork").is_dir())

    def testforkstays(self) -> None:
        self.shell("true")
        self.session("s-2")
        second = self.newclaude()
        self.shell("true", "s-2", second)
        self.first.kill()
        self.first.wait()
        time.sleep(1.3)
        self.shell("echo still > f.txt", "s-2", second)
        self.assertFalse((self.root / "f.txt").exists())

    def testnewowner(self) -> None:
        self.shell("true")
        self.first.kill()
        self.first.wait()
        time.sleep(1.3)
        self.session("s-2")
        self.shell("echo real > f.txt", "s-2", self.newclaude())
        self.assertEqual((self.root / "f.txt").read_text(), "real\n")
        self.assertEqual((self.lock / "owner.info").read_text().split()[1], "s-2")

    def testownerguard(self) -> None:
        for path in (".claude/settings.json", ".git/config", ".git/hooks/evil"):
            done = self.shell("echo x >> %s" % path)
            self.assertIn("Read-only", done.stderr, path)
        hook = self.root / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\ngit rev-parse HEAD >/dev/null\n")
        hook.chmod(0o755)
        done = self.shell("git add a.txt; echo three > a.txt; git add a.txt; git commit -qm mine; echo rc=$?; git rev-parse -q --verify nope; echo rc=$?")
        self.assertEqual(done.stdout.split(), ["rc=0", "rc=1"], done.stderr)
        self.assertEqual(git(self.root, "log", "-1", "--format=%s"), "mine")

    def testnolockcall(self) -> None:
        self.shell("true")
        start = time.monotonic()
        late = subprocess.Popen([str(self.saddler / "sandbox.sh"), WRAPPER % "# saddler agent=a1 nolock\nsleep 2"],
                                env=self.environ("s-1", self.first), cwd=self.root,
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        self.addCleanup(late.wait)
        time.sleep(0.5)
        self.shell("git status --short")
        self.assertLess(time.monotonic() - start, 1.8)

    def testhookshell(self) -> None:
        done = subprocess.run([str(self.saddler / "sandbox.sh"), "cat '%s/hidden'; echo x > .claude/y; touch '%s/ok'" % (self.home, self.lock)],
                              capture_output=True, text=True, env=self.environ("s-1", self.first), cwd=self.root)
        self.assertIn("No such file", done.stderr)
        self.assertIn("Read-only", done.stderr)
        self.assertTrue((self.lock / "ok").exists())
        self.assertFalse((self.lock / "owner.info").exists())

    def testnested(self) -> None:
        inner = shlex.quote(WRAPPER % "git rev-parse HEAD")
        done = self.shell('H="$TMPDIR/inner"; mkdir -p "$H"; cp -r ~/.claude "$H/"; HOME="$H" "$H/.claude/saddler/sandbox.sh" %s' % inner)
        self.assertEqual(done.stdout.strip(), self.base, done.stderr)


if __name__ == "__main__":
    unittest.main()
