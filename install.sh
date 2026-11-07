#!/usr/bin/env bash
# install.sh [NAME...]
# Install every folder holding a SKILL.md as a personal Claude Code skill
# (hard copy, no symlink), or only the skills named by their SKILL.md name;
# a named skill is overwritten without asking.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"

# the skills by name; an unknown NAME installs nothing
NAMES=()
declare -A DIRS=() WANT=()
for SKILL in "$SRC"/*/SKILL.md; do
    NAME="$(sed -n '/^---$/,/^---$/{s/^name:[[:space:]]*//p}' "$SKILL" | head -1)"
    [ -n "$NAME" ] || { echo "no 'name' in $SKILL frontmatter" >&2; exit 1; }
    NAMES+=("$NAME")
    DIRS[$NAME]="$(dirname "$SKILL")"
done
for NAME in "$@"; do
    [ -n "${DIRS[$NAME]:-}" ] || { echo "install.sh: no skill named $NAME" >&2; exit 1; }
    WANT[$NAME]=1
done
ALL=$#
picked() { [ "$ALL" -eq 0 ] || [ -n "${WANT[$1]:-}" ]; }

# fileguard's shell scripts and registry, which run outside the project, and forkshell in ~/.bashrc
if picked fileguard; then
    SADDLER="$HOME/.claude/saddler"
    BOX="$HOME/.claude/sandbox"
    mkdir -p "$SADDLER" "$BOX"
    for NAME in sandbox allowlist overlayfork checkpoint requestcheckpoint forkshell; do
        install -m 755 "$SRC/fileguard/$NAME.sh" "$SADDLER/$NAME.sh"
    done
    rm -f "$SADDLER/gitlock.sh" "$SADDLER/gitwrap.sh" "$SADDLER/overlayowner.sh"
    [ -e "$BOX/whitelist.txt" ] || cp "$SRC/fileguard/whitelist.txt" "$BOX/whitelist.txt"
    echo "installed fileguard scripts -> $SADDLER"

    # forkshell in ~/.bashrc, as one marked block replaced on every run; writing through the path keeps a symlink
    BASHRC="$HOME/.bashrc"
    BEGIN='#>>>>>>>>>>>>>># saddler'
    END='#<<<<<<<<<<<<<<# saddler'
    TMP=$(mktemp)
    if [ -e "$BASHRC" ]; then
        awk -v b="$BEGIN" -v e="$END" '$0 == b { skip = 1; next } $0 == e { skip = 0; next } !skip' "$BASHRC" > "$TMP"
    fi
    printf '%s\n' "$BEGIN" 'forkshell() { "$HOME/.claude/saddler/forkshell.sh" "$@"; }' "$END" >> "$TMP"
    cat "$TMP" > "$BASHRC"
    rm -f "$TMP"
    echo "registered forkshell in $BASHRC"
fi

for NAME in "${NAMES[@]}"; do
    picked "$NAME" || continue
    DEST="$SKILLS/$NAME"

    if [ -e "$DEST" ]; then
        if [ "$ALL" -eq 0 ]; then
            printf 'overwrite %s? [y/N] ' "$DEST"
            read -r reply
            case "$reply" in [yY]*) ;; *) echo "skipped $NAME"; continue;; esac
        fi
        rm -rf "$DEST"
    fi

    mkdir -p "$DEST"
    tar -C "${DIRS[$NAME]}" --exclude='__pycache__' -cf - . | tar -C "$DEST" -xf -
    echo "installed $NAME -> $DEST"
done
