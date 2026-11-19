#!/usr/bin/env bash
# Claude Code status line: <TOKEN COUNT> @ <FOLDER> (session-<SESSION>)
# A session without its fileguard folder shows (<BRANCH>) instead.

input=$(cat)

tokens=$(jq -r '.context_window.total_input_tokens // 0' <<<"$input")
dir=$(jq -r '.workspace.current_dir // .cwd // ""' <<<"$input")
project=$(jq -r '.workspace.project_dir // .cwd // ""' <<<"$input")
session=$(jq -r '.session_id // ""' <<<"$input")

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

# the main agent's view branch when the project's .git/saddler holds the session folder
label=''
root=$(git -C "${project:-.}" rev-parse --show-toplevel 2>/dev/null || printf '%s' "$project")
if [[ $session =~ ^[A-Za-z0-9-]+$ ]] && [ -d "$root/.git/saddler/session-$session" ]; then
  label=session-$session
fi
if [ -z "$label" ]; then
  label=$(git -C "${dir:-.}" branch --show-current 2>/dev/null)
fi
if [ -z "$label" ]; then
  # detached HEAD -> short sha
  label=$(git -C "${dir:-.}" rev-parse --short HEAD 2>/dev/null)
fi

printf '%s @ %s' "$(fmt_tokens "$tokens")" "$(short_dir "$dir")"
[ -n "$label" ] && printf ' (%s)' "$label"
printf '\n'
