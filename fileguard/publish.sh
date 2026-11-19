#!/bin/bash
# publish.sh NAME
# The branches of the view NAME, from its privatized .git to the real repositories of the project holding the current
# folder: each submodule's branch, deepest first, making the real git folder of a submodule the agent added,
# then the project's. Nothing when the agent's view is not from the current generation. It takes the agent's
# registration lock itself, so a caller must not hold it.
# outermost DIR: the outermost git work tree holding DIR, climbing out of submodules; without one, the nearest
# folder at or above DIR holding .git/saddler, as the hooks make it in a folder without git; empty when neither
outermost() {
    local TOP UP DIR
    if TOP=$(git -C "$1" rev-parse --show-toplevel 2>/dev/null); then
        while UP=$(git -C "$TOP" rev-parse --show-superproject-working-tree 2>/dev/null) && [ -n "$UP" ]; do
            TOP=$UP
        done
        printf '%s' "$TOP"
        return 0
    fi
    DIR=$(readlink -f "$1") || return 0
    while [ -n "$DIR" ] && [ "$DIR" != / ]; do
        if [ -d "$DIR/.git/saddler" ]; then
            printf '%s' "$DIR"
            return 0
        fi
        DIR=${DIR%/*}
    done
    return 0
}
# gitdir DIR ARGS...: git on a git folder from outside the view, where a submodule's work tree path leads nowhere
gitdir() {
    git -C / --git-dir="$1" --work-tree=/ "${@:2}"
}
defaultbranch() {
    local NAME
    NAME=$(gitdir "$REAL_GIT" symbolic-ref -q refs/remotes/origin/HEAD) || NAME=''
    for NAME in "${NAME#refs/remotes/origin/}" main master; do
        if [ -n "$NAME" ] && gitdir "$REAL_GIT" rev-parse --verify -q "refs/heads/$NAME" > /dev/null; then
            echo "refs/heads/$NAME"
            return
        fi
    done
    echo HEAD
}
# modules DIR PREFIX: the submodule git folders below DIR, nested ones included, parents first, as PREFIX<name>
modules() {
    local ENTRY
    for ENTRY in "$1"/*/; do
        ENTRY=${ENTRY%/}
        if [ -f "$ENTRY/HEAD" ] && [ -d "$ENTRY/objects" ]; then
            echo "$2${ENTRY##*/}"
            modules "$ENTRY/modules" "$2${ENTRY##*/}/modules/"
        elif [ -d "$ENTRY" ]; then
            modules "$ENTRY" "$2${ENTRY##*/}/"
        fi
    done
}
# survey GITDIR: fill MODULES, WORKTREE and TIPS for the submodules below GITDIR, the real .git or the private one;
# a submodule's tip is its BRANCH, else the commit its parent's tip points to
survey() {
    local M PARENT PARENTGIT TIP REL
    mapfile -t MODULES < <(modules "$1/modules" modules/)
    WORKTREE[.]=$PROJ_FOLDER
    TIPS[.]=$(gitdir "$1" rev-parse -q --verify "refs/heads/$BRANCH^{commit}" 2>/dev/null)
    for M in "${MODULES[@]}"; do
        REL=$(gitdir "$1/$M" config core.worktree 2>/dev/null) || continue
        WORKTREE[$M]=$(realpath -m "$REAL_GIT/$M/$REL")
        MODULEOF[${WORKTREE[$M]}]=$M
        PARENT=. PARENTGIT=$1
        if [[ $M == */modules/* ]]; then PARENT=${M%/modules/*} PARENTGIT=$1/${M%/modules/*}; fi
        TIP=$(gitdir "$1/$M" rev-parse -q --verify "refs/heads/$BRANCH^{commit}" 2>/dev/null) || TIP=''
        if [ -z "$TIP" ] && [ -n "${TIPS[$PARENT]:-}" ]; then
            REL=${WORKTREE[$M]#"${WORKTREE[$PARENT]}"/}
            TIP=$(gitdir "$PARENTGIT" ls-tree "${TIPS[$PARENT]}" -- "$REL" 2>/dev/null | awk '$1 == "160000" { print $3 }')
        fi
        TIPS[$M]=$TIP
    done
}
# newmodule M: a real git folder for a submodule the agent added, taking from the agent only its work tree and origin
newmodule() {
    local OWN=$PRIVATE/$1 REL URL
    REL=$(gitdir "$OWN" config core.worktree) || return 1
    case $(realpath -m "$REAL_GIT/$1/$REL") in "$PROJ_FOLDER"/*) ;; *) return 1 ;; esac
    URL=$(gitdir "$OWN" config remote.origin.url) || URL=''
    git init -q --bare --template= --object-format="$(gitdir "$OWN" rev-parse --show-object-format)" "$REAL_GIT/$1" &&
        gitdir "$REAL_GIT/$1" config core.bare false &&
        gitdir "$REAL_GIT/$1" config core.worktree "$REL" &&
        gitdir "$REAL_GIT/$1" config gc.pruneExpire never &&
        gitdir "$REAL_GIT/$1" config gc.packRefs false &&
        { [ -z "$URL" ] || gitdir "$REAL_GIT/$1" config remote.origin.url "$URL"; }
}
# publish REAL OWN TIP WORKTREE BASE [DEFAULT]: BRANCH of one repository moves to TIP, objects before the ref.
# Refused when it drops a commit DEFAULT has, or when a submodule pointer changed since BASE names a commit
# the real submodule lacks. Staged objects the real repository has are deleted, when OWN reads through to it.
publish() {
    local REAL=$1 OWN=$2 TIP=$3 WT=$4 BASE=$5 DEFAULT=${6:-} OLD KEEP LINE META SUB REASON=''
    local -A BEFORE=()
    OLD=$(gitdir "$REAL" rev-parse -q --verify "refs/heads/$BRANCH")
    if [ -n "$TIP" ] && [ "$TIP" != "$OLD" ]; then
        if [ -n "$DEFAULT" ] && [ -n "$OLD" ] && [ "$DEFAULT" != HEAD ]; then
            for KEEP in $(gitdir "$REAL" merge-base --all "$OLD" "$DEFAULT"); do
                if ! GIT_ALTERNATE_OBJECT_DIRECTORIES=$OWN/objects gitdir "$REAL" merge-base --is-ancestor "$KEEP" "$TIP"; then
                    REASON="it drops commits ${DEFAULT#refs/heads/} has; rebase onto saddler/${DEFAULT#refs/heads/}"
                fi
            done
        fi
        while IFS= read -r -d '' LINE; do
            META=${LINE%%$'\t'*}
            if [ "${META%% *}" = 160000 ]; then BEFORE[${LINE#*$'\t'}]=${META##* }; fi
        done < <(gitdir "$REAL" ls-tree -r -z "${OLD:-$BASE}" 2>/dev/null)
        while IFS= read -r -d '' LINE; do
            META=${LINE%%$'\t'*}
            if [ "${META%% *}" != 160000 ] || [ "${BEFORE[${LINE#*$'\t'}]:-}" = "${META##* }" ]; then continue; fi
            SUB=${MODULEOF[$(realpath -m "$WT/${LINE#*$'\t'}")]:-}
            if [ -n "$SUB" ] && ! gitdir "$REAL_GIT/$SUB" cat-file -e "${META##* }^{commit}" 2>/dev/null; then
                REASON="its pointer ${LINE#*$'\t'} names ${META##* }, which the real submodule lacks; commit it on $BRANCH there"
            fi
        done < <(GIT_ALTERNATE_OBJECT_DIRECTORIES=$OWN/objects gitdir "$REAL" ls-tree -r -z "$TIP" 2>/dev/null)
        if [ -n "$REASON" ]; then
            echo "publish.sh: $BRANCH is not published in ${WT#"$PROJ_FOLDER"/}, $REASON" >&2
        elif ! ( set -o pipefail
                 GIT_ALTERNATE_OBJECT_DIRECTORIES=$OWN/objects gitdir "$REAL" rev-list --objects "$TIP" --not --all |
                     cut -d' ' -f1 |
                     GIT_ALTERNATE_OBJECT_DIRECTORIES=$OWN/objects gitdir "$REAL" pack-objects --stdout -q |
                     gitdir "$REAL" unpack-objects -q --strict ) ||
             ! gitdir "$REAL" update-ref "refs/heads/$BRANCH" "$TIP" "$OLD"; then
            echo "publish.sh: publishing $BRANCH in ${WT#"$PROJ_FOLDER"/} failed, the next command retries" >&2
        fi
    fi
    if ! grep -qsF "$REAL_GIT/alt" "$OWN/objects/info/alternates"; then return; fi
    env -C "$OWN/objects" find . -mindepth 2 -maxdepth 2 -regextype posix-extended \
            -regex '\./[0-9a-f]{2}/[0-9a-f]{38,62}' -printf '%P\n' 2>/dev/null | tr -d / |
        gitdir "$REAL" cat-file --batch-check='%(objectname) %(objecttype)' |
        while read -r OID TYPE; do
            if [ "$TYPE" != missing ]; then rm -f "$OWN/objects/${OID:0:2}/${OID:2}"; fi
        done
}
BRANCH=${1:-}
PROJ_FOLDER=$(outermost "$PWD")
REAL_GIT=$PROJ_FOLDER/.git
STATE_FOLDER=$REAL_GIT/saddler
LOCK_FOLDER=$STATE_FOLDER/lock
FORK_FOLDER=$STATE_FOLDER/view/$BRANCH
PRIVATE=$FORK_FOLDER/git
LOCK_FILE=$LOCK_FOLDER/view/$BRANCH
MODULES=()
declare -A WORKTREE TIPS MODULEOF

# [1] refuse a bad branch name or project; the registration, under its lock; nothing unless its generation
#     is the current one and the private .git exists
if [[ ! $BRANCH =~ ^[A-Za-z0-9_@-][A-Za-z0-9_@.-]*$ || $BRANCH == *..* || $BRANCH == *.lock ]] ||
   [ -z "$PROJ_FOLDER" ]; then
    echo "usage: publish.sh NAME, run in the project" >&2
    exit 1
fi
if [ ! -f "$LOCK_FILE" ]; then exit 0; fi
exec 195>>"$LOCK_FILE" || exit 1
flock 195
read -r _ SEEN _ < "$LOCK_FILE"
LATEST=$(cat "$LOCK_FOLDER/generation" 2>/dev/null)
if [ "$SEEN" != "${LATEST:-0}" ] || [ ! -e "$PRIVATE/HEAD" ]; then exit 0; fi

# [2] each submodule's branch, deepest first, then the project's
survey "$PRIVATE"
for ((I = ${#MODULES[@]} - 1; I >= 0; I--)); do
    M=${MODULES[I]}
    if [ -z "${WORKTREE[$M]:-}" ] || [ -z "${TIPS[$M]}" ]; then continue; fi
    if [ ! -d "$REAL_GIT/$M" ] && ! newmodule "$M"; then continue; fi
    publish "$REAL_GIT/$M" "$PRIVATE/$M" "${TIPS[$M]}" "${WORKTREE[$M]}" \
        "$(gitdir "$REAL_GIT/$M" rev-parse -q --verify HEAD)"
done
publish "$REAL_GIT" "$PRIVATE" "${TIPS[.]}" "$PROJ_FOLDER" "$(cat "$LOCK_FOLDER/base")" "$(defaultbranch)"
