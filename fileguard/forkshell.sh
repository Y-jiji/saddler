#!/bin/bash
# forkshell.sh NAME [COMMAND...]
# A person's command, or interactive bash, on their own view of the project, like
# an agent's: it runs through sandbox.sh as a tool call of session
# human-NAME-<project hash>, whose Claude process is this terminal's shell, and
# that session's branch is published when it ends. The interactive bash also
# sources this file as its init file.
if [ "${BASH_SOURCE[0]}" != "$0" ]; then
    if [ -f ~/.bashrc ]; then . ~/.bashrc; fi
    PS1="(fork ${SADDLER_FORK:-}) ${PS1:-\$ }"
    return
fi
NAME=${1:-}
shift
HERE=$(dirname "$(readlink -f "$0")")

# [1] the project and its state folder; refuse outside a git project or with a bad NAME
if [[ ! $NAME =~ ^[A-Za-z0-9][A-Za-z0-9-]*$ ]]; then
    echo "usage: forkshell.sh NAME [COMMAND...], NAME being letters, digits and dashes" >&2
    exit 1
fi
ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "forkshell.sh: $PWD is not in a git project" >&2
    exit 1
}
ROOT=$(readlink -f "$ROOT")
STATE_FOLDER=$HOME/.claude/sandbox/project-$(python3 -c 'import sys, urllib.parse as u; print(u.quote(sys.argv[1], safe=""))' "$ROOT")
SESSION=human-$NAME-$(printf '%s' "$ROOT" | sha1sum | cut -c1-8)

# [2] the session folder
mkdir -p "$STATE_FOLDER/session-$SESSION" || exit 1

# [3] sandbox.sh, as a tool call of that session
RUN="bash --init-file $(printf '%q' "$HERE/forkshell.sh") -i"
if [ $# -gt 0 ]; then printf -v RUN '%q ' "$@"; fi
exec env CLAUDE_CODE_SESSION_ID="$SESSION" CLAUDE_PID="$PPID" SADDLER_FORK="$NAME" \
    "$HERE/sandbox.sh" "eval '${RUN//\'/\'\\\'\'}'"
