# /// script
# requires-python = ">=3.11"
# dependencies = ["tree-sitter", "tree-sitter-bash"]
# ///
"""Bash guard built on the index as a snapshot. Wire to PreToolUse and PostToolUse.

  (0) Not a git repo                -> no guard, default behavior.
  (1) PreToolUse
      - a bare non-compound `git ARGS` is exempt: no staging, no restore.
      - a command that touches git any other way is denied, so git state
        manipulation stays a separate step.
      - otherwise, if the pending change set is >= 5 MB, deny and hand
        staging to the model.
      - otherwise `git add -A`, making the index the pre-command snapshot.
  (2) PostToolUse
      - `git restore --worktree` puts the work tree back to that snapshot.

The repo is anchored to CLAUDE_PROJECT_DIR, the directory the session started
in, so a `cd` inside a command cannot move the guard to another repo.

`git add -A` does not stage ignored files, which bounds the snapshot to
version-controlled content. Files the command creates are untracked and are
NOT removed by the restore -- see KNOWN GAPS at the bottom of this file.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time

import tree_sitter_bash
from tree_sitter import Language, Parser

MAX_CHANGESET = 5 * 1024 * 1024
VCS_NAMES = {"git", "hg", "svn", "jj", "bzr"}

# git options that make git run a command of its own choosing
GIT_EXEC_OPTS = ("-c", "--config-env", "--exec-path")

# a word whose runtime value is not knowable from the string
UNRESOLVED = {"simple_expansion", "expansion", "command_substitution",
              "arithmetic_expansion", "process_substitution"}
GLOB_CHARS = set("*?[")

PARSER = Parser(Language(tree_sitter_bash.language()))


# --------------------------------------------------------------------------
# git plumbing
# --------------------------------------------------------------------------

def git(root, *args):
    return subprocess.run(["git", "-C", root, *args],
                          capture_output=True, text=True)


def toplevel(start):
    r = subprocess.run(["git", "-C", start, "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def untracked(root):
    """Untracked, non-ignored files.

    Called at step 2, after step 1 staged everything that already existed, so
    anything still untracked was created by the command. `git clean -f` is not
    used: it does not descend into a directory the command created, and `-fd`
    would also delete the directories themselves.
    """
    r = git(root, "ls-files", "--others", "--exclude-standard", "-z")
    if r.returncode != 0:
        return []
    return [p for p in r.stdout.split("\0") if p]


def pending(root):
    """(paths, total_bytes) that `git add -A` would stage. Ignored files are
    excluded by git itself, so the snapshot stays inside version control."""
    r = git(root, "status", "--porcelain=v1", "-z", "-uall")
    if r.returncode != 0:
        raise RuntimeError("git status failed: " + r.stderr.strip())
    paths, fields, i = [], r.stdout.split("\0"), 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if len(entry) < 4:
            continue
        code, path = entry[:2], entry[3:]
        if code[0] in "RC":
            i += 1                       # rename source follows
        paths.append(path)
    total = 0
    for p in paths:
        full = os.path.join(root, p)
        if os.path.isfile(full):
            total += os.path.getsize(full)
    return paths, total


# --------------------------------------------------------------------------
# classifying the command
# --------------------------------------------------------------------------

def resolved(node, src):
    if node.type in UNRESOLVED:
        return False
    if node.type == "word" and set(
            src[node.start_byte:node.end_byte].decode()) & GLOB_CHARS:
        return False
    return all(resolved(c, src) for c in node.children)


def literal(node, src):
    if node.type == "raw_string":
        return src[node.start_byte:node.end_byte].decode()[1:-1]
    if node.type in ("string", "concatenation"):
        if node.children:
            return "".join(literal(c, src) for c in node.children
                           if c.type not in ('"', "'"))
    return src[node.start_byte:node.end_byte].decode()


def walk(node):
    yield node
    for c in node.children:
        yield from walk(c)


def head_of(command_node, src):
    for c in command_node.named_children:
        if c.type == "command_name":
            inner = c.named_children[0] if c.named_children else c
            return literal(inner, src), resolved(inner, src)
    return None, True


def classify(command):
    """-> ("exempt", argv) | ("guard", None) | ("deny", reason)"""
    src = command.encode()
    tree = PARSER.parse(src)
    root = tree.root_node

    commands = [n for n in walk(root) if n.type == "command"]
    heads = []
    for c in commands:
        name, ok = head_of(c, src)
        if name is not None:
            heads.append((os.path.basename(name) if ok else name, c))

    touches_vcs = [h for h, _ in heads if h in VCS_NAMES]
    if not touches_vcs:
        return "guard", None

    # a git command qualifies for exemption only as the whole command line:
    # one simple command, no pipe, no redirect, no background, no compound,
    # every word literal.
    bodies = [c for c in root.named_children if c.type != "comment"]
    single = (not root.has_error
              and len(bodies) == 1
              and bodies[0].type == "command"
              and len(commands) == 1
              and not any(n.type in ("file_redirect", "pipeline", "&", ";",
                                     "list", "subshell", "compound_statement",
                                     "heredoc_redirect", "herestring_redirect")
                          for n in walk(root)))
    if not single:
        return ("deny", "this command mixes git with other shell work; run "
                        "git commands on their own so git state is changed "
                        "in a separate step")

    node = bodies[0]
    argv = []
    for child in node.named_children:
        if child.type == "variable_assignment":
            return ("deny", "a git command with environment assignments is "
                            "not exempt; run it on its own")
        if child.type == "command_name":
            inner = child.named_children[0] if child.named_children else child
            argv.append(literal(inner, src))
        else:
            if not resolved(child, src):
                return ("deny", "a git command with an expansion or glob "
                                "cannot be recognized; write it out literally")
            argv.append(literal(child, src))

    for opt in argv[1:]:
        if opt in GIT_EXEC_OPTS or opt.startswith(tuple(o + "=" for o in GIT_EXEC_OPTS)):
            return ("deny", "`git %s` can run a command of its own; not "
                            "exempt" % opt)
    return "exempt", argv


# --------------------------------------------------------------------------
# state carried from pre to post
# --------------------------------------------------------------------------

def guard_dir(root):
    """A state directory of its own for each project path.

    Two checkouts of the same repo, or two unrelated projects, never share a
    directory: the readable slug is for humans, the digest of the resolved
    path is what actually keeps them apart.
    """
    real = os.path.realpath(root)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", os.path.basename(real)).strip("-")
    digest = hashlib.sha256(real.encode()).hexdigest()[:12]
    d = os.path.join(tempfile.gettempdir(), "claude-bash-stage-guard",
                     "%s-%s" % (slug or "root", digest))
    os.makedirs(d, exist_ok=True)
    return d


def state_path(payload, root):
    return os.path.join(guard_dir(root), owner(payload) + ".json")


def owner(payload):
    key = payload.get("tool_use_id") or payload.get("session_id") or "default"
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in key)


# --------------------------------------------------------------------------
# one command at a time per repository
#
# The index and the work tree are a single shared slot, and steps 1 and 2
# assume nothing else writes between them. A second session -- or the same
# session's next command -- must not stage or restore inside that window, so
# the lock is taken before staging and released after the restore.
#
# It cannot be an flock: pre, the command, and post are three separate
# processes, and an flock dies with the process that took it. So it is a
# lock file created with O_EXCL, carrying the owner and a timestamp, stolen
# only once it is older than a command could plausibly still be running.
# --------------------------------------------------------------------------

LOCK_WAIT = 15.0        # how long a command waits for another to finish
LOCK_STALE = 900.0      # a lock older than this is treated as abandoned


def lock_path(root):
    return os.path.join(guard_dir(root), "lock")


def acquire(root, payload):
    path = lock_path(root)
    me = owner(payload)
    deadline = time.time() + LOCK_WAIT
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump({"owner": me, "at": time.time(),
                           "session": payload.get("session_id")}, f)
            return True
        except FileExistsError:
            try:
                with open(path) as f:
                    held = json.load(f)
                age = time.time() - float(held.get("at", 0))
            except (OSError, ValueError, TypeError):
                age = LOCK_STALE + 1          # unreadable lock is abandoned
            if age > LOCK_STALE:
                try:
                    os.unlink(path)
                except OSError:
                    pass
                continue
            if time.time() >= deadline:
                return False
            time.sleep(0.05)


def release(root, payload):
    path = lock_path(root)
    try:
        with open(path) as f:
            held = json.load(f)
    except (OSError, ValueError):
        return
    if held.get("owner") == owner(payload):    # never drop someone else's
        try:
            os.unlink(path)
        except OSError:
            pass


def emit(obj):
    json.dump(obj, sys.stdout)


def deny(reason):
    emit({
        "systemMessage": "Bash blocked: " + reason.split("\n")[0],
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason + "\nThe command was not run.",
        },
    })


# --------------------------------------------------------------------------

def save(payload, root, state):
    with open(state_path(payload, root), "w") as f:
        json.dump(state, f)


def pre(payload, root):
    top = toplevel(root)
    if top is None:                                        # step 0
        save(payload, root, {"mode": "no-repo"})
        return

    # every command that reaches git state -- staging, restoring, or an
    # exempt git command touching the index -- runs alone in this repo
    if not acquire(root, payload):
        save(payload, root, {"mode": "denied"})
        deny("another session is running a command in this repository and "
             "has not finished. The work tree is mid-snapshot, so running "
             "now could revert its work. Retry in a moment.")
        return

    def refuse(reason):
        release(root, payload)
        save(payload, root, {"mode": "denied"})
        deny(reason)

    verdict, extra = classify(
        (payload.get("tool_input") or {}).get("command", ""))
    if verdict == "deny":
        refuse(extra)
        return
    if verdict == "exempt":                    # git command, index is its own
        save(payload, root, {"mode": "exempt", "locked": True})
        return

    paths, total = pending(top)                            # step 1a
    if total >= MAX_CHANGESET:
        refuse("the pending change set is %.1f MB across %d files, at or over "
               "the %d MB automatic-staging limit. Stage or commit what should "
               "be kept first, then re-run."
               % (total / 1e6, len(paths), MAX_CHANGESET // (1024 * 1024)))
        return

    r = git(top, "add", "-A")                              # step 1b
    if r.returncode != 0:
        refuse("could not stage the work tree (%s)" % r.stderr.strip())
        return
    save(payload, root, {"mode": "guard", "top": top, "locked": True})


def post(payload, root):
    try:
        with open(state_path(payload, root)) as f:
            state = json.load(f)
    except (OSError, ValueError):
        return                       # no snapshot -> nothing to restore to
    try:
        os.unlink(state_path(payload, root))
    except OSError:
        pass
    try:
        if state.get("mode") == "guard":
            restore(state, payload, root)
    finally:
        if state.get("locked"):      # exempt commands hold it too
            release(root, payload)


def restore(state, payload, root):
    top = state["top"]
    modified = [p for p in git(top, "diff", "--name-only").stdout.splitlines()
                if p.strip()]
    created = untracked(top)
    if not modified and not created:
        return

    lines = []

    if modified:                                           # step 2, revert
        r = git(top, "restore", "--worktree", "--", ".")
        if r.returncode != 0:
            emit({"systemMessage": "guard could not restore the work tree",
                  "hookSpecificOutput": {
                      "hookEventName": "PostToolUse",
                      "additionalContext":
                          "The work tree was staged before this command but "
                          "could not be restored afterwards (%s). The "
                          "command's changes are still in place."
                          % r.stderr.strip()}})
            return
        lines += ["reverted %s" % p for p in modified]

    for p in created:                    # step 2, remove created files only
        try:
            os.unlink(os.path.join(top, p))
            lines.append("removed %s (created by the command)" % p)
        except OSError as e:
            lines.append("could NOT remove %s (%s)" % (p, e))

    emit({
        "systemMessage": "Undid %d file change(s) made by the command" % len(lines),
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext":
                "The work tree was put back to its state before this command:"
                "\n  " + "\n  ".join(lines) +
                "\nDirectories the command created were left in place. Use the "
                "Edit or Write tool to change files, or run a separate git "
                "command first to record what should be kept.",
        },
    })


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return
    if (payload.get("tool_name") or "") != "Bash":
        return
    root = (os.environ.get("CLAUDE_PROJECT_DIR")
            or payload.get("cwd") or os.getcwd())
    event = payload.get("hook_event_name")
    try:
        if event == "PreToolUse":
            pre(payload, root)
        else:
            post(payload, root)
    except Exception as e:
        if event == "PreToolUse":
            deny("the guard failed (%s: %s)" % (type(e).__name__, e))


if __name__ == "__main__":
    main()

# KNOWN GAPS -- verified, not closed by these rules:
#   * a write into a gitignored path is neither staged nor restored, and is
#     excluded from the untracked sweep too. Reaching it would need
#     `git clean -fdx`, which also destroys .env, .venv and node_modules.
#   * a backgrounded command returns before it writes, so step 2 runs against
#     a work tree the command has not touched yet.
#   * a write outside the repo is out of scope by rule (0).
#   * a file created inside a directory the command also created is removed,
#     but the directory is left behind, by choice: only files are reverted.
#   * step 1 `git add -A` flattens a partial `git add -p` selection. Accepted:
#     whatever is written is meant for the next commit, and anything that must
#     never be committed belongs in .gitignore.
#   * the lock only serializes writers that take it, which is Bash commands.
#     A write that does not pass through this hook -- the Edit and Write tools,
#     an editor, any other process -- landing between step 1 and step 2 is
#     read as this command's output: a modification is reverted and a new file
#     is removed. Verified as C1 and C2. Closing it means taking the same lock
#     from a PreToolUse/PostToolUse hook on Edit and Write.
