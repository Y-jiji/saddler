# Hooks

Two hooks. Both need `bwrap`, `uv` and `python3` on the machine.

## Effect

`edit_guard.py` — PreToolUse on Bash

Bash cannot modify or delete a git-tracked file. Covers the whole worktree of
the project the session started in, and submodules at any depth.
Bash can still create new files and directories, and write anything untracked
or gitignored, so builds, installs and generated output keep working.
A plain `git ...` command runs untouched, so `checkout`, `restore`,
`stash pop`, `merge` and `rebase` still work. Git mixed into a longer command
line is not plain and is not exempt.
No effect outside a git repository. No effect outside the project directory.
A command is refused outright if the project has more than 2900 tracked files.

`edit_hint.py` — PostToolUse and PostToolUseFailure on Bash

After a refused write, tells the model to use Edit/Write to change a file,
`git rm` to delete one, `git mv` to rename one.

## Place

Per project, so the rule travels with the repo:

```
<project>/hooks/edit_guard.py
<project>/hooks/edit_hint.py
<project>/.claude/settings.json
```

Every project, one copy:

```
~/.claude/hooks/edit_guard.py
~/.claude/hooks/edit_hint.py
~/.claude/settings.json
```

## Setup

Add to the `hooks` key of the chosen `settings.json`. Per project, use
`$CLAUDE_PROJECT_DIR` as written; for every project, replace it with
`$HOME/.claude`.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "uv run --quiet \"$CLAUDE_PROJECT_DIR/hooks/edit_guard.py\" || exit 2",
            "timeout": 20
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR/hooks/edit_hint.py\"",
            "timeout": 10
          }
        ]
      }
    ],
    "PostToolUseFailure": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR/hooks/edit_hint.py\"",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

`|| exit 2` on the guard makes a broken hook deny the command instead of
letting it run unguarded.

Check it is live: `echo x > <any tracked file>` must fail with
`Read-only file system`.
