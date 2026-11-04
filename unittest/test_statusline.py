"""Correctness tests for tokenline's statusline.sh."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Final
from urllib.parse import quote

SCRIPT: Final = Path(__file__).resolve().parent.parent / "tokenline" / "statusline.sh"
PLAIN: Final = "1.3k @ ~/my proj (main)\n"


@unittest.skipUnless(shutil.which("jq"), "jq is not installed")
class StatusTest(unittest.TestCase):
    """statusline.sh on the JSON Claude Code passes, with a throwaway home."""

    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.home = Path(holder.name).resolve()
        self.root = self.home / "my proj"
        self.root.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.root)], check=True)
        self.lock = self.home / ".claude" / "sandbox" / ("project-" + quote(str(self.root), safe="")) / "lock"
        self.lock.mkdir(parents=True)

    def line(self, session: str = "s-1", variable: str = "") -> str:
        """The status line for one session, from the JSON or from the environment."""
        payload = {"context_window": {"total_input_tokens": 1300}, "workspace": {"current_dir": str(self.root)}}
        if session:
            payload["session_id"] = session
        env = {**os.environ, "HOME": str(self.home), "CLAUDE_CODE_SESSION_ID": variable}
        return subprocess.run(["bash", str(SCRIPT)], input=json.dumps(payload), capture_output=True, text=True,
                              check=True, env=env).stdout

    def testowner(self) -> None:
        (self.lock / "owner.info").write_text("123 s-1\n")
        self.assertEqual(self.line(), PLAIN[:-1] + " [owner]\n")
        self.assertEqual(self.line("s-2"), PLAIN)

    def testfork(self) -> None:
        (self.lock / "owner.info").write_text("123 s-1\n")
        (self.lock / "s-2-master").write_text("- base branch 456\n")
        self.assertEqual(self.line("s-2"), PLAIN[:-1] + " [fork]\n")

    def testunclaimed(self) -> None:
        self.assertEqual(self.line(), PLAIN)

    def testnolock(self) -> None:
        shutil.rmtree(self.home / ".claude")
        self.assertEqual(self.line(), PLAIN)

    def testnosession(self) -> None:
        (self.lock / "owner.info").write_text("123 s-1\n")
        self.assertEqual(self.line(session=""), PLAIN)
        self.assertEqual(self.line(session="", variable="s-1"), PLAIN[:-1] + " [owner]\n")


if __name__ == "__main__":
    unittest.main()
