---
name: fileguard
description: sandbox Bash, give subagents and other sessions forks, and guard Write, Edit and NotebookEdit for this project
disable-model-invocation: true
---

Do these in order:
1. Check `bwrap`, `flock`, `setsid`, `nsenter`, `tail`, `git` and `python3` are on `PATH`; if any is missing, stop and tell the user.
2. From this skill's directory, copy `sandbox.sh`, `allowlist.sh`, `gitlock.sh`, `gitwrap.sh`, `overlayfork.sh` and `overlayowner.sh` to `~/.claude/saddler/`, and `whitelist.txt` to `~/.claude/sandbox/` unless that file already exists.
3. Add `"env": {"CLAUDE_CODE_SHELL_PREFIX": "<absolute path of ~/.claude/saddler/sandbox.sh>"}` to `~/.claude/settings.json`.
4. From this skill's directory, copy `sessionstartsandbox.py`, `pretoolusewrite.py` and `subagentstop.sh` into `<project>/.claude/hooks/`.
5. Register in `<project>/.claude/settings.json`. `<session>` is `python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/sessionstartsandbox.py"`, `<guard>` is `python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/pretoolusewrite.py" || exit 2`, and `<stop>` is `bash "$CLAUDE_PROJECT_DIR/.claude/hooks/subagentstop.sh" || exit 2`:
   - SessionStart: `<session>`, timeout 10, and `<stop>`, timeout 110
   - PreToolUse, matcher `Agent|Bash|Monitor|Write|Edit|NotebookEdit|Read|Grep|Glob`: `<guard>`, timeout 110
   - PostToolUse, matcher `TaskStop`: `<stop>`, timeout 110
   - SubagentStop: `<stop>`, timeout 110
   - SessionEnd: `<stop>`, timeout 110
   - Optional: `"env": {"SADDLER_CHECKPOINT_PERIOD": "300", "SADDLER_PREEMPT_WAIT": "60"}`, in seconds, these values being the defaults. Keep the wait under 100, because a waiting command can hit the Bash tool's timeout and a fork's last commit can hit the hook's.
6. Tell the user to restart claude, then check in the new session: `echo x > .claude/x` fails with `Read-only file system`, `ls /run` fails, Write to a file outside the project is denied, a subagent's `echo x > f` leaves the real `f` unchanged and lands on branch `saddler/<session-id>/<agent-id>`, a second session's Bash does the same on `saddler/<session-id>/master`, and, if `env` is set, `echo $SADDLER_CHECKPOINT_PERIOD` prints its value.

Why:
- The first session to run a command, or to use Write, Edit or NotebookEdit, owns the project and works on the real tracked files and `.git`, with gitignored folders on an overlay. Every other session, and every subagent, works on a fork.
- Gitignored folders are shared without a copy. The owner and each fork mount one overlay per folder, with the real folder as the lower and a private upper. Forks discard their uppers when they end. Single ignored files are copied into the base.
- Checkpointing moves the owner's upper into the real folder, and is the only step that changes one. It runs at the end of an owner command, in that command, when an upper or the ignored list changed, and no fork is registered or `SADDLER_CHECKPOINT_PERIOD` seconds passed since the last one. Without owner changes nothing happens.
- A checkpoint is skipped while another owner command or a process it left behind runs, because the owner is never killed. Otherwise it closes the gate so new fork commands wait, gives running fork commands `SADDLER_PREEMPT_WAIT` seconds, then kills every fork holder. A killed command, foreground or background, fails with a message telling the agent to run it again. Its files stay in the fork.
- A real folder must not change under a mounted overlay, so a fork's next command after a checkpoint starts a new holder. Cargo compares mtimes, so that command first touches the fork's files whose mtime or size differ from real, and the base keeps real mtimes on files equal to real. Otherwise cargo would call a newer shared build fresh and run the wrong code.
- A checkpoint interrupted by a crash is finished by the next owner command, and forks fail until then. The owner's upper stays whole until its final rename, so the owner's view stays correct.
- While a fork lives, or if the owner goes idle or ends before its next command, the real folder can stay stale, so your terminal, Read and Grep see the old contents. Write, Edit and NotebookEdit are denied inside overlaid folders. `cargo clean` empties `target/` but then fails, because a mountpoint cannot be removed. A folder created after the mount is written straight to real and shared after the next checkpoint.
- A finished agent's or session's work stays on `saddler/<session-id>/<agent-id>`; merge it yourself with `git merge`. Nothing merges automatically.
- A fork's project is the base commit plus its own writes. The base is `HEAD` at its first Bash call. Its `.git` is read-only, with `HEAD` and the index pinned to the base. Other branches stay visible by name. After each command, its files are committed to its branch as one commit whose parent is the base.
- A fork may only use Bash, because Write, Edit, NotebookEdit, Read, Grep and Glob bypass it. A fork cannot start subagents. Forking needs a git repository with a commit.
- One holder process per fork, and one for the owner, each with a PID namespace, keeps overlays mounted, so foreground commands, background commands and commits share one mount. No process can leave that namespace and every orphan becomes a child of the holder, so the holder's children show whether the owner left anything behind. Commands cannot see or signal host processes. Ending a fork ends its background commands. `SubagentStop`, `TaskStop` on an agent, `SessionEnd`, and `SessionStart` for a session whose Claude died all do this, make a last commit, and delete the fork.
- `gitlock.sh` holds a read lock for each fork command, and `gitwrap.sh`, mounted over `git` for the owner, takes the write lock for each git command, because replacing `.git/index` or `.git/HEAD` removes the pins from a running command. A wait fails after 100 seconds. `run_in_background` and `Monitor` calls skip the read lock.
- `allowlist.sh` runs a command in bwrap on an empty root holding only the host `/dev`, a fresh `/proc`, every library and `PATH` directory read-only, every dot entry in `~` read-only, the entries of `whitelist.txt`, and the project, with every `.claude` read-only.
- `whitelist.txt` is the global registry: one `ro PATH`, `rw PATH` or `private PATH STORE` per line, `~` expanded, missing paths skipped. `private` makes `PATH` writable into `STORE`, with its real entries read-only inside, so ssh can keep ControlMaster sockets in `~/.ssh`.
- State lives in `~/.claude/sandbox/project-<percent-encoded project folder>/`: `lock/`, and `session-<session-id>/` holding `agent-<agent-id>/{fork, work, ignored, generation}`, `agent-master/` and `commit-<commit-hash>/{HEAD, index, tree, generation}`. The owner's uppers live in `<project>/.git/saddler/owner/`, so moving them is a hard link on one filesystem. A session without that folder runs unsandboxed. `SessionStart` makes it, and `pretoolusewrite.py` makes it in print mode, where `SessionStart` does not fire.
- Claude Code's wrapper format is undocumented and tool calls are told from hook shells by it, so repeat the step 6 checks after updating Claude Code.
- Steps 2 and 3 come before step 5: once `pretoolusewrite.py` is registered, Write cannot reach `~/.claude`; once the prefix is live, neither can Bash.
- A session or project on the old hooks runs unguarded under this `sandbox.sh`: run `migrate.py --apply` outside the sandbox and restart every session.
- `|| exit 2` denies the call if the guard is broken, instead of running it unguarded.
