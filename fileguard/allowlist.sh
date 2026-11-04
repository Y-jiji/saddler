#!/usr/bin/env bash
# allowlist.sh PROJ_FOLDER SCAN_FOLDER MOUNT_ARGS... -- COMMAND...
set -euo pipefail
PROJ_FOLDER=$1
SCAN_FOLDER=$2
shift 2
MOUNTS=()
while [ "$1" != -- ]; do MOUNTS+=("$1"); shift; done
shift
# [1] host /dev, fresh /proc, top-level symlinks
args=(--dev-bind /dev /dev --proc /proc)
for p in /*; do
    if [ -L "$p" ]; then args+=(--symlink "$(readlink "$p")" "$p"); fi
done
# [2] library and PATH folders, read-only
while IFS= read -r d; do
    if [[ $d != /* || ! -d $d || $d == / || $d == "$HOME" ]]; then continue; fi
    if [[ $d == "$HOME"/* ]]; then r=${d#"$HOME"/}; d=$HOME/${r%%/*}; fi
    args+=(--ro-bind "$d" "$d")
done < <({ ldconfig -p | sed -n 's|.* => \(.*\)/[^/]*$|\1|p'
           tr : '\n' <<<"${LD_LIBRARY_PATH:-}:$PATH"; } | sort -u)
# [3] dot entries in ~, read-only
for e in "$HOME"/.[!.]*; do
    if [ -e "$e" ] && [ ! -L "$e" ]; then args+=(--ro-bind "$e" "$e"); fi
done
# [4] whitelist.txt, $TMPDIR
while read -r MODE WPATH STORE; do
    WPATH=${WPATH/#\~/$HOME}
    STORE=${STORE/#\~/$HOME}
    if [ ! -e "$WPATH" ]; then continue; fi
    case $MODE in
        ro) args+=(--ro-bind "$WPATH" "$WPATH") ;;
        rw) args+=(--bind "$WPATH" "$WPATH") ;;
        private)
            if [ -L "$WPATH" ]; then continue; fi
            mkdir -p -m 700 "$STORE"
            args+=(--bind "$STORE" "$WPATH")
            for e in "$WPATH"/* "$WPATH"/.[!.]*; do
                if [ -e "$e" ]; then args+=(--ro-bind "$e" "$e"); fi
            done ;;
    esac
done < "$HOME/.claude/sandbox/whitelist.txt"
if [ -d "${TMPDIR:-}" ]; then args+=(--bind "$TMPDIR" "$TMPDIR"); fi
if [ -e /.realgit ]; then args+=(--ro-bind /.realgit "$(readlink -f "$(command -v git)")"); fi
# [5] empty covers: X11, Claude daemon sockets, ssh drop-ins
for d in /tmp/.X11-unix "/tmp/cc-daemon-$UID" /etc/ssh/ssh_config.d; do
    if [ -d "$d" ]; then args+=(--tmpfs "$d" --remount-ro "$d"); fi
done
# [6] MOUNT_ARGS
args+=("${MOUNTS[@]}")
# [7] read-only under SCAN_FOLDER, placed under PROJ_FOLDER
while IFS= read -r -d '' p; do
    args+=(--ro-bind "$p" "$PROJ_FOLDER${p#"$SCAN_FOLDER"}")
done < <(find "$SCAN_FOLDER" ! -type l \
    \( \( -name .claude -o -name .git -type f \) -prune -print0 \
    -o -path '*/.git/*' \( -name config -o -name hooks \) -prune -print0 \))
wait $! || { echo "allowlist.sh: cannot scan $SCAN_FOLDER" >&2; exit 1; }
exec bwrap "${args[@]}" --remount-ro / -- "$@"
