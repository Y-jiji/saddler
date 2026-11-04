#!/bin/bash

PROJ_FOLDER=$1
BASE_COMMIT=$2
BASE_FOLDER=$3
FORK_FOLDER=$4
BRANCH=$5
shift 5

# [1] initialize base commit folder
if [ ! -d $BASE_FOLDER ]; then
    git init -q --template= "$BASE_FOLDER"
    echo "$PROJ_FOLDER/.git/objects" > "$BASE_FOLDER/.git/objects/info/alternates"
    git -C "$BASE_FOLDER" checkout -q --detach $BASE_COMMIT
    echo "$BASE_FOLDER.objects" > "$BASE_FOLDER/.git/objects/info/alternates"
    mkdir -p "$BASE_FOLDER.objects"
fi

# [2] initialize fork folders if not exist
[ ! -d $FORK_FOLDER/work ]   && mkdir -p "$FORK_FOLDER/work"
[ ! -d $FORK_FOLDER/commit ] && mkdir -p "$FORK_FOLDER/commit"

# [3] execute command in fake workspace + fake git
bwrap   --dev-bind      / / \
        --ro-bind       "$PROJ_FOLDER/.git/objects" "$BASE_FOLDER.objects" \
        --overlay-src   "$BASE_FOLDER" \
        --overlay       "$FORK_FOLDER/commit" "$FORK_FOLDER/work" "$PROJ_FOLDER" \
        --chdir         "$PROJ_FOLDER" \
        --              "$@"

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
