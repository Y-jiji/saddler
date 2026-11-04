#!/bin/bash
# gitwrap.sh GIT_ARGS...
if [ -n "${GIT_HELD:-}" ]; then exec /.realgit "$@"; fi
export GIT_HELD=1
eval "exec $GIT_WRAPPER \"\$@\""
