#!/usr/bin/env python3
"""PreToolUse hook for the Bash tool: refuse shell commands that write code files.

The decision is made from the command string alone, before anything runs. The
hook touches no files and runs no git. Nothing is modified, so nothing has to be
restored -- the failure modes are a missed command (an edit gets through) or an
over-eager match (a command is blocked), never destroyed work.

Version control commands are not analyzed. `git stash pop`, `git reset`,
`git checkout` and friends write files out of the object store on purpose;
they are the user's business, not a shell edit.
"""

import json
import os
import re
import sys

CODE_EXT = {
    ".c", ".cc", ".cpp", ".cs", ".css", ".cxx", ".ex", ".exs", ".go", ".h",
    ".hpp", ".hs", ".html", ".java", ".jl", ".js", ".json", ".jsx", ".kt",
    ".lua", ".m", ".md", ".mjs", ".ml", ".php", ".pl", ".py", ".r", ".rb",
    ".rs", ".scala", ".scss", ".sh", ".sql", ".svelte", ".swift", ".toml",
    ".ts", ".tsx", ".vue", ".yaml", ".yml", ".zig",
}

VCS = {"git", "hg", "svn", "jj", "bzr"}     # manage their own files
INPLACE = {"sed", "perl", "ruby"}           # only with -i
DEST_LAST = {"cp", "mv", "install", "rsync"}  # only the final argument
WRITES_ARGS = {"rm", "truncate", "tee", "patch", "shred", "unlink", "chmod",
               "touch", "split"}

REDIRECT_RE = re.compile(r"(?<![0-9<>])>>?\s*([^\s|;&<>()]+)")
DD_OF_RE = re.compile(r"\bof=([^\s|;&<>()]+)")
SEGMENT_RE = re.compile(r"\|\||&&|[|;&\n]")


def is_code(path):
    return os.path.splitext(path)[1].lower() in CODE_EXT


def tokens(text):
    return [t.strip("\"'") for t in text.split() if t.strip("\"'")]


def written_paths(command):
    """Paths this command line looks like it writes. Conservative, not exact."""
    hits = set()
    for segment in SEGMENT_RE.split(command):
        words = tokens(segment)
        if not words:
            continue
        # step past env assignments and sudo so the real command is at the head
        i = 0
        while i < len(words) and ("=" in words[i] or words[i] in ("sudo", "env")):
            i += 1
        if i >= len(words):
            head = ""
        else:
            head = os.path.basename(words[i])
        args = [w for w in words[i + 1:] if not w.startswith("-")]

        if head in VCS:
            continue  # version control writes files on purpose

        if head in WRITES_ARGS:
            hits.update(args)
        elif head in INPLACE and any(w.startswith("-i") for w in words[i + 1:]):
            hits.update(args)
        elif head in DEST_LAST and args:
            hits.add(args[-1])
        elif head == "dd":
            hits.update(DD_OF_RE.findall(segment))

        hits.update(REDIRECT_RE.findall(segment))
    return hits


def in_project(path, cwd):
    """True when path resolves inside the session's working directory."""
    root = os.path.realpath(cwd)
    full = os.path.realpath(os.path.join(cwd, os.path.expanduser(path)))
    return full == root or full.startswith(root + os.sep)


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return
    if (payload.get("tool_name") or "") != "Bash":
        return
    cwd = payload.get("cwd") or os.getcwd()
    command = (payload.get("tool_input") or {}).get("command", "")

    targets = sorted(
        p for p in written_paths(command) if is_code(p) and in_project(p, cwd)
    )
    if not targets:
        return

    reason = (
        "This command writes code files in the project: %s\n"
        "Use the Edit or Write tool instead. The command was not run; "
        "no file was changed." % ", ".join(targets)
    )
    json.dump(
        {
            "systemMessage": "Blocked a Bash write to: " + ", ".join(targets),
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            },
        },
        sys.stdout,
    )


if __name__ == "__main__":
    main()
