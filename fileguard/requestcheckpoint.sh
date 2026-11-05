#!/bin/bash
# requestcheckpoint.sh DEFAULT_BRANCH
# git checkpoint, inside an agent's view: build the view, then ask through a file
# in the private .git that it become everyone's base when this command ends.
DEFAULT=$1

# [1] refuse unless the working tree is clean
if [ -n "$(git status --porcelain)" ]; then
    echo "git checkpoint: commit or discard your changes first" >&2
    exit 1
fi

# [2] refuse unless the default branch can fast-forward to HEAD
if ! git merge-base --is-ancestor "refs/remotes/saddler/$DEFAULT" HEAD 2>/dev/null; then
    echo "git checkpoint: merge saddler/$DEFAULT first, it must fast-forward to HEAD" >&2
    exit 1
fi

# [3] build the view; a failed build asks for nothing
if [ -n "${SADDLER_BUILD:-}" ] && ! bash -c -- "$SADDLER_BUILD"; then
    echo "git checkpoint: SADDLER_BUILD failed, no checkpoint" >&2
    exit 1
fi

# [4] ask
git rev-parse HEAD > "$(git rev-parse --git-dir)/checkpoint" || exit 1
echo "git checkpoint: requested, it runs when this command ends" >&2
