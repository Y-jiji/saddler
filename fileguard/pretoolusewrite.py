#!/usr/bin/env python3
"""PreToolUse and PostToolUse hook. Bash and Monitor commands gain a first line
for sandbox.sh. Subagents may not use file tools, which bypass their overlay.
Write, Edit and NotebookEdit may not leave the project, the git repository
CLAUDE_PROJECT_DIR sits in or that directory outside one, and hold the mode
lock until PostToolUse.
"""

import fcntl
import glob
import json
import os
import signal
import subprocess
import sys
import time
from typing import Final
from urllib.parse import quote

# the tool input field that holds the target path
PATH_FIELDS = {"Write": "file_path", "Edit": "file_path",
               "NotebookEdit": "notebook_path"}
TAG_HEAD: Final = "# saddler "
SHELL_TOOLS: Final = ("Bash", "Monitor")
FILE_TOOLS: Final = ("Write", "Edit", "NotebookEdit", "Read", "Grep", "Glob")
WAIT_SECONDS: Final = int(os.environ.get("SADDLER_WAIT", "100"))
HOLD_SECONDS: Final = 60
RELEASE_EVENTS: Final = ("PostToolUse", "PostToolUseFailure")


def project_root(anchor):
    r = subprocess.run(["git", "-C", anchor, "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else anchor


def tagline(root: str, payload: dict[str, object]) -> str:
    """The comment line sandbox.sh strips from a shell command: the project
    root, percent-encoded to stay one unquoted word, the session, and the agent
    for a subagent."""
    line = "%sroot=%s session=%s" % (TAG_HEAD, quote(root, safe=""),
                                     payload.get("session_id"))
    agent = payload.get("agent_id")
    return "%s agent=%s" % (line, agent) if agent else line


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
    """The folder of a project's mode lock, the path sandbox.sh also builds."""
    return os.path.join(os.path.expanduser("~"), ".claude", "sandbox", "lock",
                        quote(root, safe=""))


def entermode(root: str, session: str, toolid: str) -> bool:
    """Join this session's main mode as sandbox.sh does, then leave a detached
    sleep holding it, since the tool runs after this hook exits and PostToolUse
    ends the sleep early. False when the wait runs out."""
    lock = lockdir(root)
    os.makedirs(os.path.join(lock, "hold"), exist_ok=True)
    end = time.monotonic() + WAIT_SECONDS
    own = os.path.join(lock, "mode.main." + session)
    queue = os.open(os.path.join(lock, "queue"), os.O_CREAT | os.O_WRONLY, 0o644)
    mode = os.open(own, os.O_CREAT | os.O_WRONLY, 0o644)

    def take(*words: str) -> bool:
        left = "%.1f" % max(0, end - time.monotonic())
        return subprocess.run(["flock", "-w", left, *words],
                              pass_fds=(queue,)).returncode == 0

    if not take(str(queue)):
        return False
    fcntl.flock(mode, fcntl.LOCK_SH)
    for other in glob.glob(os.path.join(glob.escape(lock), "mode.*")):
        if other != own and not take("-x", other, "true"):
            return False
    holder = subprocess.Popen(["sleep", str(HOLD_SECONDS)], pass_fds=(mode,),
                              stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL,
                              start_new_session=True)
    with open(os.path.join(lock, "hold", quote(toolid, safe="")), "w") as f:
        f.write(str(holder.pid))
    return True


def release(root: str, toolid: str) -> None:
    """End the sleep entermode left for this tool call, if there is one."""
    path = os.path.join(lockdir(root), "hold", quote(toolid, safe=""))
    try:
        with open(path) as f:
            pid = int(f.read())
        os.unlink(path)
        os.kill(pid, signal.SIGTERM)
    except (OSError, ValueError):
        return


def main():
    payload = json.load(sys.stdin)
    tool = payload.get("tool_name") or ""
    tooluse = payload.get("tool_input") or {}
    toolid = payload.get("tool_use_id") or ""
    if payload.get("agent_id") and tool in FILE_TOOLS:
        json.dump(denial("Subagents work in a private overlay that %s cannot "
                         "see. Use Bash instead." % tool), sys.stdout)
        return
    field = PATH_FIELDS.get(tool)
    if field is None and tool not in SHELL_TOOLS:
        return

    cwd = payload.get("cwd") or os.getcwd()
    anchor = os.environ.get("CLAUDE_PROJECT_DIR") or cwd
    root = os.path.realpath(project_root(anchor))
    if payload.get("hook_event_name") in RELEASE_EVENTS:
        release(root, toolid)
        return
    if tool in SHELL_TOOLS:
        command = tooluse.get("command") or ""
        json.dump({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "updatedInput": {
                    **tooluse,
                    "command": tagline(root, payload) + "\n" + command,
                },
            },
        }, sys.stdout)
        return

    path = tooluse.get(field) or ""
    real = os.path.realpath(os.path.join(cwd, path))
    if real != root and not real.startswith(root + os.sep):
        json.dump(denial("%s is outside the project %s. %s may only change "
                         "files inside it." % (path, root, tool)), sys.stdout)
    elif not entermode(root, str(payload.get("session_id")), toolid):
        json.dump(denial("Waited %ds for other commands in this project to "
                         "finish. Try again." % WAIT_SECONDS), sys.stdout)


if __name__ == "__main__":
    main()
