#!/bin/bash
# overlayfork.sh PROJ_FOLDER FORK_FOLDER LOCK_FILE BRANCH CLAUDE_PID [COMMAND...]
# One agent's command on its own view: an overlay of the real project and a
# privatized .git, kept mounted by a holder process, after which the agent's
# branch is published to the real .git. Without a command, only publish.
PROJ_FOLDER=$1
FORK_FOLDER=$2
LOCK_FILE=$3
BRANCH=$4
CLAUDE_PID=$5
shift 5
HERE=$(dirname "$(readlink -f "$0")")
LOCK_FOLDER=${LOCK_FILE%/*}
STATE_FOLDER=${LOCK_FOLDER%/*}
BOX=${STATE_FOLDER%/*}
REAL_GIT=$PROJ_FOLDER/.git
PRIVATE=$FORK_FOLDER/git
GENERATION=$(cat "$LOCK_FOLDER/generation" 2>/dev/null)
GENERATION=${GENERATION:-0}
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
alt() {
    GIT_ALTERNATE_OBJECT_DIRECTORIES=$PRIVATE/objects git --git-dir="$REAL_GIT" "$@"
}
# publish the branch, objects before the ref, unless it drops a commit the default branch has;
# staged objects the real .git now has are deleted
publish() {
    local LATEST TIP OLD DEFAULT DROPS KEEP
    LATEST=$(cat "$LOCK_FOLDER/generation" 2>/dev/null)
    if [ "${LATEST:-0}" = "$GENERATION" ] && [ -e "$PRIVATE/HEAD" ]; then
        flock 195
        TIP=$(git --git-dir="$PRIVATE" rev-parse -q --verify "refs/heads/$BRANCH^{commit}")
        OLD=$(git --git-dir="$REAL_GIT" rev-parse -q --verify "refs/heads/$BRANCH")
        if [ -n "$TIP" ] && [ "$TIP" != "$OLD" ]; then
            DEFAULT=$(defaultbranch)
            DROPS=''
            if [ -n "$OLD" ] && [ "$DEFAULT" != HEAD ]; then
                for KEEP in $(git --git-dir="$REAL_GIT" merge-base --all "$OLD" "$DEFAULT"); do
                    if ! alt merge-base --is-ancestor "$KEEP" "$TIP"; then DROPS=1; fi
                done
            fi
            if [ -n "$DROPS" ]; then
                echo "overlayfork.sh: $BRANCH is not published, it drops commits ${DEFAULT#refs/heads/} has;" \
                     "rebase onto saddler/${DEFAULT#refs/heads/}" >&2
            elif ! ( set -o pipefail
                     alt rev-list --objects "$TIP" --not --all | cut -d' ' -f1 | alt pack-objects --stdout -q |
                         git --git-dir="$REAL_GIT" unpack-objects -q --strict ) ||
                 ! git --git-dir="$REAL_GIT" update-ref "refs/heads/$BRANCH" "$TIP" "$OLD"; then
                echo "overlayfork.sh: publishing $BRANCH failed, the next command retries" >&2
            fi
        fi
        env -C "$PRIVATE/objects" find . -mindepth 2 -maxdepth 2 -regextype posix-extended \
                -regex '\./[0-9a-f]{2}/[0-9a-f]{38,62}' -printf '%P\n' 2>/dev/null | tr -d / |
            git --git-dir="$REAL_GIT" cat-file --batch-check='%(objectname) %(objecttype)' |
            while read -r OID TYPE; do
                if [ "$TYPE" != missing ]; then rm -f "$PRIVATE/objects/${OID:0:2}/${OID:2}"; fi
            done
        flock -u 195
    fi
}
exec 195>>"$LOCK_FILE" || exit 1
if [ $# -eq 0 ]; then publish; exit 0; fi
rc=0

# [1] a checkpoint ran since this agent's view was built: say so once, start over from its branch
flock 195
read -r HOLDER SEEN _ _ BORN < "$LOCK_FILE"
LIVE=''
if [ -n "$BORN" ] && [ "$(starttime "$HOLDER")" = "$BORN" ]; then LIVE=1; fi
if [ "$SEEN" != "$GENERATION" ]; then
    if [ -n "$LIVE" ]; then
        kill -KILL "$HOLDER" 2>/dev/null
        for i in $(seq 1 500); do if ! kill -0 "$HOLDER" 2>/dev/null; then break; fi; sleep 0.01; done
        LIVE=''
    fi
    if [ -n "$SEEN" ]; then
        echo "overlayfork.sh: a checkpoint reset this agent to its branch $BRANCH, uncommitted work is gone" >&2
    fi
    chmod -R u+rwx "$FORK_FOLDER" 2>/dev/null
    rm -rf "$FORK_FOLDER"
    printf -- '- %s %s %s\n' "$GENERATION" "$BRANCH" "$CLAUDE_PID" > "$LOCK_FILE"
fi

# [2] the privatized .git view: own HEAD, index, refs and config, objects staged here and read from real
FRESH=''
if [ ! -e "$PRIVATE/HEAD" ]; then
    TIP=$(git --git-dir="$REAL_GIT" rev-parse -q --verify "refs/heads/$BRANCH^{commit}") || {
        echo "overlayfork.sh: there is no branch $BRANCH" >&2
        exit 1
    }
    DEFAULT=$(defaultbranch)
    mkdir -p "$FORK_FOLDER/fork" "$FORK_FOLDER/work" || exit 1
    ln -sfn "$REAL_GIT" "$STATE_FOLDER/realgit"
    BUILD=$(mktemp -d "$FORK_FOLDER/git.XXXXXX") || exit 1
    if ! { git init -q --template= --object-format="$(git --git-dir="$REAL_GIT" rev-parse --show-object-format)" "$BUILD" &&
           git --git-dir="$BUILD/.git" symbolic-ref HEAD "refs/heads/$BRANCH" &&
           git --git-dir="$BUILD/.git" config include.path "$STATE_FOLDER/realgit/config" &&
           git --git-dir="$BUILD/.git" config gc.auto 0 &&
           git --git-dir="$BUILD/.git" config alias.checkpoint "!$HERE/requestcheckpoint.sh ${DEFAULT#refs/heads/}" &&
           mkdir -p "$BUILD/.git/refs/remotes/saddler" "$BUILD/.git/objects/info" &&
           printf '%s\n' "$STATE_FOLDER/realgit/objects" > "$BUILD/.git/objects/info/alternates" &&
           git --git-dir="$BUILD/.git" update-ref "refs/heads/$BRANCH" "$TIP" &&
           mv -T "$BUILD/.git" "$PRIVATE"; }; then
        rm -rf "$BUILD"
        echo "overlayfork.sh: cannot build the .git view of $BRANCH" >&2
        exit 1
    fi
    rm -rf "$BUILD"
    FRESH=1
fi

# [3] start the holder unless one is live: one overlay of the real project, the .git view, real .git read-only;
#     a new view checks its branch out over the base, writing only files that differ from real
if [ -z "$LIVE" ]; then
    START=$(mktemp -d) || exit 1
    mkfifo "$START/go" || exit 1
    exec 192<>"$START/go"
    setsid "$HERE/allowlist.sh" "$PROJ_FOLDER" "$PROJ_FOLDER" --unshare-pid --proc /proc \
        --overlay-src "$PROJ_FOLDER" --overlay "$FORK_FOLDER/fork" "$FORK_FOLDER/work" "$PROJ_FOLDER" \
        --bind "$PRIVATE" "$PROJ_FOLDER/.git" \
        --ro-bind "$REAL_GIT/refs/heads" "$PROJ_FOLDER/.git/refs/remotes/saddler" \
        --tmpfs "$BOX" --ro-bind "$REAL_GIT" "$STATE_FOLDER/realgit" --remount-ro "$BOX" \
        --ro-bind "$HERE" "$HERE" \
        --info-fd 9 --chdir / -- bash -c 'echo ready >&8; read -r _ <&7 && exec sleep infinity 7<&-' \
        7<"$START/go" 8>"$START/ready" 9>"$START/info" 192>&- 195>&- </dev/null >/dev/null 2>"$START/err" &
    for i in $(seq 1 300); do
        if [ -s "$START/ready" ]; then break; fi
        sleep 0.02
    done
    HOLDER=$(sed -n 's/.*"child-pid": *\([0-9]*\).*/\1/p' "$START/info")
    if [ -z "$HOLDER" ] || [ ! -s "$START/ready" ]; then
        echo "overlayfork.sh: no holder: $(head -c 300 "$START/err")" >&2
        rm -rf "$START"
        exit 1
    fi
    rm -rf "$START"
    BORN=$(starttime "$HOLDER")
    echo go >&192
    exec 192>&-
    if [ -n "$FRESH" ] && ! nsenter -t "$HOLDER" -U -m -p --preserve-credentials -- env -C "$PROJ_FOLDER" \
           bash -c 'git read-tree "$1" && { git update-index -q --refresh > /dev/null; git read-tree -m -u "$1" "$2"; }' \
           _ "$(cat "$LOCK_FOLDER/base")" "$TIP"; then
        kill -KILL "$HOLDER" 2>/dev/null
        chmod -R u+rwx "$FORK_FOLDER" 2>/dev/null
        rm -rf "$FORK_FOLDER"
        echo "overlayfork.sh: cannot check $BRANCH out over the real project" >&2
        exit 1
    fi
    printf '%s %s %s %s %s\n' "$HOLDER" "$GENERATION" "$BRANCH" "$CLAUDE_PID" "$BORN" > "$LOCK_FILE"
    setsid bash -c 'while kill -0 "$0" 2>/dev/null && kill -0 "$1" 2>/dev/null; do sleep 1; done; kill -KILL "$1" 2>/dev/null' \
        "$CLAUDE_PID" "$HOLDER" 195>&- </dev/null >/dev/null 2>&1 &
fi
flock -u 195

# [4] run the command in the holder
CWD=$PWD
if [ ! -d "/proc/$HOLDER/root$CWD" ]; then CWD=$PROJ_FOLDER; fi
nsenter -t "$HOLDER" -U -m -p --preserve-credentials -- env -C "$CWD" "$@" 195>&- || rc=$?
if [ "$rc" -ge 128 ]; then
    for i in $(seq 1 100); do if ! kill -0 "$HOLDER" 2>/dev/null; then break; fi; sleep 0.01; done
fi
if [ "$rc" -ne 0 ] && ! kill -0 "$HOLDER" 2>/dev/null; then
    echo "overlayfork.sh: a checkpoint preempted this command, run it again" >&2
    exit "$rc"
fi

# [5] publish the branch
publish

# [6] log a new largest size of the upper in this generation
if [ -d "$FORK_FOLDER/fork" ]; then
    SIZE=$(du -sb "$FORK_FOLDER/fork" 2>/dev/null | cut -f1)
    LAST=$(grep -F " $GENERATION $FORK_FOLDER/fork " "$STATE_FOLDER/uppersize.log" 2>/dev/null | tail -n 1)
    LAST=${LAST##* }
    if [ -n "$SIZE" ] && [ "$SIZE" -gt "${LAST:-0}" ]; then
        printf '%(%Y-%m-%dT%H:%M:%S)T %s %s %s\n' -1 "$GENERATION" "$FORK_FOLDER/fork" "$SIZE" >> "$STATE_FOLDER/uppersize.log"
    fi
fi
exit "$rc"
