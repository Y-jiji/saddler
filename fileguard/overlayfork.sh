#!/bin/bash

PROJ_FOLDER=$1
BASE_COMMIT=$2
BASE_FOLDER=$3
FORK_FOLDER=$4
BRANCH=$5
shift 5
COMMAND=$@

# [1] initialize base commit folder
if [ ! -d $BASE_FOLDER ]; then
    mkdir -p "$BASE_FOLDER"
    git --git-dir="$PROJ_FOLDER/.git" \
        --work-tree="$BASE_FOLDER" \
        checkout -f $BASE_COMMIT
fi

# [2] initialize fork folders if not exist
[ ! -d $FORK_FOLDER/work ]   && mkdir -p "$FORK_FOLDER/work"
[ ! -d $FORK_FOLDER/commit ] && mkdir -p "$FORK_FOLDER/commit"

# [3] execute command in fake workspace + fake git
bwrap   --overlay-src   $PROJ_FOLDER/.git \
        --overlay-src   $BASE_FOLDER \
        --overlay       $FORK_FOLDER/commit $FORK_FOLDER/work $PROJ_FOLDER \
        --dev-bind      / / \
        --              $COMMAND

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
TREE=$(hackygit add -A -f && hackygit write-tree)
COMMIT=$(hackygit commit-tree $TREE -p $BASE_COMMIT -m "saddler: $BRANCH")
hackygit update-ref refs/heads/$BRANCH $COMMIT
rm -f $TMP_INDEX_FILE
