#!/bin/bash
# gitwrap.sh GIT_ARGS...
if [ "${0##*/}" != git ]; then exec -a "${0##*/}" /.realgit "$@"; fi
if [ -n "${GIT_HELD:-}" ]; then exec /.realgit "$@"; fi
export GIT_HELD=1
eval "exec $GIT_WRAPPER \"\$@\""
