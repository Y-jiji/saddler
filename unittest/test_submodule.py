"""Correctness tests for submodules in agents' views, through sandbox.sh."""

import subprocess
import unittest
from pathlib import Path

from test_checkpoint import CheckpointCase
from test_fileguard import git

FILES: tuple[str, ...] = ("-c", "protocol.file.allow=always")


class SubmoduleTest(CheckpointCase):
    """A project with submodule sub, from repository lib."""

    def setUp(self) -> None:
        super().setUp()
        self.lib = self.repo("lib", "l.txt")
        git(self.root, *FILES, "submodule", "add", "-q", str(self.lib), "sub")
        self.identify(self.root / "sub")
        git(self.root, "commit", "-qm", "add sub")
        self.start = git(self.root, "rev-parse", "main")

    def repo(self, name: str, file: str) -> Path:
        """A repository with one commit of one file, where views can clone it from."""
        folder = self.home / "tmp" / name
        folder.mkdir()
        git(folder, "init", "-q", "-b", "main")
        git(folder, "config", "user.name", "t")
        git(folder, "config", "user.email", "t@t")
        (folder / file).write_text(name + "\n")
        git(folder, "add", "-A")
        git(folder, "commit", "-qm", name)
        return folder

    def identify(self, worktree: Path) -> None:
        """Give a real submodule a committer, which a test machine without a global one lacks."""
        git(worktree, "config", "user.name", "t")
        git(worktree, "config", "user.email", "t@t")

    def pointer(self, commit: str, path: str, root: Path | None = None) -> str:
        """The commit a submodule pointer in a commit names."""
        return git(root or self.root, "ls-tree", commit, path).split()[2]

    def teststatus(self) -> None:
        done = self.agent("git status --short && echo clean; cd sub && git status --short && git log -1 --format=%s")
        self.assertEqual(done.stdout, "clean\nlib\n", done.stderr)

    def testcommit(self) -> None:
        done = self.agent("cd sub && echo more >> l.txt && git commit -qam subwork && cd .. && git add sub && git commit -qm bump")
        module = git(self.root / "sub", "rev-parse", "session-s-1/agent-a1")
        self.assertEqual(git(self.root / "sub", "log", "-1", "--format=%s", module), "subwork", done.stderr)
        self.assertEqual(self.pointer("session-s-1/agent-a1", "sub"), module)
        self.assertEqual((self.root / "sub" / "l.txt").read_text(), "lib\n")

    def testmissing(self) -> None:
        done = self.agent("cd sub && git checkout -qb other && echo x >> l.txt && git commit -qam other && cd .. &&"
                          " git add sub && git commit -qm bump")
        self.assertIn("lacks", done.stderr)
        self.assertEqual(git(self.root, "rev-parse", "session-s-1/agent-a1"), self.start)

    def testcheckpoint(self) -> None:
        done = self.agent("cd sub && echo more >> l.txt && git commit -qam subwork && cd .. && git add sub &&"
                          " git commit -qm bump && git checkpoint")
        self.assertIn("every agent's base", done.stderr)
        self.assertEqual((self.root / "sub" / "l.txt").read_text(), "lib\nmore\n")
        self.assertEqual(git(self.root / "sub", "rev-parse", "HEAD"), self.pointer("main", "sub"))
        self.assertNotEqual(subprocess.run(["git", "-C", str(self.root / "sub"), "symbolic-ref", "-q", "HEAD"]).returncode, 0)
        self.assertEqual(git(self.root, "status", "--porcelain"), "")

    def testadd(self) -> None:
        two = self.repo("two", "m.txt")
        done = self.agent("git %s submodule add -q %s sub2 && git commit -qm add2 && git checkpoint" % (" ".join(FILES), two))
        self.assertIn("every agent's base", done.stderr)
        self.assertTrue((self.root / ".git" / "modules" / "sub2").is_dir())
        self.assertEqual((self.root / "sub2" / "m.txt").read_text(), "two\n")
        self.assertEqual(git(self.root / "sub2", "rev-parse", "HEAD"), self.pointer("main", "sub2"))
        self.assertEqual(git(self.root, "status", "--porcelain"), "")

    def testnested(self) -> None:
        deep = self.repo("deep", "d.txt")
        three = self.repo("three", "k.txt")
        git(three, *FILES, "submodule", "add", "-q", str(deep), "deep")
        git(three, "commit", "-qm", "deep")
        git(self.root, *FILES, "submodule", "add", "-q", str(three), "sub3")
        git(self.root, *FILES, "submodule", "update", "--init", "--recursive", "-q")
        self.identify(self.root / "sub3")
        self.identify(self.root / "sub3" / "deep")
        git(self.root, "commit", "-qm", "sub3")
        done = self.agent("cd sub3/deep && echo more >> d.txt && git commit -qam deepwork && cd .. && git add deep &&"
                          " git commit -qm bumpdeep && cd .. && git add sub3 && git commit -qm bump3 && git checkpoint")
        self.assertIn("every agent's base", done.stderr)
        self.assertEqual((self.root / "sub3" / "deep" / "d.txt").read_text(), "deep\nmore\n")
        self.assertEqual(git(self.root / "sub3" / "deep", "rev-parse", "HEAD"),
                         self.pointer("HEAD", "deep", self.root / "sub3"))
        self.assertEqual(git(self.root, "status", "--porcelain"), "")

    def testembedded(self) -> None:
        vendor = self.root / "vendor"
        vendor.mkdir()
        git(vendor, "init", "-q", "-b", "main")
        git(vendor, "config", "user.name", "t")
        git(vendor, "config", "user.email", "t@t")
        (vendor / "v.txt").write_text("vendor\n")
        git(vendor, "add", "-A")
        git(vendor, "commit", "-qm", "vendor")
        (self.root / ".gitignore").write_text("target/\nvendor/\n")
        git(self.root, "commit", "-qam", "ignore vendor")
        done = self.agent("echo x > vendor/.git/hooks/post-commit || echo refused; git -C vendor log -1 --format=%s;"
                          " echo n > n.txt && git add n.txt && git commit -qm n && git checkpoint")
        self.assertEqual(done.stdout, "refused\nvendor\n", done.stderr)
        self.assertIn("every agent's base", done.stderr)
        self.assertFalse((vendor / ".git" / "hooks" / "post-commit").exists())


if __name__ == "__main__":
    unittest.main()
