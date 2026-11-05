#!/usr/bin/env bash
# Claude Code status line: <TOKEN COUNT> @ <FOLDER> (<BRANCH>)

input=$(cat)

tokens=$(jq -r '.context_window.total_input_tokens // 0' <<<"$input")
dir=$(jq -r '.workspace.current_dir // .cwd // ""' <<<"$input")

# always in thousands, one decimal: 0 -> 0k, 1300 -> 1.3k, 1000700 -> 1000.7k
fmt_tokens() {
  awk -v n="$1" 'BEGIN {
    s = sprintf("%.1f", n / 1000)
    sub(/\.0$/, "", s)
    printf "%sk", s
  }'
}

# ~/foo when under $HOME, absolute path otherwise
short_dir() {
  case "$1" in
    "$HOME") printf '~' ;;
    "$HOME"/*) printf '~%s' "${1#"$HOME"}" ;;
    *) printf '%s' "$1" ;;
  esac
}

branch=$(git -C "${dir:-.}" branch --show-current 2>/dev/null)
if [ -z "$branch" ]; then
  # detached HEAD -> short sha
  branch=$(git -C "${dir:-.}" rev-parse --short HEAD 2>/dev/null)
fi

printf '%s @ %s' "$(fmt_tokens "$tokens")" "$(short_dir "$dir")"
[ -n "$branch" ] && printf ' (%s)' "$branch"
printf '\n'
