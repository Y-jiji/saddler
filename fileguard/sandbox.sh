#!/usr/bin/env bash
# sandbox.sh INVOCATION
# CLAUDE_CODE_SHELL_PREFIX: Claude Code runs this for every shell it starts. Only
# this script combines allowlist.sh, overlayfork.sh and checkpoint.sh. Every
# session's main agent and every subagent works on its own view of the project,
# whose real files only checkpoint.sh changes. A hook starts these shells, so
# CLAUDE_PID is exported for hooks, which cannot take arguments.
set -euo pipefail
: "${HOME:=$(getent passwd "$UID" | cut -d: -f6)}"
HERE=$(dirname "$(readlink -f "$0")")
BOX=$HOME/.claude/sandbox
export CLAUDE_PID=${CLAUDE_PID:-$PPID}
SESSION=${CLAUDE_CODE_SESSION_ID:-}

# [1] look up the session folder; without one, run unsandboxed
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
    exec "$HERE/allowlist.sh" "$PROJ_FOLDER" "$PROJ_FOLDER" --bind "$PROJ_FOLDER" "$PROJ_FOLDER" \
        --bind "$STATE_FOLDER" "$STATE_FOLDER" --chdir "$PWD" -- bash -c -- "$RUN"
fi

# [4] tool call: the tagged subagent, or master; a project without a commit has nothing to view
if [ -z "$AGENT" ]; then AGENT=master; fi
if ! git -C "$PROJ_FOLDER" rev-parse --verify -q HEAD > /dev/null 2>&1; then
    exec "$HERE/allowlist.sh" "$PROJ_FOLDER" "$PROJ_FOLDER" --bind "$PROJ_FOLDER" "$PROJ_FOLDER" \
        --chdir "$PWD" -- bash -c -- "$RUN"
fi

# [5] a checkpoint is in progress: finish it if nobody runs it, otherwise fail now
if [ -e "$LOCK_FOLDER/checkpointing" ]; then
    "$HERE/checkpoint.sh" "$PROJ_FOLDER" "$STATE_FOLDER" || true
    if [ -e "$LOCK_FOLDER/checkpointing" ]; then
        echo "sandbox.sh: a checkpoint is running, run this again shortly" >&2
        exit 1
    fi
fi

# [6] no base yet: the real project becomes the first one
if [ ! -s "$LOCK_FOLDER/base" ]; then "$HERE/checkpoint.sh" "$PROJ_FOLDER" "$STATE_FOLDER"; fi

# [7] the agent's branch, from the base if missing, and its registration
LOCK_FILE=$LOCK_FOLDER/$SESSION-$AGENT
BRANCH=session-$SESSION/agent-$AGENT
FORK_FOLDER=$SESSION_FOLDER/agent-$AGENT
if ! git -C "$PROJ_FOLDER" rev-parse --verify -q "refs/heads/$BRANCH" > /dev/null; then
    git -C "$PROJ_FOLDER" update-ref "refs/heads/$BRANCH" "$(cat "$LOCK_FOLDER/base")" "" 2> /dev/null || true
fi
if [ ! -s "$LOCK_FILE" ]; then
    GENERATION=$(cat "$LOCK_FOLDER/generation" 2> /dev/null || true)
    printf -- '- %s %s %s\n' "${GENERATION:-0}" "$BRANCH" "$CLAUDE_PID" > "$LOCK_FILE"
fi

# [8] run behind the gate: shared while the command runs, never inherited by it
exec 189<"$LOCK_FOLDER/gate"
if ! flock -n -s 189; then
    echo "sandbox.sh: a checkpoint is running, run this again shortly" >&2
    exit 1
fi
rc=0
"$HERE/overlayfork.sh" "$PROJ_FOLDER" "$FORK_FOLDER" "$LOCK_FILE" "$BRANCH" "$CLAUDE_PID" \
    bash -c -- "$RUN" 189<&- || rc=$?
exec 189<&-

# [9] the command ran git checkpoint
if [ -e "$FORK_FOLDER/git/checkpoint" ]; then
    "$HERE/checkpoint.sh" "$PROJ_FOLDER" "$STATE_FOLDER" "$LOCK_FILE" || if [ "$rc" -eq 0 ]; then rc=1; fi
fi
exit "$rc"
