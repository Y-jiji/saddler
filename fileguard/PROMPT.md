# Agent View

You work on your own view of the project: your file changes and commits are yours alone until published. After each Bash command, your branch is published as `session-<session>/agent-<agent>`, which every agent sees as `saddler/session-<session>/agent-<agent>`.

The real branches are under `saddler/`, read-only and always current. Merge or rebase onto `saddler/<default branch>` when you need others' work. Commit your work: uncommitted work is lost at the next checkpoint.

Grep and Glob are refused. Use `rg` and `find` in Bash instead.

`git checkpoint` makes your committed branch everyone's base: it runs the build, moves the default branch to your HEAD, replaces the real project with your view, ends every agent's running commands and discards all uncommitted work. Run it only when the user asks, or when your branch is ready to become everyone's base.
