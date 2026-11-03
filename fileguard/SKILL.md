---
name: fileguard
description: sandbox Bash and guard Write, Edit and NotebookEdit for this project
disable-model-invocation: true
---

Do these in order:
1. Check `bwrap`, `flock` and `python3` are on `PATH`; if any is missing, stop and tell the user.
2. From this skill's directory, copy `sandbox.sh` to `~/.claude/sandbox.sh`, and `sandbox.allow` to `~/.claude/sandbox/allow` unless that file already exists.
3. Add `"env": {"CLAUDE_CODE_SHELL_PREFIX": "<absolute path of ~/.claude/sandbox.sh>"}` to `~/.claude/settings.json`.
4. From this skill's directory, copy `pretoolusewrite.py` into `<project>/.claude/hooks/`.
5. Register in `<project>/.claude/settings.json`, each running `python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/pretoolusewrite.py" || exit 2`:
   - PreToolUse, matcher `Bash|Monitor|Write|Edit|NotebookEdit|Read|Grep|Glob`, timeout 110
   - PostToolUse, matcher `Write|Edit|NotebookEdit`, timeout 10
   - PostToolUseFailure, matcher `Write|Edit|NotebookEdit`, timeout 10
6. Tell the user to restart claude, then check in the new session: `echo x > .git/config` fails with `Read-only file system`, `ls /run` fails, Write to a file outside the project is denied, a subagent's `echo x > f` leaves the real `f` unchanged and lands in `~/.claude/sandbox/overlay/<session>/<agent>/upper`, and a main Write waits while a subagent's command runs.

Why:
- `sandbox.sh` runs every shell Claude Code starts. For a command with a tag line, the shell runs in bwrap on an empty root holding only the host `/dev`, a fresh `/proc`, every library and `PATH` directory read-only, every dot entry in `~` read-only, the entries of `~/.claude/sandbox/allow`, and the project writable except `config` and `hooks` under every `.git`, every `.git` that is a file and every `.claude`. `~/.ssh` is a private directory with the real entries read-only inside, so ssh can keep ControlMaster sockets. Without a tag line, the shell runs unsandboxed.
- `sandbox.allow` is the global registry: one `ro PATH` or `rw PATH` per line, `~` expanded, missing paths skipped.
- The tag line, `# saddler root=<percent-encoded path> session=<id> agent=<id>`, is a comment `pretoolusewrite.py` puts first in every Bash and Monitor command. `sandbox.sh` finds it inside Claude Code's wrapper in `$1` and strips it. Only a subagent has an `agent`.
- The wrapper format is undocumented and a missed tag line runs unguarded with no error, so repeat the step 6 checks after updating Claude Code.
- A subagent's project is a private overlay: its writes land in `~/.claude/sandbox/overlay/<session>/<agent>/upper` and stay there, since nothing merges them. `$TMPDIR` and the `rw` entries of the registry stay shared.
- No overlay may be mounted while its lower folder changes, so each project has a mode lock in `~/.claude/sandbox/lock/`: one mode at a time, subagents or one session's main, and calls in that mode run together. A call queues for its turn and fails after 100 seconds; a call holds its mode until its last process, background ones included, exits. One agent's own calls run one at a time, because only one mount can use an overlay. An editor or hook command that writes to the project takes no lock.
- `pretoolusewrite.py` adds the tag line, denies Write, Edit and NotebookEdit on a path whose real path is outside the project, and denies Write, Edit, NotebookEdit, Read, Grep and Glob to subagents, because those tools bypass the overlay. For an allowed Write, Edit or NotebookEdit it holds the mode lock with a detached 60-second `sleep`, which PostToolUse and PostToolUseFailure end early.
- The PreToolUse timeout of 110 outlasts the 100-second wait for the lock, so a long wait ends in a denial rather than a killed hook.
- Steps 2 and 3 come before step 5: once `pretoolusewrite.py` is registered, Write cannot reach `~/.claude`; once the prefix is live, neither can Bash.
- A session or project on the old hooks sends no tag line, so it runs unguarded under this `sandbox.sh`: run `migrate.py --apply` outside the sandbox and restart every session.
- `|| exit 2` denies the call if the guard is broken, instead of running it unguarded.
