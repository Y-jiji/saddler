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

import json
import os
import subprocess
import sys
import tempfile

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

def state_path(payload):
    d = os.path.join(tempfile.gettempdir(), "claude-bash-stage-guard")
    os.makedirs(d, exist_ok=True)
    key = payload.get("tool_use_id") or payload.get("session_id") or "default"
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in key)
    return os.path.join(d, safe + ".json")


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

def pre(payload, root):
    top = toplevel(root)
    if top is None:                                        # step 0
        json.dump({"mode": "no-repo"}, open(state_path(payload), "w"))
        return

    verdict, extra = classify(
        (payload.get("tool_input") or {}).get("command", ""))
    if verdict == "deny":
        json.dump({"mode": "denied"}, open(state_path(payload), "w"))
        deny(extra)
        return
    if verdict == "exempt":                                # step 1, git
        json.dump({"mode": "exempt"}, open(state_path(payload), "w"))
        return

    paths, total = pending(top)                            # step 1a
    if total >= MAX_CHANGESET:
        json.dump({"mode": "denied"}, open(state_path(payload), "w"))
        deny("the pending change set is %.1f MB across %d files, at or over "
             "the %d MB automatic-staging limit. Stage or commit what should "
             "be kept first, then re-run."
             % (total / 1e6, len(paths), MAX_CHANGESET // (1024 * 1024)))
        return

    r = git(top, "add", "-A")                              # step 1b
    if r.returncode != 0:
        json.dump({"mode": "denied"}, open(state_path(payload), "w"))
        deny("could not stage the work tree (%s)" % r.stderr.strip())
        return
    json.dump({"mode": "guard", "top": top}, open(state_path(payload), "w"))


def post(payload):
    try:
        with open(state_path(payload)) as f:
            state = json.load(f)
    except (OSError, ValueError):
        return                       # no snapshot -> nothing to restore to
    try:
        os.unlink(state_path(payload))
    except OSError:
        pass
    if state.get("mode") != "guard":
        return

    top = state["top"]
    changed = [p for p in git(top, "diff", "--name-only").stdout.splitlines()
               if p.strip()]
    if not changed:
        return
    r = git(top, "restore", "--worktree", "--", ".")        # step 2
    if r.returncode != 0:
        emit({"systemMessage": "guard could not restore the work tree",
              "hookSpecificOutput": {
                  "hookEventName": "PostToolUse",
                  "additionalContext":
                      "The work tree was staged before this command but could "
                      "not be restored afterwards (%s). The command's file "
                      "changes are still in place." % r.stderr.strip()}})
        return

    msg = ("Reverted %d file(s) this command modified, back to the state "
           "before it ran:\n  %s" % (len(changed), "\n  ".join(changed)))
    emit({
        "systemMessage": "Reverted %d file(s) modified by the command" % len(changed),
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": msg + "\nUse the Edit or Write tool to change "
                                       "files, or stage your intent with a "
                                       "separate git command first.",
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
            post(payload)
    except Exception as e:
        if event == "PreToolUse":
            deny("the guard failed (%s: %s)" % (type(e).__name__, e))


if __name__ == "__main__":
    main()

# KNOWN GAPS -- verified, not closed by these rules:
#   * a file the command CREATES is untracked, and `git restore` does not
#     remove untracked files, so creations survive. Closing this needs
#     `git clean -fd`, which also deletes legitimate command output.
#   * a write into a gitignored path is neither staged nor restored, and
#     `git clean -fd` would not remove it either (only `-x` would, which
#     also destroys .env, .venv and node_modules).
#   * a backgrounded command returns before it writes, so the restore runs
#     against a work tree the command has not touched yet.
#   * a write outside the repo is out of scope by rule (0).
