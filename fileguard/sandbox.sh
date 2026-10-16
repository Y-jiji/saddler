#!/usr/bin/env bash
# CLAUDE_CODE_SHELL_PREFIX: Claude Code runs `sandbox.sh '<invocation>'` for
# every shell it starts. When sessionstartsandbox.py has recorded a project
# root for this session, the invocation runs in bwrap on an empty root that
# holds only the paths below; otherwise it runs as if there were no prefix.
# $1 is never parsed.
#
# ~/.claude/sandbox/ holds the records (<session_id>, one line: the project
# root), the global registry `allow` (lines `ro PATH` or `rw PATH`, ~
# expanded) and the private ~/.ssh. None of it is visible inside.
#
# Later binds cover earlier ones, so the order of the steps is the policy.
set -euo pipefail
: "${HOME:=$(getent passwd "$UID" | cut -d: -f6)}"
box=$HOME/.claude/sandbox

# [1] look up this session's project root; without a record, run unsandboxed
sid=${CLAUDE_CODE_SESSION_ID:-}
if [[ ! $sid =~ ^[A-Za-z0-9-]+$ ]] || [ ! -f "$box/$sid" ]; then
    exec bash -c -- "$1"
fi
root=$(<"$box/$sid")

# [2] the base: host /dev, a fresh /proc, the top-level symlinks such as /bin
args=(--dev-bind /dev /dev --proc /proc)
for p in /*; do
    if [ -L "$p" ]; then args+=(--symlink "$(readlink "$p")" "$p"); fi
done

# [3] every library and PATH directory, read-only, so programs are found and
#     linked as outside; one under ~ brings its whole top-level entry
while IFS= read -r d; do
    if [[ $d != /* || ! -d $d || $d == / || $d == "$HOME" ]]; then continue; fi
    if [[ $d == "$HOME"/* ]]; then r=${d#"$HOME"/}; d=$HOME/${r%%/*}; fi
    args+=(--ro-bind "$d" "$d")
done < <({ ldconfig -p | sed -n 's|.* => \(.*\)/[^/]*$|\1|p'
           tr : '\n' <<<"${LD_LIBRARY_PATH:-}:$PATH"; } | sort -u)

# [4] the global registry, after [3] so its rw entries win; then $TMPDIR
while read -r mode path; do
    path=${path/#\~/$HOME}
    if [ ! -e "$path" ]; then continue; fi
    case $mode in
        ro) args+=(--ro-bind "$path" "$path") ;;
        rw) args+=(--bind "$path" "$path") ;;
    esac
done < "$box/allow"
if [ -d "${TMPDIR:-}" ]; then args+=(--bind "$TMPDIR" "$TMPDIR"); fi

# [5] the project, writable except config and hooks under every .git, every
#     .git that is a file and every .claude, nested ones included
args+=(--bind "$root" "$root")
while IFS= read -r -d '' p; do
    args+=(--ro-bind "$p" "$p")
done < <(find "$root" ! -type l \
    \( \( -name .claude -o -name .git -type f \) -prune -print0 \
    -o -path '*/.git/*' \( -name config -o -name hooks \) -prune -print0 \))
wait $! || { echo "sandbox.sh: cannot scan $root for read-only paths" >&2; exit 1; }

# [6] empty covers: the X11 and Claude Code daemon sockets, and the ssh
#     drop-ins ssh rejects, since their root owner shows as nobody in here
for d in /tmp/.X11-unix "/tmp/cc-daemon-$UID" /etc/ssh/ssh_config.d; do
    if [ -d "$d" ]; then args+=(--tmpfs "$d" --remount-ro "$d"); fi
done

# [7] ~/.ssh as a private directory with the real entries read-only inside,
#     so ssh can leave ControlMaster sockets for later calls
if [ -d "$HOME/.ssh" ] && [ ! -L "$HOME/.ssh" ]; then
    mkdir -p -m 700 "$box/ssh"
    args+=(--bind "$box/ssh" "$HOME/.ssh")
    for e in "$HOME"/.ssh/* "$HOME"/.ssh/.[!.]*; do
        if [ -e "$e" ]; then args+=(--ro-bind "$e" "$e"); fi
    done
fi

# [8] freeze the rest of the root and run the invocation
args+=(--remount-ro / --chdir "$PWD")
exec bwrap "${args[@]}" bash -c -- "$1"
