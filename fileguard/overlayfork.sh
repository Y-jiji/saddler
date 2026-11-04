#!/bin/bash

PROJ_FOLDER=$1
BASE_COMMIT=$2
BASE_FOLDER=$3
FORK_FOLDER=$4
BRANCH=$5
shift 5

# [1] initialize base commit folder
if [ ! -d $BASE_FOLDER ]; then
    mkdir -p "$BASE_FOLDER"
    GIT_INDEX_FILE=$(mktemp -u) \
    git --git-dir="$PROJ_FOLDER/.git" \
        --work-tree="$BASE_FOLDER" \
        restore --source=$BASE_COMMIT --worktree -- .
    git --git-dir="$PROJ_FOLDER/.git" rev-parse "$BASE_COMMIT^{commit}" > "$BASE_FOLDER.HEAD"
    GIT_INDEX_FILE="$BASE_FOLDER.index" \
    git --git-dir="$PROJ_FOLDER/.git" read-tree $BASE_COMMIT
fi

# [2] initialize fork folders if not exist
[ ! -d $FORK_FOLDER/work ]   && mkdir -p "$FORK_FOLDER/work"
[ ! -d $FORK_FOLDER/commit ] && mkdir -p "$FORK_FOLDER/commit"

# [3a] lock git into current snapshot
# ...

# [3b] execute command in fake workspace + read-only git
bwrap   --dev-bind      / / \
        --overlay-src   "$BASE_FOLDER" \
        --overlay       "$FORK_FOLDER/commit" "$FORK_FOLDER/work" "$PROJ_FOLDER" \
        --ro-bind       "$PROJ_FOLDER/.git" "$PROJ_FOLDER/.git" \
        --ro-bind       "$BASE_FOLDER.HEAD" "$PROJ_FOLDER/.git/HEAD" \
        --ro-bind       "$BASE_FOLDER.index" "$PROJ_FOLDER/.git/index" \
        --chdir         "$PROJ_FOLDER" \
        --              "$@"

# [3c] unlock git from current snapshot
# ...

# [4] commit changes using fake workspace + real git
TMP_INDEX_FILE=$(mktemp -u)
hackygit() {
    bwrap   --dev-bind      / / \
            --overlay-src   "$BASE_FOLDER" \
            --overlay       "$FORK_FOLDER/commit" "$FORK_FOLDER/work" "$PROJ_FOLDER" \
            --bind          "$PROJ_FOLDER/.git" "$PROJ_FOLDER/.git" \
            --chdir         "$PROJ_FOLDER" \
            --setenv        GIT_INDEX_FILE "$TMP_INDEX_FILE" \
            --              git "$@"
}
TREE=$(hackygit read-tree $BASE_COMMIT && hackygit add -A && hackygit write-tree)
COMMIT=$(hackygit commit-tree $TREE -p $BASE_COMMIT -m "saddler: $BRANCH")
hackygit update-ref refs/heads/$BRANCH $COMMIT
rm -f $TMP_INDEX_FILE
