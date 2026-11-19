#!/usr/bin/env bash
# sandbox.sh INVOCATION
# CLAUDE_CODE_SHELL_PREFIX: Claude Code runs this for every shell it starts. A hook
# shell runs under allowlist.sh. A tool call runs through forkshell.sh, so every
# session's main agent and every subagent works on its own view of the project,
# whose real files only forkshell.sh's checkpoint changes. A hook starts these shells, so
# CLAUDE_PID is exported for hooks, which cannot take arguments.
set -euo pipefail
# outermost DIR: the outermost git work tree holding DIR, climbing out of submodules; without one, the nearest
# folder at or above DIR holding .git/saddler, as the hooks make it in a folder without git; empty when neither
outermost() {
    local TOP UP DIR
    if TOP=$(git -C "$1" rev-parse --show-toplevel 2>/dev/null); then
        while UP=$(git -C "$TOP" rev-parse --show-superproject-working-tree 2>/dev/null) && [ -n "$UP" ]; do
            TOP=$UP
        done
        printf '%s' "$TOP"
        return 0
    fi
    DIR=$(readlink -f "$1") || return 0
    while [ -n "$DIR" ] && [ "$DIR" != / ]; do
        if [ -d "$DIR/.git/saddler" ]; then
            printf '%s' "$DIR"
            return 0
        fi
        DIR=${DIR%/*}
    done
    return 0
}
: "${HOME:=$(getent passwd "$UID" | cut -d: -f6)}"
HERE=$(dirname "$(readlink -f "$0")")
export CLAUDE_PID=${CLAUDE_PID:-$PPID}
SESSION=${CLAUDE_CODE_SESSION_ID:-}

# [1] split the tag out of the invocation, naming the agent; the project is the one holding the current folder,
#     a project= an older hook adds is ignored, and a tag with nolock, from a hook older still, is refused
RUN=$1 AGENT='' TAGGED='' PROJ_FOLDER=$(outermost "$PWD")
TAG=$'^([^\n]*)# saddler( agent=([^ \n]*))?( nolock)?( project=([^\n]*))?\n(.*)$'
if [[ $1 =~ $TAG ]]; then
    RUN=${BASH_REMATCH[1]}${BASH_REMATCH[7]}
    AGENT=${BASH_REMATCH[3]}
    TAGGED=1
    if [ -n "${BASH_REMATCH[4]:-}" ]; then
        echo "sandbox.sh: this command's tag comes from an old hook, run migrate.py" >&2
        exit 1
    fi
    if [[ -n $AGENT && ( ! $AGENT =~ ^[A-Za-z0-9_@-][A-Za-z0-9_@.-]*$ || $AGENT == *.lock || $AGENT == *..* ) ]]; then
        echo "sandbox.sh: bad agent name '$AGENT'" >&2
        exit 1
    fi
fi
WRAPPED=''
if [[ ${1%%$'\n'*} == *"eval '"* ]]; then WRAPPED=1; fi

# [2] the session folder in the project's .git; without one, a tagged call is refused, any other runs unsandboxed
STATE_FOLDER=$PROJ_FOLDER/.git/saddler
if [[ ! $SESSION =~ ^[A-Za-z0-9-]+$ ]] || [ -z "$PROJ_FOLDER" ] || [ ! -d "$STATE_FOLDER/session-$SESSION" ]; then
    if [ -n "$TAGGED" ]; then echo "sandbox.sh: no session folder in $STATE_FOLDER, run migrate.py" >&2; exit 1; fi
    exec bash -c -- "$1"
fi

# [3] hook shell
if [ -z "$WRAPPED" ] && [ -z "$AGENT" ]; then
    exec "$HERE/allowlist.sh" "$PROJ_FOLDER" --bind "$PROJ_FOLDER" "$PROJ_FOLDER" --chdir "$PWD" -- bash -c -- "$RUN"
fi

# [4] tool call: forkshell.sh, on the view session-SESSION of the main agent, or session-SESSION-agent-AGENT
#     of the tagged subagent
NAME=session-$SESSION
if [ -n "$AGENT" ]; then NAME=$NAME-agent-$AGENT; fi
exec "$HERE/forkshell.sh" "$NAME" bash -c -- "$RUN"
