#!/usr/bin/env bash
# allowlist.sh PROJ_FOLDER MOUNT_ARGS... -- COMMAND...
set -euo pipefail
PROJ_FOLDER=$1
shift
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
# [4] whitelist.txt, $TMPDIR; a socket in a ro or rw line is refused, dbus-system lines are collected
CALLS=()
while read -r MODE WPATH STORE; do
    if [ "$MODE" = dbus-system ]; then
        if [ -n "$WPATH" ] && [ -n "$STORE" ]; then CALLS+=("--call=$WPATH=$STORE"); fi
        continue
    fi
    WPATH=${WPATH/#\~/$HOME}
    STORE=${STORE/#\~/$HOME}
    if [ ! -e "$WPATH" ]; then continue; fi
    if [[ $MODE == r[ow] && -S $WPATH ]]; then
        echo "allowlist.sh: $WPATH is a socket, which $MODE cannot restrict, skipped" >&2
        continue
    fi
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
# [6] system bus: the dbus-system calls through xdg-dbus-proxy, which ends once the sandbox lets go of its sync fd
if [ ${#CALLS[@]} -gt 0 ]; then
    if ! command -v xdg-dbus-proxy > /dev/null; then
        echo "allowlist.sh: xdg-dbus-proxy is missing, no system bus" >&2
    elif BUS=$(mktemp -d "${XDG_RUNTIME_DIR:-/tmp}/saddler-bus.XXXXXX" 2> /dev/null || mktemp -d /tmp/saddler-bus.XXXXXX); then
        exec {SYNC}< <({ xdg-dbus-proxy --fd=1 "${DBUS_SYSTEM_BUS_ADDRESS:-unix:path=/run/dbus/system_bus_socket}" \
                             "$BUS/socket" --filter "${CALLS[@]}"; rm -rf "$BUS"; } < /dev/null 2> /dev/null)
        READY=''
        read -r -n 1 -u "$SYNC" READY || true
        if [ "$READY" = x ]; then
            args+=(--bind "$BUS/socket" /run/dbus/system_bus_socket --sync-fd "$SYNC"
                   --setenv DBUS_SYSTEM_BUS_ADDRESS unix:path=/run/dbus/system_bus_socket)
        else
            echo "allowlist.sh: xdg-dbus-proxy did not start, no system bus" >&2
        fi
    fi
fi
# [7] MOUNT_ARGS
args+=("${MOUNTS[@]}")
# [8] every .claude in the project, read-only
while IFS= read -r -d '' p; do
    args+=(--ro-bind "$p" "$p")
done < <(find "$PROJ_FOLDER" -name .git -prune -o ! -type l -name .claude -prune -print0)
wait $! || { echo "allowlist.sh: cannot scan $PROJ_FOLDER" >&2; exit 1; }
exec bwrap "${args[@]}" --remount-ro / -- "$@"
