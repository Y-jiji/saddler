#!/usr/bin/env python3
"""PreToolUse hook. A subagent's Bash and Monitor commands, and any background
command, gain a first line for sandbox.sh. A fork may only use Bash. Write, Edit
and NotebookEdit may not leave the project, and claim it for this session.
"""

import fcntl
import json
import os
import re
import subprocess
import sys
from typing import Final
from urllib.parse import quote

# the tool input field that holds the target path
PATH_FIELDS = {"Write": "file_path", "Edit": "file_path",
               "NotebookEdit": "notebook_path"}
TAG_HEAD: Final = "# saddler"
SHELL_TOOLS: Final = ("Bash", "Monitor")
FILE_TOOLS: Final = ("Write", "Edit", "NotebookEdit", "Read", "Grep", "Glob")
SPAWN_TOOLS: Final = ("Agent",)


def project_root(anchor):
    r = subprocess.run(["git", "-C", anchor, "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else anchor


def tagline(agent: str | None, nolock: bool) -> str:
    """The comment line sandbox.sh strips from a shell command."""
    line = TAG_HEAD
    if agent:
        line += " agent=%s" % agent
    if nolock:
        line += " nolock"
    return line


def denial(reason: str) -> dict[str, object]:
    """Hook output that refuses this tool call and tells Claude why."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
    }


def lockdir(root: str) -> str:
    """The folder of a project's locks, the path sandbox.sh also builds."""
    return os.path.join(os.path.expanduser("~"), ".claude", "sandbox",
                        "project-" + quote(root, safe=""), "lock")


def inignored(lock: str, rel: str) -> bool:
    """Whether a project path lies in a gitignored folder that overlays use as a lower."""
    try:
        with open(os.path.join(lock, "ignored"), "rb") as f:
            entries = f.read().split(b"\0")
    except OSError:
        return False
    path = os.fsencode(rel) + b"/"
    return any(e.endswith(b"/") and path.startswith(e) for e in entries)


def main() -> None:
    """Handle one PreToolUse call, top to bottom. SHAME(TALLFUNC)"""
    payload = json.load(sys.stdin)
    if payload.get("hook_event_name", "PreToolUse") != "PreToolUse":
        return
    tool = payload.get("tool_name") or ""
    tooluse = payload.get("tool_input") or {}
    agent = payload.get("agent_id")
    session = str(payload.get("session_id"))
    cwd = payload.get("cwd") or os.getcwd()
    anchor = os.environ.get("CLAUDE_PROJECT_DIR") or cwd
    root = os.path.realpath(project_root(anchor))
    lock = lockdir(root)
    if re.fullmatch(r"[A-Za-z0-9-]+", session):
        os.makedirs(os.path.join(os.path.dirname(lock), "session-" + session), exist_ok=True)
        os.makedirs(lock, exist_ok=True)

    forked = os.path.exists(os.path.join(lock, "%s-master" % session))
    if tool in FILE_TOOLS and (agent or forked):
        json.dump(denial("This session works on a private fork that %s cannot "
                         "see. Use Bash instead." % tool), sys.stdout)
        return
    if tool in SPAWN_TOOLS and forked:
        json.dump(denial("This session works on a fork, like a subagent, so it "
                         "cannot start subagents."), sys.stdout)
        return

    if tool in SPAWN_TOOLS:
        head = subprocess.run(["git", "-C", root, "rev-parse", "--verify", "-q", "HEAD"], capture_output=True)
        if head.returncode != 0:
            json.dump(denial("%s is not a git repository with a commit. Subagents "
                             "start from the last commit." % root), sys.stdout)
            return

    field = PATH_FIELDS.get(tool)
    if field is not None:
        path = tooluse.get(field) or ""
        real = os.path.realpath(os.path.join(cwd, path))
        if real != root and not real.startswith(root + os.sep):
            json.dump(denial("%s is outside the project %s. %s may only change "
                             "files inside it." % (path, root, tool)), sys.stdout)
            return
        if inignored(lock, os.path.relpath(real, root)):
            json.dump(denial("%s is in a gitignored folder that subagents share. "
                             "Use Bash instead: it writes to an overlay." % path), sys.stdout)
            return

    if field is not None or tool in SPAWN_TOOLS:
        claude = os.environ.get("CLAUDE_PID") or str(os.getppid())
        fd = os.open(os.path.join(lock, "owner"), os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o644)
        other = None
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if field is not None:
                with open(os.path.join(lock, "owner.info"), "w") as f:
                    f.write("%s %s\n" % (claude, session))
                subprocess.Popen(["tail", "--pid=" + claude, "-f", "/dev/null"], pass_fds=(fd,), cwd="/",
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
        except BlockingIOError:
            with open(os.path.join(lock, "owner.info")) as f:
                holder, owner = (f.read().split() + ["", "another session"])[:2]
            other = None if holder == claude else owner
        os.close(fd)
        if other is not None:
            json.dump(denial("Session %s owns %s. Use Bash instead: it runs on a "
                             "private fork of the last commit." % (other, root)), sys.stdout)
            return

    if tool in SHELL_TOOLS:
        nolock = tool == "Monitor" or bool(tooluse.get("run_in_background"))
        if agent or nolock:
            command = tooluse.get("command") or ""
            json.dump({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "updatedInput": {**tooluse, "command": tagline(agent, nolock) + "\n" + command},
                },
            }, sys.stdout)


if __name__ == "__main__":
    main()
