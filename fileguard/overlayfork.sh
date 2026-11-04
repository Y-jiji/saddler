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
LOCK_FOLDER=${LOCK_FILE%/*}
starttime() {
    local STAT=''
    { read -r STAT < "/proc/$1/stat"; } 2>/dev/null
    cut -d' ' -f20 <<< "${STAT##*) }"
}
keepignored() {
    IGNORED=()
    if [ ! -s "$LOCK_FOLDER/ignored" ]; then return; fi
    mapfile -d '' -t IGNORED < <(GIT_HELD=1 GIT_INDEX_FILE="$1/index" git --git-dir="$PROJ_FOLDER/.git" --work-tree=. -C "$1/tree" \
        check-ignore -z --stdin < "$LOCK_FOLDER/ignored")
}

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
    LC_ALL=C comm -z -23 \
        <(git --git-dir="$PROJ_FOLDER/.git" ls-tree -r -z "$BASE_COMMIT" | grep -z '^100' | cut -z -f2- | LC_ALL=C sort -z) \
        <(GIT_OPTIONAL_LOCKS=0 git -C "$PROJ_FOLDER" diff -z --no-renames --name-only "$BASE_COMMIT" | LC_ALL=C sort -z) |
        env -C "$PROJ_FOLDER" xargs -0 -r cp --attributes-only --preserve=timestamps --parents -t "$BUILD/tree" -- 2>/dev/null
    keepignored "$BUILD"
    for ENTRY in "${IGNORED[@]}"; do
        if [ "${ENTRY%/}" = "$ENTRY" ]; then printf '%s\0' "$ENTRY"; fi
    done | env -C "$PROJ_FOLDER" xargs -0 -r cp -a --parents -t "$BUILD/tree" -- 2>/dev/null
    if [ -e "$LOCK_FOLDER/generation" ]; then cp "$LOCK_FOLDER/generation" "$BUILD/generation"; fi
    mv -T "$BUILD" "$BASE_FOLDER" 2>/dev/null || rm -rf "$BUILD"
fi
keepignored "$BASE_FOLDER"

# [2] initialize fork folders, start the holder unless one is live
if [ -e "$LOCK_FOLDER/checkpointing" ]; then
    echo "overlayfork.sh: a checkpoint was interrupted, the owner's next command finishes it" >&2
    exit 1
fi
mkdir -p "$FORK_FOLDER/fork" "$FORK_FOLDER/work" || exit 1
exec 195>>"$LOCK_FILE"
flock 195
read -r HOLDER _ _ _ BORN < "$LOCK_FILE"
if [ "${HOLDER:--}" = - ] || [ -z "$BORN" ] || [ "$(starttime "$HOLDER")" != "$BORN" ]; then
    OVERLAYS=()
    for ENTRY in "${IGNORED[@]}"; do
        DIR=${ENTRY%/}
        if [ "$DIR" = "$ENTRY" ] || [ ! -d "$PROJ_FOLDER/$DIR" ]; then continue; fi
        NAME=${DIR//%/%25}
        NAME=${NAME//\//%2F}
        mkdir -p "$FORK_FOLDER/ignored/$NAME/upper" "$FORK_FOLDER/ignored/$NAME/work" || exit 1
        OVERLAYS+=(--overlay-src "$PROJ_FOLDER/$DIR"
                   --overlay "$FORK_FOLDER/ignored/$NAME/upper" "$FORK_FOLDER/ignored/$NAME/work" "$PROJ_FOLDER/$DIR")
    done
    START=$(mktemp -d) || exit 1
    mkfifo "$START/go" || exit 1
    exec 192<>"$START/go"
    setsid "${HOLD[@]}" --unshare-pid --proc /proc \
        --overlay-src "$BASE_FOLDER/tree" \
        --overlay "$FORK_FOLDER/fork" "$FORK_FOLDER/work" "$PROJ_FOLDER" \
        --bind "$PROJ_FOLDER/.git" "$PROJ_FOLDER/.git" \
        "${OVERLAYS[@]}" \
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
    printf '%s %s %s %s %s\n' "$HOLDER" "$BASE_COMMIT" "$BRANCH" "$CLAUDE_PID" "$BORN" > "$LOCK_FILE"
    echo go >&192
    exec 192>&-
    setsid bash -c 'while kill -0 "$0" 2>/dev/null && kill -0 "$1" 2>/dev/null; do sleep 1; done; kill -KILL "$1" 2>/dev/null' \
        "$CLAUDE_PID" "$HOLDER" 195>&- </dev/null >/dev/null 2>&1 &
fi
SEEN=$(cat "$FORK_FOLDER/generation" 2>/dev/null || cat "$BASE_FOLDER/generation" 2>/dev/null)
LATEST=$(cat "$LOCK_FOLDER/generation" 2>/dev/null)
if [ "$SEEN" != "$LATEST" ]; then
    REGULAR=$(mktemp) || exit 1
    git --git-dir="$PROJ_FOLDER/.git" ls-tree -r -z "$BASE_COMMIT" | grep -z '^100' | cut -z -f2- > "$REGULAR"
    LC_ALL=C comm -z -23 \
        <(nsenter -t "$HOLDER" -U -m -p --preserve-credentials -- env -C "$PROJ_FOLDER" \
              xargs -0 -r stat --printf='%.9Y %s %n\0' -- < "$REGULAR" 2>/dev/null | LC_ALL=C sort -z) \
        <(env -C "$PROJ_FOLDER" xargs -0 -r stat --printf='%.9Y %s %n\0' -- < "$REGULAR" 2>/dev/null | LC_ALL=C sort -z) |
        cut -z -d' ' -f3- |
        nsenter -t "$HOLDER" -U -m -p --preserve-credentials -- env -C "$PROJ_FOLDER" \
            xargs -0 -r touch -c -- 2>/dev/null
    rm -f "$REGULAR"
    if ! kill -0 "$HOLDER" 2>/dev/null; then
        echo "overlayfork.sh: a checkpoint preempted this command, run it again" >&2
        exit 1
    fi
    if [ -n "$LATEST" ]; then printf '%s\n' "$LATEST" > "$FORK_FOLDER/generation"; fi
fi
flock -u 195

# [3] execute command in fake workspace + read-only git
CWD=$PWD
REL=${CWD#"$PROJ_FOLDER"}
if [ "$REL" = "$CWD" ] || { [ ! -d "$BASE_FOLDER/tree$REL" ] && [ ! -d "$FORK_FOLDER/fork$REL" ]; }; then CWD=$PROJ_FOLDER; fi
HIDE=()
if [ -d "$PROJ_FOLDER/.git/saddler" ]; then HIDE=(--tmpfs "$PROJ_FOLDER/.git/saddler" --remount-ro "$PROJ_FOLDER/.git/saddler"); fi
rc=0
nsenter -t "$HOLDER" -U -m -p --preserve-credentials -- \
    bwrap   --dev-bind      / / \
            --ro-bind       "$PROJ_FOLDER/.git" "$PROJ_FOLDER/.git" \
            --ro-bind       "$BASE_FOLDER/HEAD" "$PROJ_FOLDER/.git/HEAD" \
            --ro-bind       "$BASE_FOLDER/index" "$PROJ_FOLDER/.git/index" \
            "${HIDE[@]}" \
            --tmpfs         "$HOME/.claude/sandbox" --remount-ro "$HOME/.claude/sandbox" \
            --chdir         "$CWD" \
            --              "$@" 195>&- || rc=$?
if [ "$rc" -ge 128 ]; then
    for i in $(seq 1 100); do if ! kill -0 "$HOLDER" 2>/dev/null; then break; fi; sleep 0.01; done
fi
if [ "$rc" -ne 0 ] && ! kill -0 "$HOLDER" 2>/dev/null; then
    echo "overlayfork.sh: a checkpoint preempted this command, run it again" >&2
    exit "$rc"
fi

# [4] commit changes using fake workspace + real git
flock 195
TMP_INDEX_FILE=$(mktemp -u)
hackygit() {
    nsenter -t "$HOLDER" -U -m -p --preserve-credentials -- \
        env -C "$PROJ_FOLDER" GIT_INDEX_FILE="$TMP_INDEX_FILE" git "$@"
}
EXCLUDES=()
if [ "${#IGNORED[@]}" -gt 0 ]; then
    while IFS= read -r -d '' ENTRY; do EXCLUDES+=(":(exclude,literal)${ENTRY%/}"); done < <(
        LC_ALL=C comm -z -23 <(printf '%s\0' "${IGNORED[@]}" | LC_ALL=C sort -z) \
            <(printf '%s\0' "${IGNORED[@]}" | hackygit check-ignore -z --no-index --stdin | LC_ALL=C sort -z))
fi
FAILED=''
TREE=$(hackygit read-tree "$BASE_COMMIT" && hackygit add -A -- . "${EXCLUDES[@]}" && hackygit write-tree) || FAILED=1
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
