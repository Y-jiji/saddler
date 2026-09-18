Needs `bwrap`, `uv`, `python3`.

`edit_guard.py` — PreToolUse on Bash. Bash can write only existing gitignored paths in the project repo, `/tmp` and dot entries in `~` except `.claude`, `.bashrc`, `.profile`; everything else, including tracked files, untracked files, `.git` and the home directory, is read-only. Folders at the repo root named `#` + 3 digits, such as `./#001/`, are writable, tracked files inside included. An ignored path that does not exist yet cannot be created unless its parent is writable. A plain `git ...` command can also write the whole repo, so checkout and stash pop still work. So can a plain `mkdir ...` command, so a new `#NNN` folder can be created. Outside a git repo only `/tmp` and dot entries in `~` except `.claude`, `.bashrc`, `.profile` are writable. Refuses the command above 2900 binds.
`edit_hint.py` — PostToolUse and PostToolUseFailure on Bash. After a refused write, tells the model: Edit/Write to change a file, `git rm` to delete, `git mv` to rename.

Both ship in this skill's `scripts/`. Copy them into `<project>/.claude/hooks/` and register in `<project>/.claude/settings.json`, so the rule is committed and shared with the team.

Hook commands, matcher `Bash`:
- PreToolUse — `uv run --quiet "$CLAUDE_PROJECT_DIR/.claude/hooks/edit_guard.py" || exit 2`
- PostToolUse and PostToolUseFailure — `python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/edit_hint.py"`

`|| exit 2` denies the command if the guard is broken, instead of running it unguarded.
Check it is live: `echo x > <any tracked file>` must fail with `Read-only file system`.
