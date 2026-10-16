---
name: fileguard
description: sandbox Bash and guard Write, Edit and NotebookEdit for this project
disable-model-invocation: true
---

Do these in order:
1. Check `bwrap` and `python3` are on `PATH`; if either is missing, stop and tell the user.
2. From this skill's directory, copy `sandbox.sh` to `~/.claude/sandbox.sh`, and `sandbox.allow` to `~/.claude/sandbox/allow` unless that file already exists.
3. Add `"env": {"CLAUDE_CODE_SHELL_PREFIX": "<absolute path of ~/.claude/sandbox.sh>"}` to `~/.claude/settings.json`.
4. From this skill's directory, copy `sessionstartsandbox.py` and `pretoolusewrite.py` into `<project>/.claude/hooks/`.
5. Register in `<project>/.claude/settings.json`:
   - SessionStart — `python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/sessionstartsandbox.py"`
   - PreToolUse, matcher `Write|Edit|NotebookEdit` — `python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/pretoolusewrite.py" || exit 2`
6. Tell the user to restart claude, then check in the new session: `echo x > .git/config` fails with `Read-only file system`, `ls /run` fails, and Write to a file outside the project is denied.

Why:
- `sandbox.sh` runs every shell Claude Code starts. In a session with a record, the shell runs in bwrap on an empty root holding only the host `/dev`, a fresh `/proc`, every library and `PATH` directory read-only, the entries of `~/.claude/sandbox/allow`, and the project writable except `config` and `hooks` under every `.git`, every `.git` that is a file and every `.claude`. `~/.ssh` is a private directory with the real entries read-only inside, so ssh can keep ControlMaster sockets. Without a record, the shell runs unsandboxed.
- `sandbox.allow` is the global registry: one `ro PATH` or `rw PATH` per line, `~` expanded, missing paths skipped.
- `sessionstartsandbox.py` records the project root, the git repo `$CLAUDE_PROJECT_DIR` sits in or that directory outside a repo, in `~/.claude/sandbox/<session_id>`.
- `pretoolusewrite.py` denies Write, Edit and NotebookEdit on a path whose real path is outside the project.
- Steps 2 and 3 come before step 5: once `pretoolusewrite.py` is registered, Write cannot reach `~/.claude`; once the prefix is live, neither can Bash.
- `|| exit 2` denies the call if the guard is broken, instead of running it unguarded.
