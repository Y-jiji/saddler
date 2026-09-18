# /// script
# requires-python = ">=3.11"
# dependencies = ["tree-sitter", "tree-sitter-bash"]
# ///
"""PreToolUse hook for Bash: run the command with only gitignored paths, /tmp
and dot entries in the home directory writable.

The whole filesystem is bind-mounted read-only into a private mount namespace,
then /tmp, every existing dot entry in ~ except those in HOME_DENY, and every
existing gitignored path in the repository are bound writable again, so the
kernel refuses any other write however the command reaches it -- a redirect,
sed -i, another interpreter, a script, a background child. Tracked files,
untracked files that are not ignored, and .git are all read-only. A tracked
file inside an ignored directory is bound read-only again. A dot entry that
does not exist yet cannot be created, since ~ itself is read-only.

Research folders directly under the repository root, named by WAIVED (#001,
#002, ...), are bound writable last, tracked files inside them included.

An ignored path that does not exist yet cannot be created unless its parent is
writable: a first `cargo build` cannot create target/.

The repository is found from CLAUDE_PROJECT_DIR, the directory the session
started in, so a `cd` cannot move the guard to another repository or out of
one. The command still runs in the directory it expects, via --chdir. Outside
a git repository only /tmp and the home dot entries are writable.

A simple git command (is_simple_git) gets the whole repository writable instead
-- git rewrites tracked files and .git on purpose, and a read-only bind makes
checkout and restore fail, sometimes while still reporting success. A simple
mkdir command (is_simple_mkdir) gets the same, so a new folder, such as the
next #NNN, can be created anywhere in the repository. Everything outside the
repository, /tmp and the home dot entries stays read-only for them too.

The hook rewrites the command through hookSpecificOutput.updatedInput.

The command is inlined as `bash -c <word>`, quoted into a single shell word, so
the transcript and the auto mode classifier see exactly what runs. The bind
list is written to a file and handed to bwrap by file descriptor, since it can
run to thousands of arguments.
"""

import json
import os
import re
import subprocess
import sys
import tempfile

import tree_sitter_bash
from tree_sitter import Language, Parser

# bwrap accepts 9000 arguments; each bind spends 3. Setup also grows faster
# than linearly: 19 ms at 146 binds, 181 ms at 636, 915 ms at 1500.
MAX_BINDS = 2900

# dot entries in ~ that stay read-only: they configure code run outside the
# sandbox
HOME_DENY = (".claude", ".bashrc", ".profile")

# research folders directly under the repository root that stay writable
WAIVED = re.compile(r"#\d{3}", re.ASCII)

# git options that let git run a command of its own choosing
GIT_EXEC_OPTS = ("-c", "--config-env", "--exec-path")

# node types meaning the command is more than one simple command
COMPOUND = {"pipeline", "list", "subshell", "compound_statement",
            "command_substitution", "process_substitution", "heredoc_redirect",
            "herestring_redirect", "file_redirect", "for_statement",
            "while_statement", "if_statement", "case_statement",
            "function_definition", "&", ";", "&&", "||"}

UNRESOLVED = {"simple_expansion", "expansion", "command_substitution",
              "arithmetic_expansion", "process_substitution"}
GLOB_CHARS = set("*?[")

_PARSER = Parser(Language(tree_sitter_bash.language()))


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


def _literal(node, src):
    if node.type == "raw_string":
        return src[node.start_byte:node.end_byte].decode()[1:-1]
    if node.type in ("string", "concatenation") and node.children:
        return "".join(_literal(c, src) for c in node.children
                       if c.type not in ('"', "'"))
    return src[node.start_byte:node.end_byte].decode()


def _resolved(node, src):
    if node.type in UNRESOLVED:
        return False
    if node.type == "word" and set(
            src[node.start_byte:node.end_byte].decode()) & GLOB_CHARS:
        return False
    return all(_resolved(c, src) for c in node.children)


def simple_argv(command):
    """The literal argv when the whole command line is one plain command,
    else None.

    Requires valid bash, a single command, no pipe, redirect, background,
    separator, subshell, substitution or heredoc, no leading VAR=value and
    every word a literal.
    """
    src = command.encode()
    root = _PARSER.parse(src).root_node
    if root.has_error:
        return None
    if any(n.type in COMPOUND for n in _walk(root)):
        return None

    bodies = [c for c in root.named_children if c.type != "comment"]
    if len(bodies) != 1 or bodies[0].type != "command":
        return None

    argv = []
    for child in bodies[0].named_children:
        if child.type == "variable_assignment":
            return None
        if child.type == "command_name":
            child = child.named_children[0] if child.named_children else child
        if not _resolved(child, src):
            return None
        argv.append(_literal(child, src))
    return argv or None


def is_simple_git(command):
    """True when the whole command line is one plain `git ARGS` invocation.

    Requires simple_argv, the program `git`, and no option that lets git
    execute something of its own.

    `git commit -m 'a message'` qualifies. `ls && git checkout main`,
    `git log > out.txt`, `git -c core.pager='rm x' log`, `git $CMD` do not.
    """
    argv = simple_argv(command)
    if not argv or os.path.basename(argv[0]) != "git":
        return False
    return not any(a in GIT_EXEC_OPTS
                   or a.startswith(tuple(o + "=" for o in GIT_EXEC_OPTS))
                   for a in argv[1:])


def is_simple_mkdir(command):
    """True when the whole command line is one plain `mkdir ARGS` invocation.

    Requires simple_argv and the program exactly `mkdir`, with no path, so a
    script named mkdir in a writable folder does not qualify.

    `mkdir -p '#004'` qualifies. `mkdir x && cd x`, `./mkdir x` do not.
    """
    argv = simple_argv(command)
    return bool(argv) and argv[0] == "mkdir"


def repo_root(cwd):
    r = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def ignored_paths(root):
    """Existing gitignored paths, an ignored directory given once as a whole.

    Symlinks are skipped: binding one resolves to its target, which may sit
    outside the repository. Submodules are not searched, so their work trees
    stay read-only.
    """
    r = subprocess.run(
        ["git", "-C", root, "ls-files", "-z", "--others", "--ignored",
         "--exclude-standard", "--directory"],
        capture_output=True, text=True)
    out = []
    for name in r.stdout.split("\0"):
        if not name:
            continue
        path = os.path.join(root, name.rstrip("/"))
        if os.path.exists(path) and not os.path.islink(path):
            out.append(path)
    return out


def tracked_files(root):
    """Existing regular tracked files, submodules included.

    --recurse-submodules descends to any depth once a submodule is
    initialized, and reports paths relative to the superproject. An
    uninitialized submodule contributes nothing, which is correct: its files
    are not on disk to freeze.

    Symlinks are skipped: binding one resolves to its target, which may sit
    outside the repository.
    """
    r = subprocess.run(
        ["git", "-C", root, "ls-files", "-z", "--recurse-submodules"],
        capture_output=True, text=True)
    out = []
    for name in r.stdout.split("\0"):
        if not name:
            continue
        path = os.path.join(root, name)
        if os.path.isfile(path) and not os.path.islink(path):
            out.append(path)
    return out


def workdir(payload):
    d = payload.get("scratchpad_dir") or tempfile.gettempdir()
    d = os.path.join(d, "edit-guard")
    os.makedirs(d, exist_ok=True)
    return d


def _quote(s):
    """`s` as one shell word, kept readable: '...' unless it holds a quote."""
    if "'" not in s:
        return "'%s'" % s
    return "$'%s'" % s.replace("\\", "\\\\").replace("'", "\\'")


def mounts(root, whole):
    """bwrap binds: all read-only, then /tmp, the home dot entries and the
    allowed repo paths writable, the WAIVED folders last.

    Later binds cover earlier ones, so the order is the policy. `root` is None
    outside a git repository; `whole` makes the whole repository writable.
    Only existing dot entries and WAIVED folders are bound, since bwrap fails
    on a missing source, and symlinks are skipped, since binding one resolves
    to its target.
    """
    args = ["--ro-bind", "/", "/", "--dev-bind", "/dev", "/dev",
            "--proc", "/proc", "--bind", "/tmp", "/tmp"]
    home = os.path.expanduser("~")
    for entry in sorted(os.scandir(home), key=lambda e: e.name):
        if (entry.name.startswith(".") and entry.name not in HOME_DENY
                and not entry.is_symlink()):
            args += ["--bind", entry.path, entry.path]
    if root is None:
        return args
    if whole:
        return args + ["--bind", root, root]

    # read-only again, in case the repository sits under /tmp
    args += ["--ro-bind", root, root]
    ignored = ignored_paths(root)
    for path in ignored:
        args += ["--bind", path, path]
    dirs = tuple(p + os.sep for p in ignored if os.path.isdir(p))
    for path in tracked_files(root):
        if path.startswith(dirs):
            args += ["--ro-bind", path, path]
    for entry in sorted(os.scandir(root), key=lambda e: e.name):
        if (WAIVED.fullmatch(entry.name) and entry.is_dir()
                and not entry.is_symlink()):
            args += ["--bind", entry.path, entry.path]
    return args


def rewrite(command, binds, cwd, payload):
    """The command line that runs `command` under `binds`.

    The command sits on bwrap's argv as `bash -c <word>`; the binds go into a
    file that bwrap reads from fd 9, so no path is spliced into the string.
    """
    d = workdir(payload)
    tag = payload.get("tool_use_id") or "cmd"
    tag = "".join(c if c.isalnum() or c in "-_" else "_" for c in tag)

    # bwrap --args carries OPTIONS only; the command has to sit on the real
    # argv, and the binds go in the file
    args = binds + ["--chdir", cwd]

    argfile = os.path.join(d, tag + ".args")
    with open(argfile, "wb") as f:
        f.write("\0".join(args).encode())

    # $0 is set so the command's own $1, $2... are not shifted
    return "bwrap --args 9 bash -c %s edit-guard 9<%s" % (_quote(command),
                                                          argfile)


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return
    if (payload.get("tool_name") or "") != "Bash":
        return
    command = (payload.get("tool_input") or {}).get("command", "")
    cwd = payload.get("cwd") or os.getcwd()

    # The repository is anchored to the directory the session started in, not
    # to where the command happens to run, so a `cd` cannot move the guard to
    # a different repository -- or out of one.
    anchor = os.environ.get("CLAUDE_PROJECT_DIR") or cwd
    root = repo_root(anchor)
    binds = mounts(root, is_simple_git(command) or is_simple_mkdir(command))
    if len(binds) // 3 > MAX_BINDS:
        json.dump({
            "systemMessage": "edit-guard: repository too large to guard",
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason":
                    "%d paths to bind exceeds the %d bwrap can take, so this "
                    "command cannot be run guarded. It was not run."
                    % (len(binds) // 3, MAX_BINDS)},
        }, sys.stdout)
        return

    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "updatedInput": {**(payload.get("tool_input") or {}),
                             "command": rewrite(command, binds, cwd, payload)},
        },
    }, sys.stdout)


if __name__ == "__main__":
    main()
