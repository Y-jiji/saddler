#!/usr/bin/env bash
# sandbox.sh INVOCATION
# CLAUDE_CODE_SHELL_PREFIX: Claude Code runs this for every shell it starts. Only
# this script combines allowlist.sh, gitlock.sh, gitwrap.sh, overlayfork.sh and
# overlayowner.sh. The first session to run a command owns the project and works
# on the real tracked files; every other session and every subagent works on a
# fork. A hook starts these shells, so CLAUDE_PID is exported for hooks, which
# cannot take arguments.
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
mkdir -p "$LOCK_FOLDER/checkpoint"
touch "$LOCK_FOLDER/queue" "$LOCK_FOLDER/mode" "$LOCK_FOLDER/checkpoint/queue" "$LOCK_FOLDER/checkpoint/mode" \
    "$LOCK_FOLDER/ownercmd" "$LOCK_FOLDER/ownerholder"

# [2] split the tag out of the invocation
RUN=$1 AGENT='' NOLOCK=''
TAG=$'^([^\n]*)# saddler( agent=([^ \n]*))?( nolock)?\n(.*)$'
if [[ $1 =~ $TAG ]]; then
    RUN=${BASH_REMATCH[1]}${BASH_REMATCH[5]}
    AGENT=${BASH_REMATCH[3]}
    NOLOCK=${BASH_REMATCH[4]}
    if [[ -n $AGENT && ! $AGENT =~ ^[A-Za-z0-9_@-][A-Za-z0-9_@.-]*$ ]]; then
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

# [4] tool call, session has a fork: stay on it
# [5] tool call: claim the project; another owner makes this session a fork
OWNER=''
if [ -n "$WRAPPED" ] && [ -z "$AGENT" ] && [ -e "$LOCK_FOLDER/$SESSION-master" ]; then
    AGENT=master
elif [ -n "$WRAPPED" ]; then
    exec 198>>"$LOCK_FOLDER/owner"
    if flock -n 198; then
        printf '%s %s\n' "$CLAUDE_PID" "$SESSION" > "$LOCK_FOLDER/owner.info"
        ( cd /; setsid tail --pid="$CLAUDE_PID" -f /dev/null > /dev/null 2>&1 < /dev/null & )
    else
        read -r HOLDER OWNER < "$LOCK_FOLDER/owner.info" || true
        if [ "$HOLDER" = "$CLAUDE_PID" ]; then OWNER=''; fi
        if [ -n "$OWNER" ] && [ -z "$AGENT" ]; then AGENT=master; fi
    fi
    exec 198>&-
fi

# [6] owner
if [ -z "$AGENT" ]; then
    GIT=$(readlink -f "$(command -v git)")
    REAL_GIT=$GIT
    if [ -e /.realgit ]; then REAL_GIT=/.realgit; fi
    printf -v GIT_WRAPPER '%q ' "$HERE/gitlock.sh" "$LOCK_FOLDER" write 100 /.realgit
    if [ -d "$PROJ_FOLDER/.git" ]; then
        exec "$HERE/overlayowner.sh" "$PROJ_FOLDER" "$LOCK_FOLDER" "$CLAUDE_PID" "$GIT_WRAPPER" \
            "$HERE/allowlist.sh" "$PROJ_FOLDER" "$PROJ_FOLDER" --bind "$PROJ_FOLDER" "$PROJ_FOLDER" \
            --ro-bind "$REAL_GIT" /.realgit --ro-bind "$HERE/gitwrap.sh" "$GIT" -- bash -c -- "$RUN"
    fi
    exec "$HERE/allowlist.sh" "$PROJ_FOLDER" "$PROJ_FOLDER" --bind "$PROJ_FOLDER" "$PROJ_FOLDER" \
        --ro-bind "$REAL_GIT" /.realgit --ro-bind "$HERE/gitwrap.sh" "$GIT" --setenv GIT_WRAPPER "$GIT_WRAPPER" \
        --chdir "$PWD" -- bash -c -- "$RUN"
fi

# [7] fork, first call: take HEAD as base, make the branch, register
LOCK_FILE=$LOCK_FOLDER/$SESSION-$AGENT
BRANCH=saddler/$SESSION/$AGENT
if [ ! -s "$LOCK_FILE" ]; then
    BASE_COMMIT=$(git -C "$PROJ_FOLDER" rev-parse --verify -q HEAD) || {
        echo "sandbox.sh: session ${OWNER:-another} owns $PROJ_FOLDER, and it has no commit to fork from" >&2
        exit 1
    }
    git -C "$PROJ_FOLDER" update-ref "refs/heads/$BRANCH" "$BASE_COMMIT" ""
    printf -- '- %s %s %s\n' "$BASE_COMMIT" "$BRANCH" "$CLAUDE_PID" > "$LOCK_FILE"
fi
read -r _ BASE_COMMIT _ _ < "$LOCK_FILE"
BASE_FOLDER=$SESSION_FOLDER/commit-$BASE_COMMIT
FORK_FOLDER=$SESSION_FOLDER/agent-$AGENT

# [8] fork, waiting out a running checkpoint
WAIT=${SADDLER_PREEMPT_WAIT:-60}
if [[ ! $WAIT =~ ^[0-9]+$ ]]; then WAIT=60; fi
GATE=("$HERE/gitlock.sh" "$LOCK_FOLDER/checkpoint" read $((WAIT + 100)))
if [ -n "$NOLOCK" ]; then
    exec "${GATE[@]}" "$HERE/overlayfork.sh" "$PROJ_FOLDER" "$BASE_COMMIT" "$BASE_FOLDER" "$FORK_FOLDER" "$LOCK_FILE" "$BRANCH" "$CLAUDE_PID" \
        "$HERE/allowlist.sh" "$PROJ_FOLDER" "$BASE_FOLDER/tree" -- bash -c -- "$RUN"
fi
exec "${GATE[@]}" "$HERE/gitlock.sh" "$LOCK_FOLDER" read 100 \
    "$HERE/overlayfork.sh" "$PROJ_FOLDER" "$BASE_COMMIT" "$BASE_FOLDER" "$FORK_FOLDER" "$LOCK_FILE" "$BRANCH" "$CLAUDE_PID" \
    "$HERE/allowlist.sh" "$PROJ_FOLDER" "$BASE_FOLDER/tree" -- bash -c -- "$RUN"
