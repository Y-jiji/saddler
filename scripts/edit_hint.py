#!/usr/bin/env python3
"""PostToolUse hook for Bash: name the right tool after edit_guard refuses a write.

edit_guard.py freezes every .git and .claude in the repository, and
everything outside it but /tmp and the home dot entries not in its HOME_DENY,
with a read-only bind mount, so a command that writes there fails with a raw
kernel error and no indication of what to do instead. This turns that error
into a one-line hint.

Both PostToolUse and PostToolUseFailure are handled: a refused write does not
always make the command exit non-zero -- `perl -e 'unlink'` returns 0 while
the file survives.
"""

import json
import sys

# kernel errors a read-only bind mount produces; the script path is
# deliberately not a signature, since any error from the command would carry it
SIGNATURES = ("Read-only file system", "Device or resource busy",
              "Errno 30", "EROFS")

HINT = ("Bash can write only the repo except every `.git` and `.claude` in it, "
        "`/tmp` and dot entries in `~` except `.claude`, `.claude.json`, "
        "`.gitconfig`, `.ssh`, `.config` and shell startup files. Use "
        "Edit/Write to change a file in the project, a non-compound "
        "`git ...` command to change `.git`.")


def flatten(value):
    """Tool responses vary in shape; collect every string in one blob."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(flatten(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return " ".join(flatten(v) for v in value)
    return ""


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return
    if (payload.get("tool_name") or "") != "Bash":
        return

    blob = flatten(payload.get("tool_response")) + flatten(payload.get("error"))
    if not any(s in blob for s in SIGNATURES):
        return

    json.dump({
        "hookSpecificOutput": {
            "hookEventName": payload.get("hook_event_name") or "PostToolUse",
            "additionalContext": HINT,
        },
    }, sys.stdout)


if __name__ == "__main__":
    main()
