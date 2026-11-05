#!/bin/bash
# overlayfork.sh PROJ_FOLDER LOCK_FILE CLAUDE_PID [COMMAND...]
# One agent's command on its own view: an overlay of the real project and a
# privatized .git, holding one privatized git folder per submodule, kept mounted by
# a holder process, after which the agent's branches are published to the real
# repositories. Without a command, only publish.
PROJ_FOLDER=$1
LOCK_FILE=$2
CLAUDE_PID=$3
shift 3
HERE=$(dirname "$(readlink -f "$0")")
LOCK_FOLDER=${LOCK_FILE%/*}
STATE_FOLDER=${LOCK_FOLDER%/*}
BOX=${STATE_FOLDER%/*}
REAL_GIT=$PROJ_FOLDER/.git
BRANCH=''
if [ -s "$LOCK_FILE" ]; then read -r _ _ BRANCH _ < "$LOCK_FILE"; fi
if [[ ! $BRANCH == session-*/agent-* ]]; then
    echo "overlayfork.sh: $LOCK_FILE registers no agent branch" >&2
    exit 1
fi
SESSION=${BRANCH#session-}
FORK_FOLDER=$STATE_FOLDER/session-${SESSION%%/*}/agent-${BRANCH##*/agent-}
PRIVATE=$FORK_FOLDER/git
GENERATION=$(cat "$LOCK_FOLDER/generation" 2>/dev/null)
GENERATION=${GENERATION:-0}
MODULES=()
declare -A WORKTREE TIPS BASES MODULEOF
# gitdir DIR ARGS...: git on a git folder from outside the view, where a submodule's work tree path leads nowhere
gitdir() {
    git -C / --git-dir="$1" --work-tree=/ "${@:2}"
}
starttime() {
    local STAT=''
    { read -r STAT < "/proc/$1/stat"; } 2>/dev/null
    cut -d' ' -f20 <<< "${STAT##*) }"
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
# privatize M BUILD: a private git folder for real submodule M inside the .git view being built; git reads
# core.bare and core.worktree only from the folder's own config, never through an include
privatize() {
    local OWN=$2/$1
    git init -q --bare --template= --object-format="$(gitdir "$REAL_GIT/$1" rev-parse --show-object-format)" "$OWN" &&
        gitdir "$OWN" config core.bare false &&
        gitdir "$OWN" config core.worktree "$(gitdir "$REAL_GIT/$1" config core.worktree)" &&
        gitdir "$OWN" symbolic-ref HEAD "refs/heads/$BRANCH" &&
        gitdir "$OWN" config include.path "$STATE_FOLDER/realgit/$1/config" &&
        gitdir "$OWN" config gc.auto 0 &&
        mkdir -p "$OWN/refs/remotes/saddler" "$OWN/objects/info" &&
        printf '%s\n' "$STATE_FOLDER/realgit/$1/objects" > "$OWN/objects/info/alternates" &&
        { [ -z "${TIPS[$1]}" ] || gitdir "$OWN" update-ref "refs/heads/$BRANCH" "${TIPS[$1]}"; }
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
            echo "overlayfork.sh: $BRANCH is not published in ${WT#"$PROJ_FOLDER"/}, $REASON" >&2
        elif ! ( set -o pipefail
                 GIT_ALTERNATE_OBJECT_DIRECTORIES=$OWN/objects gitdir "$REAL" rev-list --objects "$TIP" --not --all |
                     cut -d' ' -f1 |
                     GIT_ALTERNATE_OBJECT_DIRECTORIES=$OWN/objects gitdir "$REAL" pack-objects --stdout -q |
                     gitdir "$REAL" unpack-objects -q --strict ) ||
             ! gitdir "$REAL" update-ref "refs/heads/$BRANCH" "$TIP" "$OLD"; then
            echo "overlayfork.sh: publishing $BRANCH in ${WT#"$PROJ_FOLDER"/} failed, the next command retries" >&2
        fi
    fi
    if ! grep -qsF "$STATE_FOLDER/realgit" "$OWN/objects/info/alternates"; then return; fi
    env -C "$OWN/objects" find . -mindepth 2 -maxdepth 2 -regextype posix-extended \
            -regex '\./[0-9a-f]{2}/[0-9a-f]{38,62}' -printf '%P\n' 2>/dev/null | tr -d / |
        gitdir "$REAL" cat-file --batch-check='%(objectname) %(objecttype)' |
        while read -r OID TYPE; do
            if [ "$TYPE" != missing ]; then rm -f "$OWN/objects/${OID:0:2}/${OID:2}"; fi
        done
}
# publishall: each submodule's branch, deepest first, creating real submodules the agent added, then the project's
publishall() {
    local LATEST I M
    LATEST=$(cat "$LOCK_FOLDER/generation" 2>/dev/null)
    if [ "${LATEST:-0}" != "$GENERATION" ] || [ ! -e "$PRIVATE/HEAD" ]; then return; fi
    flock 195
    survey "$PRIVATE"
    for ((I = ${#MODULES[@]} - 1; I >= 0; I--)); do
        M=${MODULES[I]}
        if [ -z "${WORKTREE[$M]:-}" ] || [ -z "${TIPS[$M]}" ]; then continue; fi
        if [ ! -d "$REAL_GIT/$M" ] && ! newmodule "$M"; then continue; fi
        publish "$REAL_GIT/$M" "$PRIVATE/$M" "${TIPS[$M]}" "${WORKTREE[$M]}" \
            "$(gitdir "$REAL_GIT/$M" rev-parse -q --verify HEAD)"
    done
    publish "$REAL_GIT" "$PRIVATE" "${TIPS[.]}" "$PROJ_FOLDER" "$(cat "$LOCK_FOLDER/base")" "$(defaultbranch)"
    flock -u 195
}
exec 195>>"$LOCK_FILE" || exit 1
if [ $# -eq 0 ]; then publishall; exit 0; fi
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

# [2] the privatized .git view: own HEAD, index, refs and config, objects staged here and read from real,
#     and one such git folder for each real submodule
FRESH=''
if [ ! -e "$PRIVATE/HEAD" ]; then
    survey "$REAL_GIT"
    if [ -z "${TIPS[.]}" ]; then
        echo "overlayfork.sh: there is no branch $BRANCH" >&2
        exit 1
    fi
    for M in "${MODULES[@]}"; do
        BASES[$M]=$(gitdir "$REAL_GIT/$M" rev-parse -q --verify HEAD)
        if [ -z "${TIPS[$M]}" ] || ! gitdir "$REAL_GIT/$M" cat-file -e "${TIPS[$M]}^{commit}" 2>/dev/null; then
            TIPS[$M]=${BASES[$M]}
        fi
    done
    DEFAULT=$(defaultbranch)
    mkdir -p "$FORK_FOLDER/fork" "$FORK_FOLDER/work" || exit 1
    ln -sfn "$REAL_GIT" "$STATE_FOLDER/realgit"
    BUILD=$(mktemp -d "$FORK_FOLDER/git.XXXXXX") || exit 1
    FAILED=''
    if ! { git init -q --template= --object-format="$(gitdir "$REAL_GIT" rev-parse --show-object-format)" "$BUILD" &&
           gitdir "$BUILD/.git" symbolic-ref HEAD "refs/heads/$BRANCH" &&
           gitdir "$BUILD/.git" config include.path "$STATE_FOLDER/realgit/config" &&
           gitdir "$BUILD/.git" config gc.auto 0 &&
           gitdir "$BUILD/.git" config alias.checkpoint "!$HERE/requestcheckpoint.sh ${DEFAULT#refs/heads/}" &&
           mkdir -p "$BUILD/.git/refs/remotes/saddler" "$BUILD/.git/objects/info" &&
           printf '%s\n' "$STATE_FOLDER/realgit/objects" > "$BUILD/.git/objects/info/alternates" &&
           gitdir "$BUILD/.git" update-ref "refs/heads/$BRANCH" "${TIPS[.]}"; }; then
        FAILED=1
    fi
    for M in "${MODULES[@]}"; do
        if [ -z "$FAILED" ] && [ -n "${WORKTREE[$M]:-}" ] && ! privatize "$M" "$BUILD/.git"; then FAILED=1; fi
    done
    if [ -n "$FAILED" ] || ! mv -T "$BUILD/.git" "$PRIVATE"; then
        rm -rf "$BUILD"
        echo "overlayfork.sh: cannot build the .git view of $BRANCH" >&2
        exit 1
    fi
    rm -rf "$BUILD"
    FRESH=1
fi

# [3] start the holder unless one is live: one overlay of the real project, the .git view with each submodule's
#     real branches, real .git read-only, every other .git folder in the project read-only;
#     a new view checks its branches out over the base, writing only files that differ from real
if [ -z "$LIVE" ]; then
    MOUNTS=()
    while IFS= read -r M; do
        if [ -d "$REAL_GIT/$M/refs/heads" ] && [ -d "$PRIVATE/$M/refs/remotes/saddler" ]; then
            MOUNTS+=(--ro-bind "$REAL_GIT/$M/refs/heads" "$PROJ_FOLDER/.git/$M/refs/remotes/saddler")
        fi
    done < <(modules "$PRIVATE/modules" modules/)
    while IFS= read -r -d '' M; do
        MOUNTS+=(--ro-bind "$M" "$M")
    done < <(find "$PROJ_FOLDER" -path "$PROJ_FOLDER/.git" -prune -o -name .git -type d -print0 -prune)
    START=$(mktemp -d) || exit 1
    mkfifo "$START/go" || exit 1
    exec 192<>"$START/go"
    setsid "$HERE/allowlist.sh" "$PROJ_FOLDER" --unshare-pid --proc /proc \
        --overlay-src "$PROJ_FOLDER" --overlay "$FORK_FOLDER/fork" "$FORK_FOLDER/work" "$PROJ_FOLDER" \
        --bind "$PRIVATE" "$PROJ_FOLDER/.git" \
        --ro-bind "$REAL_GIT/refs/heads" "$PROJ_FOLDER/.git/refs/remotes/saddler" \
        "${MOUNTS[@]}" \
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
    CHECKOUT='git read-tree "$1" && { git update-index -q --refresh > /dev/null; git read-tree -m -u "$1" "$2"; }'
    if [ -n "$FRESH" ]; then
        FAILED=''
        nsenter -t "$HOLDER" -U -m -p --preserve-credentials -- env -C "$PROJ_FOLDER" \
            bash -c "$CHECKOUT" _ "$(cat "$LOCK_FOLDER/base")" "${TIPS[.]}" || FAILED=1
        for M in "${MODULES[@]}"; do
            if [ -n "$FAILED" ] || [ -z "${WORKTREE[$M]:-}" ] || [ -z "${BASES[$M]}" ] || [ ! -e "${WORKTREE[$M]}/.git" ]; then
                continue
            fi
            nsenter -t "$HOLDER" -U -m -p --preserve-credentials -- env -C "${WORKTREE[$M]}" \
                bash -c "$CHECKOUT" _ "${BASES[$M]}" "${TIPS[$M]}" || FAILED=1
        done
        if [ -n "$FAILED" ]; then
            kill -KILL "$HOLDER" 2>/dev/null
            chmod -R u+rwx "$FORK_FOLDER" 2>/dev/null
            rm -rf "$FORK_FOLDER"
            echo "overlayfork.sh: cannot check $BRANCH out over the real project" >&2
            exit 1
        fi
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

# [5] publish each submodule's branch, then the project's
publishall

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
