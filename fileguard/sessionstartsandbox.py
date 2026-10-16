#!/usr/bin/env python3
"""SessionStart hook: record this session's project root for sandbox.sh.

sandbox.sh, run as CLAUDE_CODE_SHELL_PREFIX for every shell Claude Code
starts, finds the root in ~/.claude/sandbox/<session_id> through
$CLAUDE_CODE_SESSION_ID and confines the shell to it; a session without a
record runs unsandboxed. The root is the git repository CLAUDE_PROJECT_DIR
sits in, or that directory itself outside a repository, as in
pretoolusewrite.py.

In a session that already has a record, as on continue or compact, this hook
runs inside the sandbox, where the record is not visible and ~/.claude is
read-only; the write fails and the hook does nothing.
"""

import json
import os
import re
import subprocess
import sys


def project_root(anchor):
    r = subprocess.run(["git", "-C", anchor, "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else anchor


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return
    # the same shape sandbox.sh accepts, so no path can be spliced in
    sid = payload.get("session_id") or ""
    if not re.fullmatch(r"[A-Za-z0-9-]+", sid):
        return
    record = os.path.join(os.path.expanduser("~"), ".claude", "sandbox", sid)
    if os.path.exists(record):
        return

    anchor = (os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd")
              or os.getcwd())
    root = os.path.realpath(project_root(anchor))
    try:
        os.makedirs(os.path.dirname(record), exist_ok=True)
        tmp = "%s.%d" % (record, os.getpid())
        with open(tmp, "w") as f:
            f.write(root + "\n")
        os.replace(tmp, record)
    except OSError:
        return


if __name__ == "__main__":
    main()
