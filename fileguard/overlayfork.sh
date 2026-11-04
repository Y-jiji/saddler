#!/bin/bash
# overlayfork.sh PROJ_FOLDER BASE_COMMIT BASE_FOLDER FORK_FOLDER LOCK_FILE BRANCH CLAUDE_PID HOLD_WRAPPER... -- COMMAND...
PROJ_FOLDER=$1
BASE_COMMIT=$2
BASE_FOLDER=$3
FORK_FOLDER=$4
LOCK_FILE=$5
BRANCH=$6
CLAUDE_PID=$7
shift 7
HOLD=()
while [ "$1" != -- ]; do HOLD+=("$1"); shift; done
shift

# [1] initialize base commit folder
if [ ! -d "$BASE_FOLDER" ]; then
    BUILD=$(mktemp -d "$BASE_FOLDER.XXXXXX") || exit 1
    if ! { mkdir -p "$BUILD/tree" &&
           GIT_INDEX_FILE=$(mktemp -u) git --git-dir="$PROJ_FOLDER/.git" --work-tree="$BUILD/tree" \
               restore --source="$BASE_COMMIT" --worktree -- . &&
           git --git-dir="$PROJ_FOLDER/.git" rev-parse "$BASE_COMMIT^{commit}" > "$BUILD/HEAD" &&
           GIT_INDEX_FILE="$BUILD/index" git --git-dir="$PROJ_FOLDER/.git" read-tree "$BASE_COMMIT"; }; then
        rm -rf "$BUILD"
        echo "overlayfork.sh: cannot build the base at $BASE_COMMIT" >&2
        exit 1
    fi
    mv -T "$BUILD" "$BASE_FOLDER" 2>/dev/null || rm -rf "$BUILD"
fi

# [2] initialize fork folders, start the holder unless one is live
mkdir -p "$FORK_FOLDER/fork" "$FORK_FOLDER/work" || exit 1
exec 195>>"$LOCK_FILE"
flock 195
read -r HOLDER _ < "$LOCK_FILE"
if [ "${HOLDER:--}" = - ] || ! kill -0 "$HOLDER" 2>/dev/null; then
    START=$(mktemp -d) || exit 1
    setsid "${HOLD[@]}" --unshare-pid --proc /proc \
        --overlay-src "$BASE_FOLDER/tree" \
        --overlay "$FORK_FOLDER/fork" "$FORK_FOLDER/work" "$PROJ_FOLDER" \
        --bind "$PROJ_FOLDER/.git" "$PROJ_FOLDER/.git" \
        --info-fd 9 --chdir / -- bash -c 'echo ready >&8; exec sleep infinity' \
        8>"$START/ready" 9>"$START/info" 195>&- </dev/null >/dev/null 2>"$START/err" &
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
    printf '%s %s %s %s\n' "$HOLDER" "$BASE_COMMIT" "$BRANCH" "$CLAUDE_PID" > "$LOCK_FILE"
    setsid bash -c 'while kill -0 "$0" 2>/dev/null && kill -0 "$1" 2>/dev/null; do sleep 1; done; kill -KILL "$1" 2>/dev/null' \
        "$CLAUDE_PID" "$HOLDER" 195>&- </dev/null >/dev/null 2>&1 &
fi
flock -u 195

# [3] execute command in fake workspace + read-only git
CWD=$PWD
REL=${CWD#"$PROJ_FOLDER"}
if [ "$REL" = "$CWD" ] || { [ ! -d "$BASE_FOLDER/tree$REL" ] && [ ! -d "$FORK_FOLDER/fork$REL" ]; }; then CWD=$PROJ_FOLDER; fi
rc=0
nsenter -t "$HOLDER" -U -m -p --preserve-credentials -- \
    bwrap   --dev-bind      / / \
            --ro-bind       "$PROJ_FOLDER/.git" "$PROJ_FOLDER/.git" \
            --ro-bind       "$BASE_FOLDER/HEAD" "$PROJ_FOLDER/.git/HEAD" \
            --ro-bind       "$BASE_FOLDER/index" "$PROJ_FOLDER/.git/index" \
            --tmpfs         "$HOME/.claude/sandbox" --remount-ro "$HOME/.claude/sandbox" \
            --chdir         "$CWD" \
            --              "$@" 195>&- || rc=$?

# [4] commit changes using fake workspace + real git
flock 195
TMP_INDEX_FILE=$(mktemp -u)
hackygit() {
    nsenter -t "$HOLDER" -U -m -p --preserve-credentials -- \
        env -C "$PROJ_FOLDER" GIT_INDEX_FILE="$TMP_INDEX_FILE" git "$@"
}
FAILED=''
TREE=$(hackygit read-tree "$BASE_COMMIT" && hackygit add -A && hackygit write-tree) || FAILED=1
TIP=$(hackygit rev-parse -q --verify "refs/heads/$BRANCH") || TIP=''
if [ -z "$FAILED" ] && { [ -z "$TIP" ] || [ "$TREE" != "$(hackygit rev-parse "$TIP^{tree}")" ]; }; then
    if [ "$TREE" = "$(hackygit rev-parse "$BASE_COMMIT^{tree}")" ]; then
        COMMIT=$BASE_COMMIT
    else
        COMMIT=$(hackygit -c user.name=saddler -c user.email=saddler@localhost commit-tree "$TREE" -p "$BASE_COMMIT" -m "saddler: $BRANCH") || FAILED=1
    fi
    if [ -z "$FAILED" ]; then hackygit update-ref "refs/heads/$BRANCH" "$COMMIT" "$TIP" || FAILED=1; fi
fi
rm -f "$TMP_INDEX_FILE"
flock -u 195
if [ -n "$FAILED" ]; then
    echo "overlayfork.sh: commit failed, retrying on the next call" >&2
    if [ "$rc" -eq 0 ]; then rc=1; fi
fi
exit "$rc"
