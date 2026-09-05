# /// script
# requires-python = ">=3.11"
# dependencies = ["tree-sitter", "tree-sitter-bash"]
# ///
"""Run a bash command with every git-tracked file read-only.

    sandbox_run.py <command>          run it guarded
    sandbox_run.py --check <command>  print the plan, run nothing

Tracked files are bind-mounted read-only into a private mount namespace, so
the kernel refuses to modify or delete them no matter what the command does --
a shell redirect, `sed -i`, another interpreter, a script, a background child.
The repository directory itself stays writable, so new files and directories
are allowed and `cargo run`, `npm install` and friends keep working.

Two things run unguarded: a command outside any git repository, and a simple
git command (see is_simple_git). Git rewrites tracked files on purpose --
checkout, restore, stash pop -- and a bind mount makes that fail with
"Device or resource busy", sometimes while still reporting success.
"""

import os
import subprocess
import sys

import tree_sitter_bash
from tree_sitter import Language, Parser

# bwrap accepts 9000 arguments; each bind spends 3, and --dev-bind takes 3.
# Setup cost also grows faster than linearly: ~180 ms at 636 binds, ~900 ms at
# 1500, ~3.3 s at the ceiling.
MAX_BINDS = 2900

# git options that make git run a command of its own choosing, so a command
# carrying one is not a simple git command however it is spelled
GIT_EXEC_OPTS = ("-c", "--config-env", "--exec-path")

# node types that mean the command is more than one simple command
COMPOUND = {"pipeline", "list", "subshell", "compound_statement",
            "command_substitution", "process_substitution", "heredoc_redirect",
            "herestring_redirect", "file_redirect", "for_statement",
            "while_statement", "if_statement", "case_statement",
            "function_definition", "&", ";", "&&", "||"}

# a word whose value is not knowable from the text
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


def is_simple_git(command):
    """True when the whole command line is one plain `git ARGS` invocation.

    Requires: valid bash, a single command, no pipe, redirect, background,
    separator, subshell, substitution or heredoc, no leading VAR=value, every
    word a literal (no expansion or glob), the program is `git`, and no option
    that lets git execute something of its own (-c, --config-env, --exec-path).

    `git commit -m 'a message'` qualifies. `ls && git checkout main`,
    `git log > out.txt`, `git -c core.pager='rm x' log` and `git $CMD` do not.
    """
    src = command.encode()
    root = _PARSER.parse(src).root_node
    if root.has_error:
        return False

    if any(n.type in COMPOUND for n in _walk(root)):
        return False

    bodies = [c for c in root.named_children if c.type != "comment"]
    if len(bodies) != 1 or bodies[0].type != "command":
        return False
    node = bodies[0]

    argv = []
    for child in node.named_children:
        if child.type == "variable_assignment":
            return False                      # `GIT_DIR=x git ...` is not plain
        if child.type == "command_name":
            child = child.named_children[0] if child.named_children else child
        if not _resolved(child, src):
            return False
        argv.append(_literal(child, src))

    if not argv or os.path.basename(argv[0]) != "git":
        return False
    return not any(a in GIT_EXEC_OPTS
                   or a.startswith(tuple(o + "=" for o in GIT_EXEC_OPTS))
                   for a in argv[1:])


def repo_root(cwd):
    r = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def tracked_files(root):
    """Existing regular tracked files, the set to freeze.

    Symlinks are skipped: binding one would resolve to its target, which may
    sit outside the repository.
    """
    r = subprocess.run(["git", "-C", root, "ls-files", "-z"],
                       capture_output=True, text=True)
    out = []
    for name in r.stdout.split("\0"):
        if not name:
            continue
        path = os.path.join(root, name)
        if os.path.isfile(path) and not os.path.islink(path):
            out.append(path)
    return out


def bwrap_argv(files, command):
    args = ["bwrap", "--dev-bind", "/", "/"]
    for path in files:
        args += ["--ro-bind", path, path]
    return args + ["bash", "-c", command]


def plan(command, cwd):
    """-> (reason, argv). argv is None when the command runs unguarded."""
    root = repo_root(cwd)
    if root is None:
        return "not a git repository", None
    if is_simple_git(command):
        return "simple git command", None
    files = tracked_files(root)
    if len(files) > MAX_BINDS:
        return ("%d tracked files exceeds the %d bwrap can bind"
                % (len(files), MAX_BINDS)), None
    return "%d tracked files frozen" % len(files), bwrap_argv(files, command)


def main(argv):
    check = argv and argv[0] == "--check"
    if check:
        argv = argv[1:]
    if not argv:
        print(__doc__.strip().split("\n\n")[1], file=sys.stderr)
        return 2

    command = " ".join(argv)
    cwd = os.getcwd()
    reason, wrapped = plan(command, cwd)

    if check:
        print("command : %s" % command)
        print("guarded : %s" % ("yes" if wrapped else "no"))
        print("reason  : %s" % reason)
        return 0

    if wrapped is None:
        if reason.endswith("bwrap can bind"):
            print("sandbox_run: %s; refusing to run unguarded" % reason,
                  file=sys.stderr)
            return 1
        os.execvp("bash", ["bash", "-c", command])
    os.execvp(wrapped[0], wrapped)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
