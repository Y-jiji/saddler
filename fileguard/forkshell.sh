#!/usr/bin/env bash
# forkshell.sh SESSION[/AGENT] [COMMAND...]
# SESSION[/AGENT] may also be the branch name session-SESSION[/agent-AGENT]
# COMMAND, or an interactive bash, on one agent's own view of the project, named by
#   SESSION                 the session; one starting with human- gets a person's view
#   AGENT                   the agent, default master
# and by the environment
#   CLAUDE_PROJECT_DIR      the project, default the git project of PWD
#   CLAUDE_PID              the Claude process, default the parent
# sandbox.sh runs every tool call through it. The agent's branch is published when
# the command ends. The interactive bash also sources this file as its init file.
if [ "${BASH_SOURCE[0]}" != "$0" ]; then
    if [ -f ~/.bashrc ]; then . ~/.bashrc; fi
    PS1="(fork ${CLAUDE_CODE_SESSION_ID:-}/${CLAUDE_AGENT:-master}) ${PS1:-\$ }"
    return
fi
set -euo pipefail
HERE=$(dirname "$(readlink -f "$0")")
export CLAUDE_PID=${CLAUDE_PID:-$PPID}
SPEC=${1:-}
SESSION=${SPEC%%/*} AGENT=master
if [[ $SPEC == */* ]]; then AGENT=${SPEC#*/}; fi
SESSION=${SESSION#session-}
AGENT=${AGENT#agent-}
PROJ_FOLDER=${CLAUDE_PROJECT_DIR:-$(readlink -f "$(git rev-parse --show-toplevel 2>/dev/null)" || true)}
STATE_FOLDER=$PROJ_FOLDER/.git/saddler
SESSION_FOLDER=$STATE_FOLDER/session-$SESSION
FORK_FOLDER=$SESSION_FOLDER/agent-$AGENT
LOCK_FOLDER=$STATE_FOLDER/lock
LOCK_FILE=$LOCK_FOLDER/$SESSION-$AGENT
BRANCH=session-$SESSION/agent-$AGENT
RUN=("${@:2}")
if [ $# -le 1 ]; then RUN=(bash --init-file "$HERE/forkshell.sh" -i); fi

# [1] refuse a bad session id, agent name or project; make the session and lock folders
if [[ ! $SESSION =~ ^[A-Za-z0-9-]+$ ]]; then
    echo "usage: forkshell.sh SESSION[/AGENT] [COMMAND...], or session-SESSION[/agent-AGENT] for SESSION[/AGENT]," \
        "SESSION being letters, digits and dashes" >&2
    exit 1
fi
if [[ ! $AGENT =~ ^[A-Za-z0-9_@-][A-Za-z0-9_@.-]*$ || $AGENT == *.lock || $AGENT == *..* ]]; then
    echo "forkshell.sh: bad agent name '$AGENT'" >&2
    exit 1
fi
if [ -z "$PROJ_FOLDER" ]; then echo "forkshell.sh: $PWD is not in a git project" >&2; exit 1; fi
export CLAUDE_CODE_SESSION_ID=$SESSION CLAUDE_AGENT=$AGENT
mkdir -p "$SESSION_FOLDER" "$LOCK_FOLDER"
touch "$LOCK_FOLDER/gate" "$LOCK_FOLDER/checkpoint"

# [2] a project without a commit has nothing to view: a person's command runs unsandboxed, an agent's under allowlist.sh
if ! git -C "$PROJ_FOLDER" rev-parse --verify -q HEAD > /dev/null 2>&1; then
    if [[ $SESSION == human-* ]]; then exec "${RUN[@]}"; fi
    exec "$HERE/allowlist.sh" "$PROJ_FOLDER" --bind "$PROJ_FOLDER" "$PROJ_FOLDER" \
        --chdir "$PWD" -- "${RUN[@]}"
fi

# [3] a checkpoint is in progress: finish it if nobody runs it, otherwise fail now
if [ -e "$LOCK_FOLDER/checkpointing" ]; then
    "$HERE/checkpoint.sh" "$PROJ_FOLDER" || true
    if [ -e "$LOCK_FOLDER/checkpointing" ]; then
        echo "forkshell.sh: a checkpoint is running, run this again shortly" >&2
        exit 1
    fi
fi

# [4] no base yet: the real project becomes the first one
if [ ! -s "$LOCK_FOLDER/base" ]; then "$HERE/checkpoint.sh" "$PROJ_FOLDER"; fi

# [5] the agent's branch, from the base if missing, and its registration
if ! git -C "$PROJ_FOLDER" rev-parse --verify -q "refs/heads/$BRANCH" > /dev/null; then
    git -C "$PROJ_FOLDER" update-ref "refs/heads/$BRANCH" "$(cat "$LOCK_FOLDER/base")" "" 2> /dev/null || true
fi
REGISTERED=''
if [ -s "$LOCK_FILE" ]; then read -r _ _ REGISTERED _ < "$LOCK_FILE"; fi
if [ "$REGISTERED" != "$BRANCH" ]; then
    GENERATION=$(cat "$LOCK_FOLDER/generation" 2> /dev/null || true)
    printf -- '- %s %s %s\n' "${GENERATION:-0}" "$BRANCH" "$CLAUDE_PID" > "$LOCK_FILE"
fi

# [6] run behind the gate: shared while the command runs, never inherited by it
exec 189<"$LOCK_FOLDER/gate"
if ! flock -n -s 189; then
    echo "forkshell.sh: a checkpoint is running, run this again shortly" >&2
    exit 1
fi
rc=0
"$HERE/overlayfork.sh" "$PROJ_FOLDER" "$LOCK_FILE" "$CLAUDE_PID" "${RUN[@]}" 189<&- || rc=$?
exec 189<&-

# [7] the command ran git checkpoint
if [ -e "$FORK_FOLDER/git/checkpoint" ]; then
    "$HERE/checkpoint.sh" "$PROJ_FOLDER" "$LOCK_FILE" || if [ "$rc" -eq 0 ]; then rc=1; fi
fi
exit "$rc"
