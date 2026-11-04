---
name: fileguard
description: sandbox Bash, give subagents and other sessions forks, and guard Write, Edit and NotebookEdit for this project
disable-model-invocation: true
---

Do these in order:
1. Check `bwrap`, `flock`, `setsid`, `nsenter`, `tail`, `git` and `python3` are on `PATH`; if any is missing, stop and tell the user.
2. From this skill's directory, copy `sandbox.sh`, `allowlist.sh`, `gitlock.sh`, `gitwrap.sh` and `overlayfork.sh` to `~/.claude/saddler/`, and `whitelist.txt` to `~/.claude/sandbox/` unless that file already exists.
3. Add `"env": {"CLAUDE_CODE_SHELL_PREFIX": "<absolute path of ~/.claude/saddler/sandbox.sh>"}` to `~/.claude/settings.json`.
4. From this skill's directory, copy `sessionstartsandbox.py`, `pretoolusewrite.py` and `subagentstop.sh` into `<project>/.claude/hooks/`.
5. Register in `<project>/.claude/settings.json`. `<session>` is `python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/sessionstartsandbox.py"`, `<guard>` is `python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/pretoolusewrite.py" || exit 2`, and `<stop>` is `bash "$CLAUDE_PROJECT_DIR/.claude/hooks/subagentstop.sh" || exit 2`:
   - SessionStart: `<session>`, timeout 10, and `<stop>`, timeout 110
   - PreToolUse, matcher `Agent|Bash|Monitor|Write|Edit|NotebookEdit|Read|Grep|Glob`: `<guard>`, timeout 110
   - PostToolUse, matcher `TaskStop`: `<stop>`, timeout 110
   - SubagentStop: `<stop>`, timeout 110
   - SessionEnd: `<stop>`, timeout 110
6. Tell the user to restart claude, then check in the new session: `echo x > .claude/x` fails with `Read-only file system`, `ls /run` fails, Write to a file outside the project is denied, a subagent's `echo x > f` leaves the real `f` unchanged and lands on branch `saddler/<session-id>/<agent-id>`, and a second session's Bash does the same on `saddler/<session-id>/master`.

Why:
- The first session to run a command, or to use Write, Edit or NotebookEdit, owns the project and works on the real files. Every other session, and every subagent, works on a fork.
- A finished agent's or session's work stays on `saddler/<session-id>/<agent-id>`; merge it yourself with `git merge`. Nothing merges automatically.
- A fork's project is the base commit plus its own writes. The base is `HEAD` at its first Bash call. Its `.git` is read-only, with `HEAD` and the index pinned to the base. Other branches stay visible by name. After each command, its files are committed to its branch as one commit whose parent is the base.
- A fork may only use Bash, because Write, Edit, NotebookEdit, Read, Grep and Glob bypass it. A fork cannot start subagents. Forking needs a git repository with a commit.
- One holder process per fork keeps its overlay mounted, so foreground commands, background commands and commits share one mount. Ending a fork ends its background commands. `SubagentStop`, `TaskStop` on an agent, `SessionEnd`, and `SessionStart` for a session whose Claude died all do this, make a last commit, and delete the fork.
- `gitlock.sh` holds a read lock for each fork command, and `gitwrap.sh`, mounted over `git` for the owner, takes the write lock for each git command, because replacing `.git/index` or `.git/HEAD` removes the pins from a running command. A wait fails after 100 seconds. `run_in_background` and `Monitor` calls skip the read lock.
- `allowlist.sh` runs a command in bwrap on an empty root holding only the host `/dev`, a fresh `/proc`, every library and `PATH` directory read-only, every dot entry in `~` read-only, the entries of `whitelist.txt`, and the project, with every `.claude` read-only.
- `whitelist.txt` is the global registry: one `ro PATH`, `rw PATH` or `private PATH STORE` per line, `~` expanded, missing paths skipped. `private` makes `PATH` writable into `STORE`, with its real entries read-only inside, so ssh can keep ControlMaster sockets in `~/.ssh`.
- State lives in `~/.claude/sandbox/project-<percent-encoded project folder>/`: `lock/`, and `session-<session-id>/` holding `agent-<agent-id>/{fork, work}`, `agent-master/` and `commit-<commit-hash>/{HEAD, index, tree}`. A session without that folder runs unsandboxed. `SessionStart` makes it, and `pretoolusewrite.py` makes it in print mode, where `SessionStart` does not fire.
- Claude Code's wrapper format is undocumented and tool calls are told from hook shells by it, so repeat the step 6 checks after updating Claude Code.
- Steps 2 and 3 come before step 5: once `pretoolusewrite.py` is registered, Write cannot reach `~/.claude`; once the prefix is live, neither can Bash.
- A session or project on the old hooks runs unguarded under this `sandbox.sh`: run `migrate.py --apply` outside the sandbox and restart every session.
- `|| exit 2` denies the call if the guard is broken, instead of running it unguarded.
