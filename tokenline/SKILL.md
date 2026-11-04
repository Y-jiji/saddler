---
name: tokenline
description: set up the status line `<TOKEN COUNT> @ <FOLDER> (<BRANCH>) [<ROLE>]`
disable-model-invocation: true
---

Do these in order:
1. Check `jq` is on `PATH`; if it is missing, stop and tell the user.
2. From this skill's directory, copy `statusline.sh` to `~/.claude/statusline.sh` and make it executable.
3. Set `"statusLine": {"type": "command", "command": "~/.claude/statusline.sh"}` in `~/.claude/settings.json`.

Why:
- The status line reads like:
  ```
  <TOKEN COUNT> @ <FOLDER> (<BRANCH>) [<ROLE>]
  ```
  Example:
  ```
  1.3k @ ~/Documents/Project (main)
  1000.7k @ ~/Documents/Project (master) [owner]
  1.3k @ ~/Documents/Project (main) [fork]
  ```
  If not inside `~`, show absolute path.
  If not inside a git repo, show no branch.
  Example:
  ```
  0k @ /etc/sudoers
  ```
- `statusline.sh` reads the token count, folder and session from the JSON Claude Code passes on stdin, and the branch from git.
- `[owner]` or `[fork]` is this session's fileguard role, read from `lock/owner.info` and `lock/<session>-master` under `~/.claude/sandbox`. A session that has run no command yet, or a project without fileguard, shows no role.
