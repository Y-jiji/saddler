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

    def install(self, *names: str) -> None:
        """Run install.sh on the named skills, or all, declining to overwrite skills it installed before."""
        subprocess.run(["bash", str(INSTALL), *names], input="n\n" * 20, capture_output=True, text=True, check=True,
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

    def testwhitelist(self) -> None:
        box = self.home / ".claude" / "sandbox"
        box.mkdir(parents=True)
        (box / "whitelist.txt").write_text("ro /mine\n")
        self.install("fileguard")
        repo = (INSTALL.parent / "fileguard" / "whitelist.txt").read_text()
        self.assertEqual((box / "whitelist.txt").read_text(), repo)
        self.assertEqual((box / "whitelist.txt.old").read_text(), "ro /mine\n")
        (box / "whitelist.txt.old").unlink()
        self.install("fileguard")
        self.assertFalse((box / "whitelist.txt.old").exists())

    def testnamed(self) -> None:
        skills = self.home / "skills"
        self.install("tokenline")
        self.assertEqual([path.name for path in skills.iterdir()], ["tokenline"])
        self.assertFalse((self.home / ".claude" / "saddler").exists())
        self.assertFalse(self.bashrc.exists())
        (skills / "tokenline" / "SKILL.md").write_text("old\n")
        self.install("tokenline")
        self.assertNotEqual((skills / "tokenline" / "SKILL.md").read_text(), "old\n")
        self.install("fileguard")
        self.assertTrue((self.home / ".claude" / "saddler" / "sandbox.sh").exists())
        self.assertIn(BEGIN, self.bashrc.read_text())

    def testunknown(self) -> None:
        with self.assertRaises(subprocess.CalledProcessError):
            self.install("tokenline", "nosuch")
        self.assertFalse((self.home / "skills").exists())
        self.assertFalse(self.bashrc.exists())


if __name__ == "__main__":
    unittest.main()
