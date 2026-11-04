#!/bin/bash
# overlayowner.sh PROJ_FOLDER LOCK_FOLDER CLAUDE_PID GIT_WRAPPER HOLD_WRAPPER... -- COMMAND...
PROJ_FOLDER=$1
LOCK_FOLDER=$2
CLAUDE_PID=$3
GIT_WRAPPER=$4
shift 4
HOLD=()
while [ "$1" != -- ]; do HOLD+=("$1"); shift; done
shift
OWNER_FOLDER=$PROJ_FOLDER/.git/saddler/owner
TRASH_FOLDER=$PROJ_FOLDER/.git/saddler/trash
MARKER=$LOCK_FOLDER/checkpointing
PERIOD=${SADDLER_CHECKPOINT_PERIOD:-300}
WAIT=${SADDLER_PREEMPT_WAIT:-60}
if [[ ! $PERIOD =~ ^[0-9]+$ ]]; then PERIOD=300; fi
if [[ ! $WAIT =~ ^[0-9]+$ ]]; then WAIT=60; fi

# [1] wait out a running checkpoint
exec 194<"$LOCK_FOLDER/ownercmd" || exit 1
flock -s 194

# [2] start the holder unless one is live
exec 195>>"$LOCK_FOLDER/ownerholder" || exit 1
flock 195
read -r HOLDER < "$LOCK_FOLDER/ownerholder"
if [ -z "$HOLDER" ] || ! kill -0 "$HOLDER" 2>/dev/null ||
   [ "$(readlink "/proc/$HOLDER/ns/mnt")" = "$(readlink /proc/self/ns/mnt)" ]; then
    IGNORED=()
    OVERLAYS=()
    if [ -e "$LOCK_FOLDER/ignored" ]; then mapfile -d '' -t IGNORED < "$LOCK_FOLDER/ignored"; fi
    for ENTRY in "${IGNORED[@]}"; do
        DIR=${ENTRY%/}
        if [ "$DIR" = "$ENTRY" ] || [ ! -d "$PROJ_FOLDER/$DIR" ]; then continue; fi
        NAME=${DIR//%/%25}
        NAME=${NAME//\//%2F}
        mkdir -p "$OWNER_FOLDER/$NAME/upper" "$OWNER_FOLDER/$NAME/work" || exit 1
        OVERLAYS+=(--overlay-src "$PROJ_FOLDER/$DIR"
                   --overlay "$OWNER_FOLDER/$NAME/upper" "$OWNER_FOLDER/$NAME/work" "$PROJ_FOLDER/$DIR")
    done
    START=$(mktemp -d) || exit 1
    mkfifo "$START/go" || exit 1
    exec 192<>"$START/go"
    setsid "${HOLD[@]}" "${OVERLAYS[@]}" --info-fd 9 --chdir / -- bash -c 'echo ready >&8; read -r _ <&7 && exec sleep infinity 7<&-' \
        7<"$START/go" 8>"$START/ready" 9>"$START/info" 192>&- 194<&- 195>&- </dev/null >/dev/null 2>"$START/err" &
    for i in $(seq 1 300); do
        if [ -s "$START/ready" ]; then break; fi
        sleep 0.02
    done
    HOLDER=$(sed -n 's/.*"child-pid": *\([0-9]*\).*/\1/p' "$START/info")
    if [ -z "$HOLDER" ] || [ ! -s "$START/ready" ]; then
        echo "overlayowner.sh: no holder: $(head -c 300 "$START/err")" >&2
        rm -rf "$START"
        exit 1
    fi
    rm -rf "$START"
    printf '%s\n' "$HOLDER" > "$LOCK_FOLDER/ownerholder"
    echo go >&192
    exec 192>&-
    setsid bash -c '
        while kill -0 "$0" 2>/dev/null && kill -0 "$1" 2>/dev/null; do sleep 1; done
        while kill -0 "$1" 2>/dev/null; do
            NS=$(readlink "/proc/$1/ns/mnt")
            if [ ! -e "$2" ]; then
                kill -KILL "$1"
            elif [ "$(readlink /proc/[0-9]*/ns/mnt 2>/dev/null | grep -Fxc "$NS")" -le 1 ]; then
                flock -n "$2" kill -KILL "$1"
            fi
            sleep 1
        done' "$CLAUDE_PID" "$HOLDER" "$LOCK_FOLDER/ownercmd" 194<&- 195>&- </dev/null >/dev/null 2>&1 &
fi
flock -u 195

# [3] execute command: tracked files and .git are real, ignored folders are overlays
rc=0
nsenter -t "$HOLDER" -U -m --preserve-credentials -- \
    env -C "$PWD" GIT_WRAPPER="$GIT_WRAPPER" "$@" 194<&- 195>&- || rc=$?

# [4] only the last owner command running may checkpoint
flock -n -x 194 || exit "$rc"

# [5] go on if an upper or the ignored list changed, and no fork is registered or a period passed
NEW=$(mktemp "$LOCK_FOLDER/new.XXXXXX") || exit "$rc"
trap 'rm -f "$NEW"' EXIT
GIT_HELD=1 git -C "$PROJ_FOLDER" ls-files -z --others --ignored --exclude-standard --directory | grep -zvE '(^|/)\.(claude|git)(/|$)' > "$NEW"
if [ "${PIPESTATUS[0]}" -ne 0 ]; then exit "$rc"; fi
if [ ! -e "$MARKER" ]; then
    if [ -z "$(env -C "$OWNER_FOLDER" find . -mindepth 3 -maxdepth 3 -path './*/upper/*' -print -quit 2>/dev/null)" ] &&
       cmp -s "$NEW" "$LOCK_FOLDER/ignored"; then
        exit "$rc"
    fi
    FORKED=''
    for FORK_FILE in "$LOCK_FOLDER"/*-*; do
        if [ -s "$FORK_FILE" ]; then FORKED=1; fi
    done
    printf -v NOW '%(%s)T' -1
    LAST=$(stat -c %Y "$LOCK_FOLDER/lastcheckpoint" 2>/dev/null) || LAST=0
    if [ -n "$FORKED" ] && [ $((NOW - LAST)) -lt "$PERIOD" ]; then exit "$rc"; fi
fi

# [6] a process left in the holder's namespace still uses the overlay: never kill the owner
NS=$(readlink "/proc/$HOLDER/ns/mnt" 2>/dev/null)
if [ -n "$NS" ] && [ "$(readlink /proc/[0-9]*/ns/mnt 2>/dev/null | grep -Fxc "$NS")" -gt 1 ]; then exit "$rc"; fi

# [7] close the gate, give fork commands the wait, kill every fork holder
killforks() {
    for FORK_FILE in "$LOCK_FOLDER"/*-*; do
        if [ ! -f "$FORK_FILE" ]; then continue; fi
        exec 193>>"$FORK_FILE"
        flock 193
        if read -r FORK REST < "$FORK_FILE" && [ "$FORK" != - ]; then
            kill -KILL "$FORK" 2>/dev/null
            for i in $(seq 1 500); do if ! kill -0 "$FORK" 2>/dev/null; then break; fi; sleep 0.01; done
            printf -- '- %s\n' "$REST" > "$FORK_FILE"
        fi
        exec 193>&-
    done
}
exec 196<"$LOCK_FOLDER/checkpoint/queue" 197<"$LOCK_FOLDER/checkpoint/mode" || exit "$rc"
flock 196
if ! flock -w "$WAIT" -x 197; then
    killforks
    until flock -w 1 -x 197; do killforks; done
fi
killforks

# [8] kill the owner's holder
if [ -n "$NS" ]; then
    kill -KILL "$HOLDER" 2>/dev/null
    for i in $(seq 1 500); do if ! kill -0 "$HOLDER" 2>/dev/null; then break; fi; sleep 0.01; done
fi
: > "$LOCK_FOLDER/ownerholder"

# [9] move each upper into real, each step repeats safely until the rename to trash
touch "$MARKER"
chmod -R u+rwx "$TRASH_FOLDER" 2>/dev/null
rm -rf "$TRASH_FOLDER"
shopt -s dotglob
for FOLDER in "$OWNER_FOLDER"/*/; do
    if [ ! -d "$FOLDER" ]; then continue; fi
    FOLDER=${FOLDER%/}
    NAME=${FOLDER##*/}
    DIR=${NAME//%2F//}
    REAL=$PROJ_FOLDER/${DIR//%25/%}
    UPPER=$FOLDER/upper
    mkdir -p "$REAL"
    find "$UPPER" -type c -printf '%P\0' | env -C "$REAL" xargs -0 -r rm -rf --
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
            sys.stdout.write(os.path.relpath(path, sys.argv[1]) + "\0")' "$UPPER" | env -C "$REAL" xargs -0 -r rm -rf --
    find "$UPPER" ! -type d -printf '%P\0' | while IFS= read -r -d '' ITEM; do
        if [ -d "$REAL/$ITEM" ] && [ ! -L "$REAL/$ITEM" ]; then rm -rf "${REAL:?}/$ITEM"; fi
    done
    if ! cp -alf --no-preserve=xattr "$UPPER/." "$REAL/" || ! mv -T "$FOLDER" "$TRASH_FOLDER"; then
        echo "overlayowner.sh: checkpoint failed, the next owner command retries" >&2
        if [ "$rc" -eq 0 ]; then rc=1; fi
        exit "$rc"
    fi
    chmod -R u+rwx "$TRASH_FOLDER"
    rm -rf "$TRASH_FOLDER"
done

# [10] publish the ignored list and the generation, open the gate
mv -f "$NEW" "$LOCK_FOLDER/ignored"
GENERATION=$(cat "$LOCK_FOLDER/generation" 2>/dev/null)
printf '%s\n' "$((GENERATION + 1))" > "$LOCK_FOLDER/generation"
touch "$LOCK_FOLDER/lastcheckpoint"
rm -f "$MARKER"
exit "$rc"
