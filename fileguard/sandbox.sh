#!/usr/bin/env bash
# CLAUDE_CODE_SHELL_PREFIX: Claude Code runs `sandbox.sh '<invocation>'` for
# every shell it starts. When pretoolusewrite.py has tagged the command, the
# invocation runs in bwrap on an empty root that holds only the paths below;
# otherwise it runs as if there were no prefix.
#
# The tag is a comment on the first line of the command, inside Claude Code's
# wrapper in $1, and never reaches the shell:
#   ... eval '# saddler root=<percent-encoded path, / too> session=<id> agent=<id>
#   <command>' ...
# Only a subagent has an agent; its project is a private overlay.
#
# No overlay may be mounted while its lower folder changes, so each project has
# a mode lock in lock/<encoded root>/: one mode at a time, subagents or one
# session's main, and calls in that mode run together. A call waits its turn in
# the queue and fails after SADDLER_WAIT seconds. Each call holds its mode until
# its last process, background ones included, exits.
#
# ~/.claude/sandbox/ holds the global registry `allow` (lines `ro PATH` or
# `rw PATH`, ~ expanded), the private ~/.ssh, the mode locks and the overlays,
# overlay/<session>/<agent>/{upper,work,lock,base}. A subagent cannot see overlay/.
#
# Later binds cover earlier ones, so the order of the steps is the policy.
set -euo pipefail
: "${HOME:=$(getent passwd "$UID" | cut -d: -f6)}"
box=$HOME/.claude/sandbox

# [1] split the tag line out of $1; without one, run unsandboxed
tagre=$'^([^\n]*)# saddler ([^\n]*)\n(.*)$'
if [[ ! $1 =~ $tagre ]]; then
    exec bash -c -- "$1"
fi
run=${BASH_REMATCH[1]}${BASH_REMATCH[3]}
read -ra words <<<"${BASH_REMATCH[2]}"
encoded='' session='' agent=''
for word in "${words[@]}"; do
    case $word in
        root=*) encoded=${word#root=} ;;
        session=*) session=${word#session=} ;;
        agent=*) agent=${word#agent=} ;;
    esac
done
printf -v root '%b' "${encoded//%/\\x}"
if [[ $root != /* || ! -d $root ]]; then
    echo "sandbox.sh: no project at '$root'" >&2
    exit 1
fi
# the same check for both, so no path can be spliced into a lock or overlay path
idre='^[A-Za-z0-9_@-][A-Za-z0-9_@.-]*$'
if [[ ! $session =~ $idre || ( -n $agent && ! $agent =~ $idre ) ]]; then
    echo "sandbox.sh: bad session or agent name '$session/$agent'" >&2
    exit 1
fi

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

# [3b] every dot entry in ~, read-only, so tools find their config
for e in "$HOME"/.[!.]*; do
    if [ -e "$e" ] && [ ! -L "$e" ]; then args+=(--ro-bind "$e" "$e"); fi
done

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
#     .git that is a file and every .claude, nested ones included; a subagent
#     writes to its own overlay
if [ -n "$agent" ]; then
    layer=$box/overlay/$session/$agent
    mkdir -p "$layer/upper" "$layer/work"
    args+=(--overlay-src "$root" --overlay "$layer/upper" "$layer/work" "$root")
else
    args+=(--bind "$root" "$root")
fi
while IFS= read -r -d '' p; do
    args+=(--ro-bind "$p" "$p")
done < <(find "$root" ! -type l \
    \( \( -name .claude -o -name .git -type f \) -prune -print0 \
    -o -path '*/.git/*' \( -name config -o -name hooks \) -prune -print0 \))
wait $! || { echo "sandbox.sh: cannot scan $root for read-only paths" >&2; exit 1; }

# [6] empty covers: the X11 and Claude Code daemon sockets, and the ssh
#     drop-ins ssh rejects, since their root owner shows as nobody in here;
#     for a subagent, every overlay
for d in /tmp/.X11-unix "/tmp/cc-daemon-$UID" /etc/ssh/ssh_config.d; do
    if [ -d "$d" ]; then args+=(--tmpfs "$d" --remount-ro "$d"); fi
done
if [ -n "$agent" ]; then
    args+=(--tmpfs "$box/overlay" --remount-ro "$box/overlay")
fi

# [7] ~/.ssh as a private directory with the real entries read-only inside,
#     so ssh can leave ControlMaster sockets for later calls
if [ -d "$HOME/.ssh" ] && [ ! -L "$HOME/.ssh" ]; then
    mkdir -p -m 700 "$box/ssh"
    args+=(--bind "$box/ssh" "$HOME/.ssh")
    for e in "$HOME"/.ssh/* "$HOME"/.ssh/.[!.]*; do
        if [ -e "$e" ]; then args+=(--ro-bind "$e" "$e"); fi
    done
fi

# [7b] the mode lock: a subagent's calls first queue on its overlay, which only
#      one mount can use; then, holding the queue so nobody overtakes, join this
#      mode and wait out every other one; fds 195 and 197 stay with the command
wait=${SADDLER_WAIT:-100}
deadline=$((SECONDS + wait))
left() { local n=$((deadline - SECONDS)); echo $((n > 0 ? n : 0)); }
refuse() { echo "sandbox.sh: waited ${wait}s for $1 to finish" >&2; exit 1; }
lock=$box/lock/${encoded//\//%2F}
mkdir -p "$lock"
if [ -n "$agent" ]; then
    exec 195>"$layer/lock"
    flock -w "$(left)" 195 || refuse "this agent's other commands"
    own=$lock/mode.sub
else
    own=$lock/mode.main.$session
fi
exec 196>"$lock/queue"
flock -w "$(left)" 196 || refuse "earlier commands"
exec 197>"$own"
flock -s 197
for f in "$lock"/mode.*; do
    if [ "$f" = "$own" ]; then continue; fi
    flock -w "$(left)" -x "$f" true || refuse "${f##*mode.} commands"
done
exec 196>&-
# a subagent's first call records HEAD, now that the project cannot be mid-commit
if [ -n "$agent" ] && [ ! -e "$layer/base" ]; then
    git -C "$root" rev-parse --verify -q HEAD > "$layer/base" 2>/dev/null || true
fi

# [8] freeze the rest of the root and run the invocation
args+=(--remount-ro / --chdir "$PWD")
exec bwrap "${args[@]}" bash -c -- "$run"
