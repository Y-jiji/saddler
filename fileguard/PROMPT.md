# Agent View

You work on your own view of the project: your file changes and commits are yours alone until published. After each Bash command, your branch is published as `session-<session>/agent-<agent>`, which every agent sees as `saddler/session-<session>/agent-<agent>`.

The real branches are under `saddler/`, read-only and always current. Merge or rebase onto `saddler/<default branch>` when you need others' work. Commit your work: uncommitted work is lost at the next checkpoint.

Read is refused on project files, and Write, Edit, NotebookEdit, Grep and Glob everywhere. Use Bash instead: `cat`, `sed`, `rg`, `find` and heredocs. To view an image or PDF in the project, copy it to `/tmp` and Read it there.

`git checkpoint` makes your committed branch everyone's base: it runs `$SADDLER_BUILD` in your view, moves the default branch to your HEAD, replaces the real project with your view, ends every agent's running commands and discards all uncommitted work.

`SADDLER_BUILD` is set by the user in `.claude/settings.json`. The checkpoint's build outputs become every view's starting build, so no agent repeats that incremental build. If you are not a subagent, and `echo $SADDLER_BUILD` is empty or misses part of the project's build, tell the user once what a better `SADDLER_BUILD` would be.
