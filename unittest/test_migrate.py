"""Correctness tests for migrate.py, run on throwaway projects."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Final

REPO: Final = Path(__file__).resolve().parent.parent
FILEGUARD: Final = REPO / "fileguard"
MIGRATE: Final = FILEGUARD / "migrate.py"
HOOKS: Final = ("pretoolusewrite.py", "sessionstartsandbox.py", "subagentstop.sh")
GUARD: Final = 'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/pretoolusewrite.py" || exit 2'
STOP: Final = 'bash "$CLAUDE_PROJECT_DIR/.claude/hooks/subagentstop.sh" || exit 2'
START: Final = 'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/sessionstartsandbox.py"'
MATCHER: Final = "Agent|Bash|Monitor|Write|Edit|NotebookEdit|Read|Grep|Glob"


def entry(command: str, timeout: int, matcher: str = "") -> dict[str, object]:
    """One hook group as settings.json holds it."""
    hook = {"type": "command", "command": command, "timeout": timeout}
    return {"matcher": matcher, "hooks": [hook]} if matcher else {"hooks": [hook]}


def currenthooks() -> dict[str, object]:
    """The hook entries of an up to date project."""
    return {"SessionStart": [entry(START, 10), entry(STOP, 110)],
            "PreToolUse": [entry(GUARD, 110, MATCHER)],
            "PostToolUse": [entry(STOP, 110, "TaskStop")],
            "SubagentStop": [entry(STOP, 110)],
            "SessionEnd": [entry(STOP, 110)]}


class MigrateTest(unittest.TestCase):
    """migrate.py as a command, with a throwaway home."""

    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.home = Path(holder.name)
        self.work = self.home / "work"
        self.work.mkdir()

    def runscript(self, *words: str, root: Path | None = None) -> str:
        """The script's output for one folder."""
        done = subprocess.run(["python3", str(MIGRATE), str(root or self.work), *words], capture_output=True, text=True,
                              check=True, env={**os.environ, "HOME": str(self.home)})
        return done.stdout

    def project(self, name: str, settings: dict[str, object] | None = None) -> Path:
        """A folder holding .claude, with settings.json when given."""
        folder = self.work / name
        (folder / ".claude").mkdir(parents=True)
        if settings is not None:
            (folder / ".claude" / "settings.json").write_text(json.dumps(settings))
        return folder

    def current(self, name: str) -> Path:
        """A project with the wanted entries and hook files."""
        folder = self.project(name, {"hooks": currenthooks()})
        (folder / ".claude" / "hooks").mkdir()
        for hook in HOOKS:
            shutil.copy2(FILEGUARD / hook, folder / ".claude" / "hooks" / hook)
        return folder

    def testscan(self) -> None:
        one = self.current("one")
        deep = self.project("a/b/deep", {"hooks": {"Stop": [entry(STOP, 5)]}})
        output = self.runscript()
        self.assertNotIn(str(one), output)
        self.assertIn(str(deep), output)

    def testskip(self) -> None:
        old = {"hooks": {"Stop": [entry(STOP, 5)]}}
        for name in ("target/x", "node_modules/x", ".hidden/x"):
            self.project(name, old)
        (self.home / ".claude").mkdir()
        (self.home / ".claude" / "settings.json").write_text(json.dumps(old))
        self.assertIn("no project under", self.runscript(root=self.home))

    def testcurrent(self) -> None:
        folder = self.current("one")
        path = folder / ".claude" / "settings.json"
        text = json.dumps({"hooks": currenthooks()}, indent=7)
        path.write_text(text)
        self.assertIn("no project under", self.runscript("--apply"))
        self.assertEqual(path.read_text(), text)

    def testhookbytes(self) -> None:
        folder = self.current("one")
        path = folder / ".claude" / "settings.json"
        text = path.read_text()
        (folder / ".claude" / "hooks" / "subagentstop.sh").write_text("stale\n")
        self.runscript("--apply")
        self.assertEqual((folder / ".claude" / "hooks" / "subagentstop.sh").read_bytes(),
                         (FILEGUARD / "subagentstop.sh").read_bytes())
        self.assertEqual(path.read_text(), text)

    def testentries(self) -> None:
        hooks = currenthooks()
        hooks["SessionEnd"] = [entry(STOP, 5)]
        hooks["PreToolUse"] = [entry(GUARD, 110, "Bash")]
        hooks["Stop"] = [entry("echo mine", 3)]
        folder = self.current("one")
        (folder / ".claude" / "settings.json").write_text(json.dumps({"hooks": hooks}))
        self.runscript("--apply")
        wanted = {**currenthooks(), "Stop": [entry("echo mine", 3)]}
        self.assertEqual(json.loads((folder / ".claude" / "settings.json").read_text())["hooks"], wanted)

    def testlocal(self) -> None:
        folder = self.current("one")
        local = folder / ".claude" / "settings.local.json"
        local.write_text(json.dumps({"permissions": {"allow": ["Bash(ls)"]},
                                     "hooks": {"Stop": [entry("python3 .claude/hooks/write_guard.py", 5)]}}))
        self.runscript("--apply")
        self.assertEqual(json.loads(local.read_text()), {"permissions": {"allow": ["Bash(ls)"]}})

    def testoldhooks(self) -> None:
        folder = self.project("one", {"hooks": {"PreToolUse": [entry("python3 .claude/hooks/edit_guard.py", 5)]}})
        (folder / ".claude" / "hooks").mkdir()
        (folder / ".claude" / "hooks" / "edit_guard.py").write_text("old\n")
        self.runscript("--apply")
        self.assertFalse((folder / ".claude" / "hooks" / "edit_guard.py").exists())
        self.assertEqual(json.loads((folder / ".claude" / "settings.json").read_text())["hooks"], currenthooks())
        for hook in HOOKS:
            self.assertTrue((folder / ".claude" / "hooks" / hook).is_file())

    def testunused(self) -> None:
        folder = self.project("one", {"hooks": {"Stop": [entry("echo mine", 3)]}})
        text = (folder / ".claude" / "settings.json").read_text()
        self.assertIn("no project under", self.runscript("--apply"))
        self.assertEqual((folder / ".claude" / "settings.json").read_text(), text)
        self.assertFalse((folder / ".claude" / "hooks").exists())

    def testowncopy(self) -> None:
        folder = self.project("clone", {"hooks": {"SessionEnd": [entry("bash fileguard/subagentstop.sh", 110)]}})
        text = (folder / ".claude" / "settings.json").read_text()
        (folder / "fileguard").mkdir()
        (folder / "fileguard" / "migrate.py").write_text("older\n")
        output = self.runscript("--apply")
        self.assertIn("pull it", output)
        self.assertEqual((folder / "fileguard" / "migrate.py").read_text(), "older\n")
        self.assertEqual((folder / ".claude" / "settings.json").read_text(), text)

    def testinstalled(self) -> None:
        saddler = self.home / ".claude" / "saddler"
        saddler.mkdir(parents=True)
        (saddler / "sandbox.sh").write_text("older\n")
        output = self.runscript("--apply")
        self.assertIn("sandbox.sh differs", output)
        self.assertEqual((saddler / "sandbox.sh").read_text(), "older\n")

    def testunreadable(self) -> None:
        folder = self.project("one")
        (folder / ".claude" / "settings.json").write_text("{not json")
        self.assertIn("cannot read", self.runscript("--apply"))
        self.assertEqual((folder / ".claude" / "settings.json").read_text(), "{not json")

    def testdryrun(self) -> None:
        folder = self.current("one")
        (folder / ".claude" / "hooks" / "subagentstop.sh").write_text("stale\n")
        output = self.runscript()
        self.assertIn("copy subagentstop.sh", output)
        self.assertIn("dry run", output)
        self.assertEqual((folder / ".claude" / "hooks" / "subagentstop.sh").read_text(), "stale\n")


if __name__ == "__main__":
    unittest.main()
