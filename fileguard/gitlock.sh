#!/bin/bash
# gitlock.sh LOCK_FOLDER read|write WAIT_SECONDS COMMAND...
LOCK_FOLDER=$1
MODE=$2
WAIT_SECONDS=$3
shift 3
exec 196<"$LOCK_FOLDER/queue" || exit 1
flock -w "$WAIT_SECONDS" 196 || { echo "gitlock.sh: waited ${WAIT_SECONDS}s for other commands to finish" >&2; exit 1; }
exec 197<"$LOCK_FOLDER/mode" || exit 1
if [ "$MODE" = write ]; then FLAG=-x; else FLAG=-s; fi
flock -w "$WAIT_SECONDS" "$FLAG" 197 || { echo "gitlock.sh: waited ${WAIT_SECONDS}s for other commands to finish" >&2; exit 1; }
exec 196<&-
"$@" 197<&-
exit $?
