# Hooks

Needs `bwrap`, `uv`, `python3`.

`edit_guard.py` — PreToolUse on Bash. Bash cannot modify or delete a git-tracked file, submodules included at any depth. Creating files and writing untracked or gitignored paths still works, so builds and installs are unaffected. A plain `git ...` command is exempt, so checkout and stash pop still work. No effect outside a git repo, or outside the project dir. Refuses the command above 2900 tracked files.
`edit_hint.py` — PostToolUse and PostToolUseFailure on Bash. After a refused write, tells the model: Edit/Write to change a file, `git rm` to delete, `git mv` to rename.

Place both in `<project>/.claude/hooks/` and register in `<project>/.claude/settings.json`, so the rule is committed and shared with the team.

Hook commands, matcher `Bash`:
- PreToolUse — `uv run --quiet "$CLAUDE_PROJECT_DIR/.claude/hooks/edit_guard.py" || exit 2`
- PostToolUse and PostToolUseFailure — `python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/edit_hint.py"`

`|| exit 2` denies the command if the guard is broken, instead of running it unguarded.
Check it is live: `echo x > <any tracked file>` must fail with `Read-only file system`.
