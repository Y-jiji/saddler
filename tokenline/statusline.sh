#!/usr/bin/env bash
# Claude Code status line: <TOKEN COUNT> @ <FOLDER> (<BRANCH>) [<ROLE>]

input=$(cat)

tokens=$(jq -r '.context_window.total_input_tokens // 0' <<<"$input")
dir=$(jq -r '.workspace.current_dir // .cwd // ""' <<<"$input")
session=$(jq -r '.session_id // ""' <<<"$input")
session=${session:-${CLAUDE_CODE_SESSION_ID:-}}

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

# fileguard's role for this session: fork, owner, or none when it has claimed nothing
role=''
root=$(git -C "${dir:-.}" rev-parse --show-toplevel 2>/dev/null)
if [ -n "$root" ] && [ -n "$session" ]; then
  lock="$HOME/.claude/sandbox/project-$(jq -rn --arg path "$(readlink -f "$root")" '$path | @uri')/lock"
  owner=''
  { read -r _ owner < "$lock/owner.info"; } 2>/dev/null
  if [ -s "$lock/$session-master" ]; then
    role=fork
  elif [ "$owner" = "$session" ]; then
    role=owner
  fi
fi

printf '%s @ %s' "$(fmt_tokens "$tokens")" "$(short_dir "$dir")"
[ -n "$branch" ] && printf ' (%s)' "$branch"
[ -n "$role" ] && printf ' [%s]' "$role"
printf '\n'
