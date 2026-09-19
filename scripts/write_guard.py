#!/usr/bin/env python3
"""PreToolUse hook for Write, Edit and NotebookEdit: deny a path outside the
project.

The project is the git repository CLAUDE_PROJECT_DIR sits in, or that
directory itself outside a repository -- the anchor edit_guard.py uses, so a
session cannot change another project through these tools either. The path is
resolved with realpath first, so `..` cannot climb out and a symlink inside the
project that points outside it is denied.
"""

import json
import os
import subprocess
import sys

# the tool input field that holds the target path
PATH_FIELDS = {"Write": "file_path", "Edit": "file_path",
               "NotebookEdit": "notebook_path"}


def project_root(anchor):
    r = subprocess.run(["git", "-C", anchor, "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else anchor


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return
    tool = payload.get("tool_name") or ""
    field = PATH_FIELDS.get(tool)
    if field is None:
        return
    path = (payload.get("tool_input") or {}).get(field) or ""
    cwd = payload.get("cwd") or os.getcwd()

    anchor = os.environ.get("CLAUDE_PROJECT_DIR") or cwd
    root = os.path.realpath(project_root(anchor))
    real = os.path.realpath(os.path.join(cwd, path))
    if real == root or real.startswith(root + os.sep):
        return

    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason":
                "%s is outside the project %s. %s may only change files "
                "inside it." % (path, root, tool),
        },
    }, sys.stdout)


if __name__ == "__main__":
    main()
