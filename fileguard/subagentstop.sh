#!/bin/bash
# subagentstop.sh, hook JSON on stdin
starttime() {
    local STAT=''
    { read -r STAT < "/proc/$1/stat"; } 2>/dev/null
    cut -d' ' -f20 <<< "${STAT##*) }"
}
defaultbranch() {
    local NAME
    NAME=$(git -C "$PROJ_FOLDER" symbolic-ref -q refs/remotes/origin/HEAD) || NAME=''
    for NAME in "${NAME#refs/remotes/origin/}" main master; do
        if [ -n "$NAME" ] && git -C "$PROJ_FOLDER" rev-parse --verify -q "refs/heads/$NAME" > /dev/null; then
            echo "refs/heads/$NAME"
            return
        fi
    done
    echo HEAD
}

# [1] read event, session, agent; PROJ_FOLDER from $CLAUDE_PROJECT_DIR; LOCK_FOLDER from PROJ_FOLDER
read -r EVENT SESSION AGENT < <(python3 -c '
import json, sys
p = json.load(sys.stdin)
agent = p.get("agent_id") or (p.get("tool_input") or {}).get("task_id") or "-"
print(p.get("hook_event_name"), p.get("session_id"), agent)')
if [[ ! $SESSION =~ ^[A-Za-z0-9-]+$ || ! $AGENT =~ ^[A-Za-z0-9_@-][A-Za-z0-9_@.-]*$ ]]; then exit 0; fi
PROJ_FOLDER=$(git -C "${CLAUDE_PROJECT_DIR:-$PWD}" rev-parse --show-toplevel 2>/dev/null) || exit 0
PROJ_FOLDER=$(readlink -f "$PROJ_FOLDER")
STATE_FOLDER=$HOME/.claude/sandbox/project-$(python3 -c 'import sys, urllib.parse as u; print(u.quote(sys.argv[1], safe=""))' "$PROJ_FOLDER")
LOCK_FOLDER=$STATE_FOLDER/lock
if [ ! -d "$LOCK_FOLDER" ]; then exit 0; fi

# [2] list forks to end
FORKS=()
case $EVENT in
    SubagentStop|PostToolUse) FORKS+=("$LOCK_FOLDER/$SESSION-$AGENT") ;;
    SessionEnd) for f in "$LOCK_FOLDER/$SESSION"-*; do FORKS+=("$f"); done ;;
    SessionStart)
        for f in "$LOCK_FOLDER"/*-*; do
            if [ -f "$f" ] && read -r _ _ _ FORK_CLAUDE _ < "$f" && ! kill -0 "$FORK_CLAUDE" 2>/dev/null; then FORKS+=("$f"); fi
        done ;;
esac

for LOCK_FILE in "${FORKS[@]}"; do
    if [ ! -s "$LOCK_FILE" ]; then continue; fi
    # [3] kill the holder, last commit through sandbox.sh, kill the holder
    read -r HOLDER BASE_COMMIT BRANCH _ BORN < "$LOCK_FILE"
    FORK_SESSION=${BRANCH#saddler/}
    FORK_AGENT=${FORK_SESSION#*/}
    FORK_SESSION=${FORK_SESSION%%/*}
    if [ -n "$BORN" ] && [ "$(starttime "$HOLDER")" = "$BORN" ]; then
        kill -KILL "$HOLDER" 2>/dev/null
        for i in $(seq 1 500); do if ! kill -0 "$HOLDER" 2>/dev/null; then break; fi; sleep 0.01; done
    fi
    CLAUDE_CODE_SESSION_ID=$FORK_SESSION "$CLAUDE_CODE_SHELL_PREFIX" "# saddler agent=$FORK_AGENT nolock"$'\n'"true" || continue
    read -r HOLDER _ _ _ BORN < "$LOCK_FILE"
    if [ -n "$BORN" ] && [ "$(starttime "$HOLDER")" = "$BORN" ]; then
        kill -KILL "$HOLDER" 2>/dev/null
        for i in $(seq 1 500); do if ! kill -0 "$HOLDER" 2>/dev/null; then break; fi; sleep 0.01; done
    fi
    # [4] nothing beyond the default branch: delete the branch
    if git -C "$PROJ_FOLDER" merge-base --is-ancestor "refs/heads/$BRANCH" "$(defaultbranch)"; then
        git -C "$PROJ_FOLDER" update-ref -d "refs/heads/$BRANCH"
    fi
    # [5] delete the fork and its registration; delete its base if no fork uses it
    SESSION_FOLDER=$STATE_FOLDER/session-$FORK_SESSION
    chmod -R u+rwx "$SESSION_FOLDER/agent-$FORK_AGENT" 2>/dev/null
    rm -rf "$SESSION_FOLDER/agent-$FORK_AGENT"
    rm -f "$LOCK_FILE"
    if ! grep -qs " $BASE_COMMIT " "$LOCK_FOLDER/$FORK_SESSION"-*; then rm -rf "$SESSION_FOLDER/commit-$BASE_COMMIT"; fi
done
if [ "$EVENT" = SessionEnd ]; then rm -rf "$STATE_FOLDER/session-$SESSION"; fi
