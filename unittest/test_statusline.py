"""Correctness tests for fileguard's statusline.sh."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Final

SCRIPT: Final = Path(__file__).resolve().parent.parent / "fileguard" / "statusline.sh"
PLAIN: Final = "1.3k @ ~/my proj (main)\n"
FORKED: Final = "1.3k @ ~/my proj (session-abc/agent-master)\n"


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

    def line(self) -> str:
        """The status line for the JSON Claude Code passes."""
        payload = {"context_window": {"total_input_tokens": 1300}, "workspace": {"current_dir": str(self.root)},
                   "session_id": "abc"}
        env = {**os.environ, "HOME": str(self.home)}
        return subprocess.run(["bash", str(SCRIPT)], input=json.dumps(payload), capture_output=True, text=True,
                              check=True, env=env).stdout

    def testplain(self) -> None:
        self.assertEqual(self.line(), PLAIN)

    def testnogit(self) -> None:
        shutil.rmtree(self.root / ".git")
        self.assertEqual(self.line(), PLAIN.replace(" (main)", ""))

    def testsession(self) -> None:
        (self.home / ".claude" / "sandbox" / "project-x" / "session-abc").mkdir(parents=True)
        self.assertEqual(self.line(), FORKED)


if __name__ == "__main__":
    unittest.main()
