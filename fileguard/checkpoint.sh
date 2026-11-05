#!/bin/bash
# checkpoint.sh PROJ_FOLDER STATE_FOLDER [LOCK_FILE]
# The only script that changes the real project. Without LOCK_FILE, record the
# first base or finish an interrupted checkpoint. With LOCK_FILE, that agent ran
# git checkpoint: the default branch moves to its tip, its view becomes the real
# project and everyone's base, and every agent starts over from its branch.
PROJ_FOLDER=$1
STATE_FOLDER=$2
LOCK_FILE=${3:-}
HERE=$(dirname "$(readlink -f "$0")")
LOCK_FOLDER=$STATE_FOLDER/lock
MARKER=$LOCK_FOLDER/checkpointing
REQUEST=$LOCK_FOLDER/request
TRASH_FOLDER=$STATE_FOLDER/trash
REAL_GIT=$PROJ_FOLDER/.git
WAIT=${SADDLER_PREEMPT_WAIT:-60}
if [[ ! $WAIT =~ ^[0-9]+$ ]]; then WAIT=60; fi
starttime() {
    local STAT=''
    { read -r STAT < "/proc/$1/stat"; } 2>/dev/null
    cut -d' ' -f20 <<< "${STAT##*) }"
}
defaultbranch() {
    local NAME
    NAME=$(git --git-dir="$REAL_GIT" symbolic-ref -q refs/remotes/origin/HEAD) || NAME=''
    for NAME in "${NAME#refs/remotes/origin/}" main master; do
        if [ -n "$NAME" ] && git --git-dir="$REAL_GIT" rev-parse --verify -q "refs/heads/$NAME" > /dev/null; then
            echo "refs/heads/$NAME"
            return
        fi
    done
    echo HEAD
}
forkfolder() {
    local SESSION=${1#session-}
    echo "$STATE_FOLDER/session-${SESSION%%/*}/agent-${1##*/agent-}"
}
rescue() {
    local INDEX TREE COMMIT NAME
    if [ -z "$(git -C "$PROJ_FOLDER" status --porcelain --untracked-files=no)" ]; then return; fi
    INDEX=$(mktemp -u)
    printf -v NAME 'rescue-%(%Y%m%d-%H%M%S)T' -1
    if GIT_INDEX_FILE=$INDEX git -C "$PROJ_FOLDER" read-tree HEAD &&
       GIT_INDEX_FILE=$INDEX git -C "$PROJ_FOLDER" add -u &&
       TREE=$(GIT_INDEX_FILE=$INDEX git -C "$PROJ_FOLDER" write-tree) &&
       COMMIT=$(git -C "$PROJ_FOLDER" -c user.name=saddler -c user.email=saddler@localhost \
                    commit-tree "$TREE" -p HEAD -m "saddler: changes found in the real project") &&
       git -C "$PROJ_FOLDER" update-ref "refs/heads/$NAME" "$COMMIT"; then
        echo "checkpoint.sh: changes found in $PROJ_FOLDER are on branch $NAME" >&2
    fi
    rm -f "$INDEX"
}
killholders() {
    local FILE HOLDER SEEN BRANCH CLAUDE BORN
    for FILE in "$LOCK_FOLDER"/*-*; do
        if [ ! -f "$FILE" ]; then continue; fi
        exec 193>>"$FILE"
        flock 193
        if read -r HOLDER SEEN BRANCH CLAUDE BORN < "$FILE" && [ "$HOLDER" != - ]; then
            if [ -n "$BORN" ] && [ "$(starttime "$HOLDER")" = "$BORN" ]; then
                kill -KILL "$HOLDER" 2>/dev/null
                for i in $(seq 1 500); do if ! kill -0 "$HOLDER" 2>/dev/null; then break; fi; sleep 0.01; done
            fi
            printf -- '- %s %s %s\n' "$SEEN" "$BRANCH" "$CLAUDE" > "$FILE"
        fi
        exec 193>&-
    done
}

# [1] one checkpoint at a time; only recording the first base waits for another
exec 190>>"$LOCK_FOLDER/checkpoint" || exit 1
if ! flock -n 190; then
    if [ -n "$LOCK_FILE" ] || [ -s "$LOCK_FOLDER/base" ]; then
        if [ -n "$LOCK_FILE" ]; then
            read -r _ _ BRANCH _ < "$LOCK_FILE"
            rm -f "$(forkfolder "$BRANCH")/git/checkpoint"
        fi
        echo "checkpoint.sh: another checkpoint is running, run this again shortly" >&2
        exit 1
    fi
    flock 190
fi

# [2] no base yet: the real project becomes the first, if its tracked files are committed
if [ ! -s "$LOCK_FOLDER/base" ]; then
    if [ -n "$(git -C "$PROJ_FOLDER" status --porcelain --untracked-files=no)" ]; then
        echo "checkpoint.sh: $PROJ_FOLDER has uncommitted changes to tracked files, commit or stash them first" >&2
        exit 1
    fi
    if ! { git --git-dir="$REAL_GIT" config gc.pruneExpire never &&
           git --git-dir="$REAL_GIT" config gc.packRefs false &&
           git --git-dir="$REAL_GIT" rev-parse HEAD > "$LOCK_FOLDER/base.new" &&
           mv -f "$LOCK_FOLDER/base.new" "$LOCK_FOLDER/base"; }; then
        echo "checkpoint.sh: cannot record the base of $PROJ_FOLDER" >&2
        exit 1
    fi
    if [ ! -e "$LOCK_FOLDER/generation" ]; then echo 0 > "$LOCK_FOLDER/generation"; fi
    exit 0
fi

# [3] a request: the agent's view is current, clean and published, and the default branch fast-forwards to it
if [ ! -e "$MARKER" ]; then
    if [ -z "$LOCK_FILE" ]; then exit 0; fi
    read -r HOLDER SEEN BRANCH _ BORN < "$LOCK_FILE"
    FORK_FOLDER=$(forkfolder "$BRANCH")
    WANT=$(cat "$FORK_FOLDER/git/checkpoint" 2>/dev/null)
    rm -f "$FORK_FOLDER/git/checkpoint"
    TIP=$(git --git-dir="$REAL_GIT" rev-parse -q --verify "refs/heads/$BRANCH")
    DEFAULT=$(defaultbranch)
    GENERATION=$(cat "$LOCK_FOLDER/generation" 2>/dev/null)
    GENERATION=${GENERATION:-0}
    REASON=''
    if [ "$SEEN" != "$GENERATION" ]; then
        REASON="another checkpoint ran first"
    elif [ -z "$WANT" ] || [ "$WANT" != "$TIP" ]; then
        REASON="HEAD is not the published tip of $BRANCH"
    elif [ "$DEFAULT" = HEAD ]; then
        REASON="the project has no default branch"
    elif ! git --git-dir="$REAL_GIT" merge-base --is-ancestor "$DEFAULT" "$TIP"; then
        REASON="${DEFAULT#refs/heads/} cannot fast-forward to $BRANCH"
    elif [ -z "$BORN" ] || [ "$(starttime "$HOLDER")" != "$BORN" ]; then
        REASON="the agent's view is gone"
    elif [ -n "$(nsenter -t "$HOLDER" -U -m -p --preserve-credentials -- env -C "$PROJ_FOLDER" git status --porcelain)" ]; then
        REASON="the working tree is not clean"
    fi
    if [ -n "$REASON" ]; then
        echo "checkpoint.sh: no checkpoint, $REASON" >&2
        exit 1
    fi
    printf '%s\n' "$TIP" "$DEFAULT" "$((GENERATION + 1))" "$FORK_FOLDER" > "$REQUEST.new" &&
        mv -f "$REQUEST.new" "$REQUEST" && touch "$MARKER" || exit 1
fi
if [ ! -s "$REQUEST" ]; then
    rm -f "$MARKER"
    exit 0
fi
{ read -r TIP; read -r DEFAULT; read -r NEXT; read -r FORK_FOLDER; } < "$REQUEST"

# [4] stop everyone: new commands fail on the marker, running ones get the wait, then every holder is killed
exec 189<"$LOCK_FOLDER/gate" || exit 1
if ! flock -w "$WAIT" -x 189; then
    killholders
    until flock -w 1 -x 189; do killholders; done
fi
killholders

# [5] changes made straight in the real project go to a rescue branch
rescue

# [6] the default branch moves to the requester's tip, and the requester's upper moves into real
OLD=$(git --git-dir="$REAL_GIT" rev-parse -q --verify "$DEFAULT")
if [ "$OLD" != "$TIP" ] &&
   ! { git --git-dir="$REAL_GIT" merge-base --is-ancestor "$OLD" "$TIP" &&
       git --git-dir="$REAL_GIT" update-ref "$DEFAULT" "$TIP" "$OLD"; }; then
    echo "checkpoint.sh: no checkpoint, ${DEFAULT#refs/heads/} moved" >&2
    rm -f "$REQUEST" "$MARKER"
    exit 1
fi
UPPER=$FORK_FOLDER/fork
if [ -d "$UPPER" ]; then
    rm -rf "$UPPER/.git"
    find "$UPPER" -type c -printf '%P\0' | env -C "$PROJ_FOLDER" xargs -0 -r rm -rf --
    find "$UPPER" -type c -delete
    python3 -c '
import os, sys
for root, folders, files in os.walk(sys.argv[1]):
    for name in folders + files:
        path = os.path.join(root, name)
        marks = [m for m in os.listxattr(path, follow_symlinks=False) if m.startswith("user.overlay.")]
        if name not in folders:
            for mark in marks:
                os.removexattr(path, mark, follow_symlinks=False)
        elif "user.overlay.opaque" in marks:
            sys.stdout.write(os.path.relpath(path, sys.argv[1]) + "\0")' "$UPPER" | env -C "$PROJ_FOLDER" xargs -0 -r rm -rf --
    find "$UPPER" ! -type d -printf '%P\0' | while IFS= read -r -d '' ITEM; do
        if [ -d "$PROJ_FOLDER/$ITEM" ] && [ ! -L "$PROJ_FOLDER/$ITEM" ]; then rm -rf "${PROJ_FOLDER:?}/$ITEM"; fi
    done
    COPY=-alf
    if [ "$(stat -c %d "$UPPER")" != "$(stat -c %d "$PROJ_FOLDER")" ]; then COPY=-af; fi
    if ! cp "$COPY" --no-preserve=xattr "$UPPER/." "$PROJ_FOLDER/"; then
        echo "checkpoint.sh: moving the view into $PROJ_FOLDER failed, the next command finishes it" >&2
        exit 1
    fi
    find "$TRASH_FOLDER" -type d -exec chmod u+rwx {} + 2>/dev/null
    rm -rf "$TRASH_FOLDER"
    mv -T "$UPPER" "$TRASH_FOLDER"
fi
git --git-dir="$REAL_GIT" update-ref --no-deref HEAD "$TIP"
git -C "$PROJ_FOLDER" read-tree "$TIP"
git -C "$PROJ_FOLDER" update-index -q --refresh > /dev/null
if [ -n "$(git -C "$PROJ_FOLDER" status --porcelain --untracked-files=no)" ]; then
    rescue
    git -C "$PROJ_FOLDER" reset -q --hard "$TIP"
fi

# [7] every agent starts over: publish it once more, delete its folder, drop registrations of dead Claude
#     processes and branches the default branch has, then prune what nothing reaches
for FILE in "$LOCK_FOLDER"/*-*; do
    if [ ! -f "$FILE" ]; then continue; fi
    read -r _ _ BRANCH CLAUDE _ < "$FILE"
    AGENT_FOLDER=$(forkfolder "$BRANCH")
    if [ "$AGENT_FOLDER" != "$FORK_FOLDER" ]; then
        "$HERE/overlayfork.sh" "$PROJ_FOLDER" "$FILE" "$CLAUDE"
    fi
    chmod -R u+rwx "$AGENT_FOLDER" 2>/dev/null
    rm -rf "$AGENT_FOLDER"
    if ! kill -0 "$CLAUDE" 2>/dev/null; then rm -f "$FILE"; fi
done
git --git-dir="$REAL_GIT" for-each-ref --format='%(refname)' refs/heads/ | while read -r REF; do
    case $REF in
        refs/heads/session-*/agent-*)
            if git --git-dir="$REAL_GIT" merge-base --is-ancestor "$REF" "$TIP"; then
                git --git-dir="$REAL_GIT" update-ref -d "$REF"
            fi ;;
    esac
done
find "$TRASH_FOLDER" -type d -exec chmod u+rwx {} + 2>/dev/null
rm -rf "$TRASH_FOLDER"
git -C "$PROJ_FOLDER" gc -q --prune=now

# [8] the new base is out: bump the generation, open the gate
printf '%s\n' "$TIP" > "$LOCK_FOLDER/base.new" && mv -f "$LOCK_FOLDER/base.new" "$LOCK_FOLDER/base"
printf '%s\n' "$NEXT" > "$LOCK_FOLDER/generation"
rm -f "$REQUEST" "$MARKER"
echo "checkpoint.sh: ${DEFAULT#refs/heads/} is now $(git --git-dir="$REAL_GIT" rev-parse --short "$TIP"), every agent's base" >&2
