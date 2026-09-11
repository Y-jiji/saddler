Commit message: `feature/refactor/chore/test/fix`, top-level crate/module/file path in parentheses, e.g. `feature(some_crate): ...`, only one line
Just push: code only goes into git push, never copy code files directly unless you are sure that the script can only ever exists on the server and never enter github
Commit as you go: end each turn with a commit whenever there is code change
Be plain: `git ...` instead of `git ... && something else && ... git ...`; otherwise it gets rejected
No worktree: do not create worktrees, user usually don't ask for overlapping changes; if there are, communicate with other agent sessions
