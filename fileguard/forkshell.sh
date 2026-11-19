#!/usr/bin/env bash
# forkshell.sh SESSION[/AGENT] [COMMAND...]
# SESSION[/AGENT] may also be the branch name session-SESSION[/agent-AGENT]
# COMMAND, or an interactive bash, on one agent's own view of the project, named by
#   SESSION                 the session; one starting with human- gets a person's view
#   AGENT                   the agent, default master
# and by CLAUDE_PID, the Claude process, default the parent; the project is the one holding the current folder.
# The view is an overlay of the real project and a privatized .git, holding one privatized git folder per
# submodule, kept mounted by a holder process. sandbox.sh runs every tool call through it, and publish.sh
# publishes the agent's branches when the command ends. The interactive bash also sources this file as its init file.
if [ "${BASH_SOURCE[0]}" != "$0" ]; then
    if [ -f ~/.bashrc ]; then . ~/.bashrc; fi
    PS1="(fork ${CLAUDE_CODE_SESSION_ID:-}/${CLAUDE_AGENT:-master}) ${PS1:-\$ }"
    return
fi
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
        gitdir "$OWN" config include.path "$REAL_GIT/alt/$1/config" &&
        gitdir "$OWN" config gc.auto 0 &&
        mkdir -p "$OWN/refs/remotes/saddler" "$OWN/objects/info" &&
        printf '%s\n' "$REAL_GIT/alt/$1/objects" > "$OWN/objects/info/alternates" &&
        { [ -z "${TIPS[$1]}" ] || gitdir "$OWN" update-ref "refs/heads/$BRANCH" "${TIPS[$1]}"; }
}
HERE=$(dirname "$(readlink -f "$0")")
export CLAUDE_PID=${CLAUDE_PID:-$PPID}
SPEC=${1:-}
SESSION=${SPEC%%/*} AGENT=master
if [[ $SPEC == */* ]]; then AGENT=${SPEC#*/}; fi
SESSION=${SESSION#session-}
AGENT=${AGENT#agent-}
PROJ_FOLDER=$(outermost "$PWD")
REAL_GIT=$PROJ_FOLDER/.git
STATE_FOLDER=$REAL_GIT/saddler
SESSION_FOLDER=$STATE_FOLDER/session-$SESSION
FORK_FOLDER=$SESSION_FOLDER/agent-$AGENT
PRIVATE=$FORK_FOLDER/git
LOCK_FOLDER=$STATE_FOLDER/lock
LOCK_FILE=$LOCK_FOLDER/$SESSION-$AGENT
BRANCH=session-$SESSION/agent-$AGENT
RUN=("${@:2}")
if [ $# -le 1 ]; then RUN=(bash --init-file "$HERE/forkshell.sh" -i); fi
MODULES=()
declare -A WORKTREE TIPS BASES MODULEOF

# [1] refuse a bad session id, agent name or project; make the session and lock folders
if [[ ! $SESSION =~ ^[A-Za-z0-9-]+$ ]]; then
    echo "usage: forkshell.sh SESSION[/AGENT] [COMMAND...], or session-SESSION[/agent-AGENT] for SESSION[/AGENT]," \
        "SESSION being letters, digits and dashes" >&2
    exit 1
fi
if [[ ! $AGENT =~ ^[A-Za-z0-9_@-][A-Za-z0-9_@.-]*$ || $AGENT == *.lock || $AGENT == *..* ]]; then
    echo "forkshell.sh: bad agent name '$AGENT'" >&2
    exit 1
fi
if [ -z "$PROJ_FOLDER" ]; then echo "forkshell.sh: $PWD is in no project" >&2; exit 1; fi
export CLAUDE_CODE_SESSION_ID=$SESSION CLAUDE_AGENT=$AGENT
mkdir -p "$SESSION_FOLDER" "$LOCK_FOLDER" || exit 1
touch "$LOCK_FOLDER/gate" "$LOCK_FOLDER/checkpoint" || exit 1

# [2] a project without a commit has nothing to view: a person's command runs unsandboxed, an agent's under allowlist.sh
if ! git -C "$PROJ_FOLDER" rev-parse --verify -q HEAD > /dev/null 2>&1; then
    if [[ $SESSION == human-* ]]; then exec "${RUN[@]}"; fi
    exec "$HERE/allowlist.sh" "$PROJ_FOLDER" --bind "$PROJ_FOLDER" "$PROJ_FOLDER" \
        --chdir "$PWD" -- "${RUN[@]}"
fi

# [3] a checkpoint is in progress: finish it if nobody runs it, otherwise fail now
if [ -e "$LOCK_FOLDER/checkpointing" ]; then
    "$HERE/checkpoint.sh" "$PROJ_FOLDER" || true
    if [ -e "$LOCK_FOLDER/checkpointing" ]; then
        echo "forkshell.sh: a checkpoint is running, run this again shortly" >&2
        exit 1
    fi
fi

# [4] no base yet: the real project becomes the first one
if [ ! -s "$LOCK_FOLDER/base" ]; then "$HERE/checkpoint.sh" "$PROJ_FOLDER" || exit 1; fi

# [5] the agent's branch, from the base if missing, and its registration
if ! git -C "$PROJ_FOLDER" rev-parse --verify -q "refs/heads/$BRANCH" > /dev/null; then
    git -C "$PROJ_FOLDER" update-ref "refs/heads/$BRANCH" "$(cat "$LOCK_FOLDER/base")" "" 2> /dev/null || true
fi
REGISTERED=''
if [ -s "$LOCK_FILE" ]; then read -r _ _ REGISTERED _ < "$LOCK_FILE"; fi
if [ "$REGISTERED" != "$BRANCH" ]; then
    GENERATION=$(cat "$LOCK_FOLDER/generation" 2> /dev/null || true)
    printf -- '- %s %s %s\n' "${GENERATION:-0}" "$BRANCH" "$CLAUDE_PID" > "$LOCK_FILE"
fi

# [6] the gate, shared until the command is published, never inherited by a child; then the registration's lock
exec 189<"$LOCK_FOLDER/gate" || exit 1
if ! flock -n -s 189; then
    echo "forkshell.sh: a checkpoint is running, run this again shortly" >&2
    exit 1
fi
exec 195>>"$LOCK_FILE" || exit 1
GENERATION=$(cat "$LOCK_FOLDER/generation" 2>/dev/null)
GENERATION=${GENERATION:-0}
rc=0

# [7] a checkpoint ran since this agent's view was built: say so once, start over from its branch
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
        echo "forkshell.sh: a checkpoint reset this agent to its branch $BRANCH, uncommitted work is gone" >&2
    fi
    chmod -R u+rwx "$FORK_FOLDER" 2>/dev/null
    rm -rf "$FORK_FOLDER"
    printf -- '- %s %s %s\n' "$GENERATION" "$BRANCH" "$CLAUDE_PID" > "$LOCK_FILE"
fi

# [8] the privatized .git view: own HEAD, index, refs and config, objects staged here and read from real through
#     .git/alt, a link the real .git holds to itself, and one such git folder for each real submodule; an agent's
#     .git, not a submodule's, is a sparse checkout without .claude, which stays the real project's
FRESH=''
if [ ! -e "$PRIVATE/HEAD" ]; then
    survey "$REAL_GIT"
    if [ -z "${TIPS[.]}" ]; then
        echo "forkshell.sh: there is no branch $BRANCH" >&2
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
    ln -sfn . "$REAL_GIT/alt"
    BUILD=$(mktemp -d "$FORK_FOLDER/git.XXXXXX") || exit 1
    FAILED=''
    if ! { git init -q --template= --object-format="$(gitdir "$REAL_GIT" rev-parse --show-object-format)" "$BUILD" &&
           gitdir "$BUILD/.git" symbolic-ref HEAD "refs/heads/$BRANCH" &&
           gitdir "$BUILD/.git" config include.path "$REAL_GIT/alt/config" &&
           gitdir "$BUILD/.git" config gc.auto 0 &&
           { [[ $BRANCH == session-human-* ]] || {
                 gitdir "$BUILD/.git" config core.sparseCheckout true &&
                 gitdir "$BUILD/.git" config core.sparseCheckoutCone false &&
                 gitdir "$BUILD/.git" config sparse.expectFilesOutsideOfPatterns true &&
                 mkdir -p "$BUILD/.git/info" && printf '/*\n!.claude/\n' > "$BUILD/.git/info/sparse-checkout"; }; } &&
           gitdir "$BUILD/.git" config alias.checkpoint "!$HERE/requestcheckpoint.sh ${DEFAULT#refs/heads/}" &&
           mkdir -p "$BUILD/.git/refs/remotes/saddler" "$BUILD/.git/objects/info" &&
           printf '%s\n' "$REAL_GIT/alt/objects" > "$BUILD/.git/objects/info/alternates" &&
           gitdir "$BUILD/.git" update-ref "refs/heads/$BRANCH" "${TIPS[.]}"; }; then
        FAILED=1
    fi
    for M in "${MODULES[@]}"; do
        if [ -z "$FAILED" ] && [ -n "${WORKTREE[$M]:-}" ] && ! privatize "$M" "$BUILD/.git"; then FAILED=1; fi
    done
    if [ -n "$FAILED" ] || ! mv -T "$BUILD/.git" "$PRIVATE"; then
        rm -rf "$BUILD"
        echo "forkshell.sh: cannot build the .git view of $BRANCH" >&2
        exit 1
    fi
    rm -rf "$BUILD"
    FRESH=1
fi

# [9] start the holder unless one is live: one overlay of the real project, the .git view with each submodule's
#     real branches, real .git read-only at .git/alt with its saddler folder covered, every other .git folder in
#     the project read-only; neither the holder nor its watcher keeps the gate or the registration's lock;
#     a new view checks its branches out over the base, writing only files that differ from real;
#     an agent's marks .claude skip-worktree first, so it is never written
#     a person's view sits on the whole host instead of allowlist.sh's, ssh drop-ins covered;
#     an agent's holder starts a private Xvfb, on an abstract socket only, and writes its display number to the
#     display file before ready, waiting at most 3 s
if [ -z "$LIVE" ]; then
    LAUNCH=("$HERE/allowlist.sh" "$PROJ_FOLDER")
    HOLD='echo ready >&8; read -r _ <&7 && exec sleep infinity 7<&-'
    if [[ $BRANCH == session-human-* ]]; then
        LAUNCH=(bwrap --dev-bind / /)
        if [ -d /etc/ssh/ssh_config.d ]; then
            LAUNCH+=(--tmpfs /etc/ssh/ssh_config.d --remount-ro /etc/ssh/ssh_config.d)
        fi
    elif command -v Xvfb > /dev/null; then
        HOLD='exec {P}< <(exec Xvfb -displayfd 1 -nolisten tcp -nolisten unix -screen 0 1920x1080x24 2> /dev/null 6>&- 7<&- 8>&-); '\
'read -r -t 3 N <&$P && echo "$N" >&6; exec 6>&- {P}<&-; '$HOLD
    fi
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
    setsid "${LAUNCH[@]}" --unshare-pid --proc /proc \
        --overlay-src "$PROJ_FOLDER" --overlay "$FORK_FOLDER/fork" "$FORK_FOLDER/work" "$PROJ_FOLDER" \
        --bind "$PRIVATE" "$PROJ_FOLDER/.git" \
        --ro-bind "$REAL_GIT/refs/heads" "$PROJ_FOLDER/.git/refs/remotes/saddler" \
        "${MOUNTS[@]}" \
        --ro-bind "$REAL_GIT" "$REAL_GIT/alt" --tmpfs "$REAL_GIT/alt/saddler" \
        --ro-bind "$HERE" "$HERE" \
        --info-fd 9 --chdir / -- bash -c "$HOLD" \
        6>"$FORK_FOLDER/display" 7<"$START/go" 8>"$START/ready" 9>"$START/info" 189<&- 192>&- 195>&- </dev/null >/dev/null 2>"$START/err" &
    for i in $(seq 1 300); do
        if [ -s "$START/ready" ]; then break; fi
        sleep 0.02
    done
    HOLDER=$(sed -n 's/.*"child-pid": *\([0-9]*\).*/\1/p' "$START/info")
    if [ -z "$HOLDER" ] || [ ! -s "$START/ready" ]; then
        echo "forkshell.sh: no holder: $(head -c 300 "$START/err")" >&2
        rm -rf "$START"
        exit 1
    fi
    rm -rf "$START"
    BORN=$(starttime "$HOLDER")
    echo go >&192
    exec 192>&-
    CHECKOUT='git read-tree "$1" && { [ "$(git config core.sparseCheckout)" != true ] || git ls-files -z -- ":(glob)**/.claude/**" | git update-index -z --skip-worktree --stdin; } && { git update-index -q --refresh > /dev/null; git read-tree -m -u "$1" "$2"; }'
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
            echo "forkshell.sh: cannot check $BRANCH out over the real project" >&2
            exit 1
        fi
    fi
    printf '%s %s %s %s %s\n' "$HOLDER" "$GENERATION" "$BRANCH" "$CLAUDE_PID" "$BORN" > "$LOCK_FILE"
    setsid bash -c 'while kill -0 "$0" 2>/dev/null && kill -0 "$1" 2>/dev/null; do sleep 1; done; kill -KILL "$1" 2>/dev/null' \
        "$CLAUDE_PID" "$HOLDER" 189<&- 195>&- </dev/null >/dev/null 2>&1 &
fi
flock -u 195

# [10] run the command in the holder; an agent's on the private display, or on none
CWD=$PWD
if [ ! -d "/proc/$HOLDER/root$CWD" ]; then CWD=$PROJ_FOLDER; fi
SCREEN=()
if [[ $BRANCH != session-human-* ]]; then
    SCREEN=(-u WAYLAND_DISPLAY -u XDG_SESSION_TYPE -u DISPLAY)
    NUMBER=''
    { read -r NUMBER < "$FORK_FOLDER/display"; } 2>/dev/null
    if [[ $NUMBER =~ ^[0-9]+$ ]]; then SCREEN=(-u WAYLAND_DISPLAY -u XDG_SESSION_TYPE "DISPLAY=:$NUMBER"); fi
fi
nsenter -t "$HOLDER" -U -m -p --preserve-credentials -- env -C "$CWD" "${SCREEN[@]}" "${RUN[@]}" 189<&- 195>&- || rc=$?
if [ "$rc" -ge 128 ]; then
    for i in $(seq 1 100); do if ! kill -0 "$HOLDER" 2>/dev/null; then break; fi; sleep 0.01; done
fi
if [ "$rc" -ne 0 ] && ! kill -0 "$HOLDER" 2>/dev/null; then
    echo "forkshell.sh: a checkpoint preempted this command, run it again" >&2
    exit "$rc"
fi

# [11] publish the agent's branches, log a new largest size of the upper in this generation, let go of the gate
env -C "$PROJ_FOLDER" "$HERE/publish.sh" "$BRANCH" 189<&- 195>&-
if [ -d "$FORK_FOLDER/fork" ]; then
    SIZE=$(du -sb "$FORK_FOLDER/fork" 2>/dev/null | cut -f1)
    LAST=$(grep -F " $GENERATION $FORK_FOLDER/fork " "$STATE_FOLDER/uppersize.log" 2>/dev/null | tail -n 1)
    LAST=${LAST##* }
    if [ -n "$SIZE" ] && [ "$SIZE" -gt "${LAST:-0}" ]; then
        printf '%(%Y-%m-%dT%H:%M:%S)T %s %s %s\n' -1 "$GENERATION" "$FORK_FOLDER/fork" "$SIZE" >> "$STATE_FOLDER/uppersize.log"
    fi
fi
exec 189<&- 195>&-

# [12] the command ran git checkpoint
if [ -e "$FORK_FOLDER/git/checkpoint" ]; then
    "$HERE/checkpoint.sh" "$PROJ_FOLDER" "$LOCK_FILE" || if [ "$rc" -eq 0 ]; then rc=1; fi
fi
exit "$rc"
