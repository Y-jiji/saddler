#!/usr/bin/env bash
# whitelist.sh [WHITELIST...] -- [BWRAP_OPTION...] -- [COMMAND...]
# bwrap on a bare root: the host /dev, a fresh /proc, the top-level symlinks, library and PATH folders and the dot
# entries in ~ read-only, then each WHITELIST's lines in order, then the BWRAP_OPTIONs as given, then the .claude
# folders of the guard lines read-only, so they also cover what the options mounted; COMMAND defaults to bash.
# A line is a mode and a path, the rest of the line, ~ expanded, a missing one skipped:
#   ro PATH, rw PATH       read-only, read-write; a socket is refused, which read-only cannot restrict
#   private PATH           a folder with a throwaway upper, gone when the sandbox ends
#   guard PATH             every .claude below PATH outside a folder holding its own .git, read-only
#   dbus-system NAME RULE  a system bus call matching RULE on NAME, let through xdg-dbus-proxy
set -euo pipefail
FILES=()
OPTIONS=()
while [ $# -gt 0 ] && [ "$1" != -- ]; do FILES+=("$1"); shift; done
if [ $# -gt 0 ]; then shift; fi
while [ $# -gt 0 ] && [ "$1" != -- ]; do OPTIONS+=("$1"); shift; done
if [ $# -eq 0 ]; then
    echo "usage: whitelist.sh [WHITELIST...] -- [BWRAP_OPTION...] -- [COMMAND...]" >&2
    exit 1
fi
shift
if [ $# -eq 0 ]; then set -- bash; fi
# claudes FOLDER: every .claude below FOLDER outside a folder holding its own .git, such as a submodule, NUL-separated
claudes() {
    local P R
    local -a REPOS=() CLAUDES=()
    while IFS= read -r -d '' P; do
        case $P in
            g"$1") ;;
            g*) REPOS+=("${P#g}") ;;
            *) CLAUDES+=("${P#c}") ;;
        esac
    done < <(find "$1" -name .git -printf 'g%h\0' -prune -o ! -type l -name .claude -printf 'c%p\0' -prune)
    wait $! || return 1
    for P in "${CLAUDES[@]}"; do
        for R in "${REPOS[@]}"; do if [[ $P == "$R"/* ]]; then continue 2; fi; done
        printf '%s\0' "$P"
    done
}
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
# [4] each WHITELIST's lines in order, $TMPDIR; a socket in a ro or rw line is refused, a private folder gets a
#     throwaway upper, dbus-system calls and guard folders are collected; an unreadable WHITELIST is refused
CALLS=()
GUARDS=()
for FILE in "${FILES[@]}"; do
    if [ ! -r "$FILE" ]; then echo "whitelist.sh: cannot read $FILE" >&2; exit 1; fi
done
if [ ${#FILES[@]} -gt 0 ]; then
    while read -r MODE WPATH; do
        case $MODE in
            '' | '#'*) continue ;;
            dbus-system)
                read -r NAME RULE <<< "$WPATH"
                if [ -n "$NAME" ] && [ -n "$RULE" ]; then CALLS+=("--call=$NAME=$RULE"); fi
                continue ;;
        esac
        WPATH=${WPATH/#\~/$HOME}
        if [ ! -e "$WPATH" ]; then continue; fi
        if [[ $MODE == r[ow] && -S $WPATH ]]; then
            echo "whitelist.sh: $WPATH is a socket, which $MODE cannot restrict, skipped" >&2
            continue
        fi
        case $MODE in
            ro) args+=(--ro-bind "$WPATH" "$WPATH") ;;
            rw) args+=(--bind "$WPATH" "$WPATH") ;;
            private)
                if [ -d "$WPATH" ]; then args+=(--overlay-src "$WPATH" --tmp-overlay "$WPATH")
                else echo "whitelist.sh: $WPATH is not a folder, which private cannot overlay, skipped" >&2; fi ;;
            guard) GUARDS+=("$WPATH") ;;
        esac
    done < <(cat -- "${FILES[@]}")
fi
if [ -d "${TMPDIR:-}" ]; then args+=(--bind "$TMPDIR" "$TMPDIR"); fi
if [ -e /.realgit ]; then args+=(--ro-bind /.realgit "$(readlink -f "$(command -v git)")"); fi
# [5] empty covers: X11, Claude daemon sockets, ssh drop-ins
for d in /tmp/.X11-unix "/tmp/cc-daemon-$UID" /etc/ssh/ssh_config.d; do
    if [ -d "$d" ]; then args+=(--tmpfs "$d" --remount-ro "$d"); fi
done
# [6] system bus: the dbus-system calls through xdg-dbus-proxy, which ends once the sandbox lets go of its sync fd
if [ ${#CALLS[@]} -gt 0 ]; then
    if ! command -v xdg-dbus-proxy > /dev/null; then
        echo "whitelist.sh: xdg-dbus-proxy is missing, no system bus" >&2
    elif BUS=$(mktemp -d "${XDG_RUNTIME_DIR:-/tmp}/saddler-bus.XXXXXX" 2> /dev/null || mktemp -d /tmp/saddler-bus.XXXXXX); then
        exec {SYNC}< <({ xdg-dbus-proxy --fd=1 "${DBUS_SYSTEM_BUS_ADDRESS:-unix:path=/run/dbus/system_bus_socket}" \
                             "$BUS/socket" --filter "${CALLS[@]}"; rm -rf "$BUS"; } < /dev/null 2> /dev/null)
        READY=''
        read -r -n 1 -u "$SYNC" READY || true
        if [ "$READY" = x ]; then
            args+=(--bind "$BUS/socket" /run/dbus/system_bus_socket --sync-fd "$SYNC"
                   --setenv DBUS_SYSTEM_BUS_ADDRESS unix:path=/run/dbus/system_bus_socket)
        else
            echo "whitelist.sh: xdg-dbus-proxy did not start, no system bus" >&2
        fi
    fi
fi
# [7] the BWRAP_OPTIONs, as given
args+=("${OPTIONS[@]}")
# [8] the .claude folders of the guard lines, read-only, after the options so they also cover what those mounted
for GUARD in "${GUARDS[@]}"; do
    while IFS= read -r -d '' P; do args+=(--ro-bind "$P" "$P"); done < <(claudes "$GUARD")
    wait $! || { echo "whitelist.sh: cannot scan $GUARD" >&2; exit 1; }
done
exec bwrap "${args[@]}" --remount-ro / -- "$@"
