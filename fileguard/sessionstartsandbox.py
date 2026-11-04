#!/usr/bin/env python3
"""SessionStart hook: make this session's folder under ~/.claude/sandbox.

sandbox.sh, run as CLAUDE_CODE_SHELL_PREFIX for every shell Claude Code starts,
confines a session that has this folder and runs any other as it is. The hook
does not fire in print mode, so pretoolusewrite.py makes the folder there.
"""

import json
import os
import re
import sys

from pretoolusewrite import lockdir, project_root


def main() -> None:
    """Make the folder for the session named on stdin."""
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return
    session = payload.get("session_id") or ""
    if not re.fullmatch(r"[A-Za-z0-9-]+", session):
        return
    anchor = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    root = os.path.realpath(project_root(anchor))
    try:
        os.makedirs(os.path.join(os.path.dirname(lockdir(root)), "session-" + session), exist_ok=True)
    except OSError:
        return


if __name__ == "__main__":
    main()
