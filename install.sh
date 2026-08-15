#!/usr/bin/env bash
# Install this folder as a personal Claude Code skill (hard copy, no symlink).
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAME="$(sed -n '/^---$/,/^---$/{s/^name:[[:space:]]*//p}' "$SRC/SKILL.md" | head -1)"
[ -n "$NAME" ] || { echo "no 'name' in SKILL.md frontmatter" >&2; exit 1; }

DEST="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}/$NAME"

if [ -e "$DEST" ]; then
    printf 'overwrite %s? [y/N] ' "$DEST"
    read -r reply
    case "$reply" in [yY]*) ;; *) echo "aborted"; exit 1;; esac
    rm -rf "$DEST"
fi

mkdir -p "$DEST"
tar -C "$SRC" \
    --exclude='.git' \
    --exclude='.claude' \
    --exclude='install.sh' \
    -cf - . | tar -C "$DEST" -xf -

echo "installed $NAME -> $DEST"
