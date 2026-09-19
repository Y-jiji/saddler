Needs `bwrap`, `uv`, `python3`.

`edit_guard.py` — PreToolUse on Bash. Bash can write the project repo except every `.git` and `.claude` in it, nested ones included, `/tmp` and dot entries in `~` except `.claude`, `.claude.json`, `.gitconfig`, `.ssh`, `.config`, `.bashrc`, `.bash_profile`, `.bash_logout`, `.bash_modules`, `.profile`, `.zshrc`; everything else, including the home directory, is read-only. A `.git` or `.claude` that does not exist yet can be created. A plain `git ...` command runs unguarded, so checkout and stash pop still work. Outside a git repo only `/tmp` and those dot entries in `~` are writable.
`edit_hint.py` — PostToolUse and PostToolUseFailure on Bash. After a refused write, tells the model: Edit/Write to change a file in the project, a plain `git ...` command to change `.git`.
`write_guard.py` — PreToolUse on Write, Edit and NotebookEdit. Denies a path whose real path is outside the project repo, or outside the project directory when it is not in a repo.

All three ship in this skill's `scripts/`. Copy them into `<project>/.claude/hooks/` and register in `<project>/.claude/settings.json`, so the rule is committed and shared with the team.

Hook commands:
- PreToolUse, matcher `Bash` — `uv run --quiet "$CLAUDE_PROJECT_DIR/.claude/hooks/edit_guard.py" || exit 2`
- PreToolUse, matcher `Write|Edit|NotebookEdit` — `python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/write_guard.py" || exit 2`
- PostToolUse and PostToolUseFailure, matcher `Bash` — `python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/edit_hint.py"`

`|| exit 2` denies the call if the guard is broken, instead of running it unguarded.
Check it is live: `echo x > .git/x` must fail with `Read-only file system`, and Write to a file outside the project must be denied.
