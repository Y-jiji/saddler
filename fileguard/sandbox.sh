#!/usr/bin/env bash
# sandbox.sh INVOCATION
# CLAUDE_CODE_SHELL_PREFIX: Claude Code runs this for every shell it starts. A hook
# shell runs under allowlist.sh. A tool call runs through forkshell.sh, so every
# session's main agent and every subagent works on its own view of the project,
# whose real files only checkpoint.sh changes. A hook starts these shells, so
# CLAUDE_PID is exported for hooks, which cannot take arguments.
set -euo pipefail
: "${HOME:=$(getent passwd "$UID" | cut -d: -f6)}"
HERE=$(dirname "$(readlink -f "$0")")
BOX=$HOME/.claude/sandbox
export CLAUDE_PID=${CLAUDE_PID:-$PPID}
SESSION=${CLAUDE_CODE_SESSION_ID:-}

# [1] look up the session folder; without one, run unsandboxed; the old version's gate folder lock/checkpoint/ goes
SESSION_FOLDER=''
if [[ $SESSION =~ ^[A-Za-z0-9-]+$ ]]; then
    for d in "$BOX"/project-*/session-"$SESSION"; do
        if [ -d "$d" ]; then SESSION_FOLDER=$d; fi
    done
fi
if [ -z "$SESSION_FOLDER" ]; then exec bash -c -- "$1"; fi
STATE_FOLDER=${SESSION_FOLDER%/*}
ENCODED=${STATE_FOLDER##*/project-}
PROJ_FOLDER=$(printf '%b' "${ENCODED//%/\\x}")
LOCK_FOLDER=$STATE_FOLDER/lock
mkdir -p "$LOCK_FOLDER"
if [ -d "$LOCK_FOLDER/checkpoint" ]; then rm -rf "$LOCK_FOLDER/checkpoint"; fi
touch "$LOCK_FOLDER/gate" "$LOCK_FOLDER/checkpoint"

# [2] split the tag out of the invocation; an old hook may still add nolock
RUN=$1 AGENT=''
TAG=$'^([^\n]*)# saddler( agent=([^ \n]*))?( nolock)?\n(.*)$'
if [[ $1 =~ $TAG ]]; then
    RUN=${BASH_REMATCH[1]}${BASH_REMATCH[5]}
    AGENT=${BASH_REMATCH[3]}
    if [[ -n $AGENT && ( ! $AGENT =~ ^[A-Za-z0-9_@-][A-Za-z0-9_@.-]*$ || $AGENT == *.lock || $AGENT == *..* ) ]]; then
        echo "sandbox.sh: bad agent name '$AGENT'" >&2
        exit 1
    fi
fi
WRAPPED=''
if [[ ${1%%$'\n'*} == *"eval '"* ]]; then WRAPPED=1; fi

# [3] hook shell
if [ -z "$WRAPPED" ] && [ -z "$AGENT" ]; then
    exec "$HERE/allowlist.sh" "$PROJ_FOLDER" --bind "$PROJ_FOLDER" "$PROJ_FOLDER" \
        --bind "$STATE_FOLDER" "$STATE_FOLDER" --chdir "$PWD" -- bash -c -- "$RUN"
fi

# [4] tool call: forkshell.sh, on the view of the tagged subagent, or master
export CLAUDE_AGENT=${AGENT:-master} CLAUDE_PROJECT_DIR=$PROJ_FOLDER
exec "$HERE/forkshell.sh" bash -c -- "$RUN"
