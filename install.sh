#!/usr/bin/env bash
# Install every folder holding a SKILL.md as a personal Claude Code skill
# (hard copy, no symlink).
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"

for SKILL in "$SRC"/*/SKILL.md; do
    DIR="$(dirname "$SKILL")"
    NAME="$(sed -n '/^---$/,/^---$/{s/^name:[[:space:]]*//p}' "$SKILL" | head -1)"
    [ -n "$NAME" ] || { echo "no 'name' in $SKILL frontmatter" >&2; exit 1; }
    DEST="$SKILLS/$NAME"

    if [ -e "$DEST" ]; then
        printf 'overwrite %s? [y/N] ' "$DEST"
        read -r reply
        case "$reply" in [yY]*) ;; *) echo "skipped $NAME"; continue;; esac
        rm -rf "$DEST"
    fi

    mkdir -p "$DEST"
    tar -C "$DIR" --exclude='__pycache__' -cf - . | tar -C "$DEST" -xf -
    echo "installed $NAME -> $DEST"
done
