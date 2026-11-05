#!/usr/bin/env python3
"""PreToolUse hook. Every agent works on its own view of the project, kept by a
holder process. A subagent's Bash and Monitor commands gain a first line naming it
for sandbox.sh. Read, Write, Edit and NotebookEdit act on the calling agent's view,
Grep and Glob are refused, and starting a subagent needs a commit.
"""

import json
import os
import re
import subprocess
import sys
from typing import Final
from urllib.parse import quote

TAG_HEAD: Final = "# saddler"
SHELL_TOOLS: Final = ("Bash", "Monitor")
SPAWN_TOOLS: Final = ("Agent",)
SEARCH_TOOLS: Final = ("Grep", "Glob")
VIEW_FIELDS: Final = {"Read": "file_path", "Write": "file_path", "Edit": "file_path",
                      "NotebookEdit": "notebook_path"}


def project_root(anchor):
    r = subprocess.run(["git", "-C", anchor, "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else anchor


def tagline(agent: str | None) -> str:
    """The comment line sandbox.sh strips from a shell command."""
    return TAG_HEAD + (" agent=%s" % agent if agent else "")


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


def holder(lock: str, session: str, agent: str) -> str:
    """The PID of an agent's live holder; a no-op command through sandbox.sh starts one if none is live."""
    prefix = os.environ.get("CLAUDE_CODE_SHELL_PREFIX")
    for attempt in range(2):
        try:
            with open(os.path.join(lock, "%s-%s" % (session, agent))) as f:
                words = f.read().split()
            with open("/proc/%s/stat" % words[0]) as f:
                if f.read().rsplit(")", 1)[1].split()[19] == words[4]:
                    return words[0]
        except (OSError, IndexError):
            pass
        if attempt == 0 and prefix:
            subprocess.run([prefix, "%s\ntrue" % tagline(agent)], capture_output=True,
                           env={**os.environ, "CLAUDE_CODE_SESSION_ID": session})
    return ""


def rewrite(path: str, cwd: str, pid: str) -> str:
    """A path as the holder sees it, through /proc/<pid>/root."""
    return "/proc/%s/root%s" % (pid, os.path.normpath(os.path.join(cwd, path)))


def main() -> None:
    """Handle one PreToolUse call, top to bottom."""
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
    if not re.fullmatch(r"[A-Za-z0-9-]+", session):
        return
    os.makedirs(os.path.join(os.path.dirname(lock), "session-" + session), exist_ok=True)
    os.makedirs(lock, exist_ok=True)

    field = VIEW_FIELDS.get(tool)
    if tool in SEARCH_TOOLS + SPAWN_TOOLS or field is not None:
        head = subprocess.run(["git", "-C", root, "rev-parse", "--verify", "-q", "HEAD"], capture_output=True)
        if head.returncode != 0:
            if tool in SPAWN_TOOLS:
                json.dump(denial("%s is not a git repository with a commit. Subagents "
                                 "start from the last commit." % root), sys.stdout)
            return
    if tool in SEARCH_TOOLS:
        json.dump(denial("%s reads the real project, not your own view of it. Use rg or find "
                         "in Bash instead." % tool), sys.stdout)
        return

    if field is not None:
        pid = holder(lock, session, agent or "master")
        if not pid:
            json.dump(denial("%s cannot reach your view of the project. Run a Bash command "
                             "to see why." % tool), sys.stdout)
            return
        json.dump({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "updatedInput": {**tooluse, field: rewrite(tooluse.get(field) or "", cwd, pid)},
            },
        }, sys.stdout)
        return

    if tool in SHELL_TOOLS and agent:
        command = tooluse.get("command") or ""
        json.dump({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "updatedInput": {**tooluse, "command": tagline(agent) + "\n" + command},
            },
        }, sys.stdout)


if __name__ == "__main__":
    main()
