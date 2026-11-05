"""Correctness tests for install.sh, with a throwaway home."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Final

INSTALL: Final = Path(__file__).resolve().parent.parent / "install.sh"
BEGIN: Final = "#>>>>>>>>>>>>>># saddler"


class InstallTest(unittest.TestCase):
    """install.sh run as a person would, outside the sandbox."""

    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.home = Path(holder.name)
        self.bashrc = self.home / ".bashrc"

    def install(self) -> None:
        """Run install.sh, declining to overwrite skills it installed before."""
        subprocess.run(["bash", str(INSTALL)], input="n\n" * 20, capture_output=True, text=True, check=True,
                       env={**os.environ, "HOME": str(self.home), "CLAUDE_SKILLS_DIR": str(self.home / "skills")})

    def testbashrc(self) -> None:
        self.bashrc.write_text("before\n")
        self.install()
        with self.bashrc.open("a") as f:
            f.write("after\n")
        self.install()
        text = self.bashrc.read_text()
        self.assertEqual(text.count(BEGIN), 1)
        self.assertIn("before\n", text)
        self.assertIn("after\n", text)
        self.assertIn('forkshell() { "$HOME/.claude/saddler/forkshell.sh" "$@"; }', text)

    def testsymlink(self) -> None:
        target = self.home / "dotfiles" / "bashrc"
        target.parent.mkdir()
        target.write_text("mine\n")
        self.bashrc.symlink_to(target)
        self.install()
        self.assertTrue(self.bashrc.is_symlink())
        self.assertIn("mine\n", target.read_text())
        self.assertIn(BEGIN, target.read_text())


if __name__ == "__main__":
    unittest.main()
