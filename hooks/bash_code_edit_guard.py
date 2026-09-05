# /// script
# requires-python = ">=3.11"
# dependencies = ["tree-sitter", "tree-sitter-bash"]
# ///
"""PreToolUse hook for the Bash tool: refuse shell commands that write code files.

The command is parsed with the tree-sitter bash grammar before anything runs.
The hook modifies nothing and invokes no git, so a wrong verdict costs a blocked
command, never destroyed work.

One statement per call, optionally backgrounded:

    cmd word... [redirect...] [| cmd ...] [&]

The accepted node types are an allowlist (ALLOWED). Any other node -- command
substitution, heredocs, here-strings, process substitution, `;`, `&&`, `||`,
subshells, groups, loops, conditionals, function definitions -- is refused by
name. A grammar the parser flags as containing an error is refused too.

The analysis fails closed. An unlisted node type, a write target carrying an
expansion or a glob, a nested command string that cannot be read literally, and
any internal error are all denials.

Version control commands are not treated as shell writes. `git stash pop`,
`git reset` and `git checkout` write files out of the object store on purpose.
Their redirections are still analyzed.
"""

import json
import os
import re
import sys

import tree_sitter_bash
from tree_sitter import Language, Parser

CODE_EXT = {
    ".c", ".cc", ".cpp", ".cs", ".css", ".cxx", ".ex", ".exs", ".go", ".h",
    ".hpp", ".hs", ".html", ".java", ".jl", ".js", ".json", ".jsx", ".kt",
    ".lua", ".m", ".md", ".mjs", ".ml", ".php", ".pl", ".py", ".r", ".rb",
    ".rs", ".scala", ".scss", ".sh", ".sql", ".svelte", ".swift", ".toml",
    ".ts", ".tsx", ".vue", ".yaml", ".yml", ".zig",
}

# Structural allowlist. Anything the parser produces that is not here is a
# denial, so a construct nobody thought about fails closed rather than open.
ALLOWED = {
    "program", "comment",
    "command", "command_name", "pipeline", "redirected_statement",
    "variable_assignment", "variable_name",
    "word", "number", "string", "raw_string", "ansi_c_string",
    "string_content", "concatenation", "escape_sequence",
    "simple_expansion", "expansion",
    "file_redirect", "file_descriptor",
    "|", "&", "=", ">", ">>", "<", ">&", "<&", "&>", "&>>", ">|", "$", "\"",
    "${", "{", "}",                # only as expansion delimiters, e.g. ${HOME}
}

# words whose literal value is not knowable here
UNRESOLVED = {"simple_expansion", "expansion", "command_substitution",
              "arithmetic_expansion", "process_substitution"}
GLOB_CHARS = set("*?[")

# redirect operators that name a file rather than duplicate a descriptor
WRITE_OPS = {">", ">>", "&>", "&>>", ">|"}
DUP_OPS = {">&", "<&"}

VCS = {"git", "hg", "svn", "jj", "bzr"}
WRAPPERS = {"sudo", "env", "nice", "ionice", "nohup", "stdbuf", "time",
            "timeout", "xargs", "command", "builtin", "exec", "doas"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "fish"}
WRAPPER_OPERANDS = {"timeout": 1}      # leading operands before the command
ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# `find` runs commands over a set this cannot enumerate
FIND_ACTIONS = {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fls",
                "-fprint", "-fprintf"}

WRITES_ARGS = {"rm", "truncate", "tee", "patch", "shred", "unlink", "touch",
               "split", "chmod", "chown", "chgrp", "ln"}
INPLACE = {"sed", "perl", "ruby", "gawk", "awk"}      # only with -i
DEST_LAST = {"cp", "mv", "install", "rsync", "dd"}

PARSER = Parser(Language(tree_sitter_bash.language()))


class Refuse(Exception):
    """Raised whenever the command cannot be proven safe."""


# --------------------------------------------------------------------------
# reading the tree
# --------------------------------------------------------------------------

def text_of(node, src):
    return src[node.start_byte:node.end_byte].decode("utf-8", "replace")


def check_types(node, src):
    """Refuse any node type outside the allowlist, deepest name first."""
    if node.type not in ALLOWED:
        raise Refuse("`%s` is not accepted; one command per call, pipes and "
                     "redirects only" % text_of(node, src).split("\n")[0][:40])
    for child in node.children:
        check_types(child, src)


def is_resolved(node, src):
    """False when the word's runtime value depends on an expansion or glob.

    Globbing is not a node type -- an unquoted `*.py` is a plain `word` -- so
    the characters are checked directly. Quoting turns a word into a string or
    raw_string node, where those characters are literal.
    """
    if node.type in UNRESOLVED:
        return False
    if node.type == "word" and set(text_of(node, src)) & GLOB_CHARS:
        return False
    for child in node.children:
        if not is_resolved(child, src):
            return False
    return True


def literal(node, src):
    """The literal value of a word, with quoting removed."""
    if node.type == "raw_string":
        return text_of(node, src)[1:-1]
    if node.type in ("string", "concatenation", "ansi_c_string"):
        if not node.children:
            return text_of(node, src)
        return "".join(literal(c, src) for c in node.children
                       if c.type not in ('"', "'"))
    if node.type == "escape_sequence":
        return text_of(node, src)[-1:]
    return text_of(node, src)


ARG_TYPES = {"word", "number", "string", "raw_string", "ansi_c_string",
             "concatenation", "simple_expansion", "expansion"}


def command_words(node, src):
    """(argv, resolved_flags) for a `command` node, assignments dropped."""
    argv, flags = [], []
    for child in node.named_children:
        if child.type == "variable_assignment":
            continue                       # `FOO=1 cmd` -- not the command
        if child.type == "command_name":
            inner = child.named_children[0] if child.named_children else child
            argv.append(literal(inner, src))
            flags.append(is_resolved(inner, src))
        elif child.type in ARG_TYPES:
            argv.append(literal(child, src))
            flags.append(is_resolved(child, src))
    return argv, flags


def redirect_targets(node, src):
    """[(literal, resolved)] for each file_redirect under this statement."""
    out = []
    for child in node.children:
        if child.type != "file_redirect":
            continue
        op = next((c.type for c in child.children
                   if c.type in WRITE_OPS or c.type in DUP_OPS), None)
        if op is None or op in DUP_OPS:
            continue                       # 2>&1 duplicates an fd, no file
        target = next((c for c in child.named_children
                       if c.type != "file_descriptor"), None)
        if target is None:
            raise Refuse("redirection without a target")
        out.append((literal(target, src), is_resolved(target, src)))
    return out


def statements(program, src):
    """The single statement of the program, plus its redirect targets."""
    bodies = [c for c in program.named_children if c.type != "comment"]
    if not bodies:
        raise Refuse("empty command")
    if len(bodies) > 1:
        raise Refuse("one command per call; found %d statements" % len(bodies))

    # a trailing `&` backgrounds the statement; `&` between statements is a
    # list, and is already excluded by the single-statement rule above
    for i, child in enumerate(program.children):
        if child.type == "&" and i != len(program.children) - 1:
            raise Refuse("`&` between commands is a list; one command per call")

    body = bodies[0]
    writes = []
    while body.type == "redirected_statement":
        writes.extend(redirect_targets(body, src))
        inner = [c for c in body.named_children if c.type != "file_redirect"]
        if not inner:
            raise Refuse("redirection without a command")
        body = inner[0]

    commands = ([c for c in body.named_children if c.type == "command"]
                if body.type == "pipeline" else
                [body] if body.type == "command" else [])
    if not commands:
        raise Refuse("`%s` is not a simple command" % body.type)
    return commands, writes


# --------------------------------------------------------------------------
# nested commands
# --------------------------------------------------------------------------

def unwrap(argv, resolved):
    """Peel wrappers, returning (effective_argv, nested command strings)."""
    nested, i = [], 0
    while i < len(argv):
        head = os.path.basename(argv[i])
        if head in SHELLS:
            for j in range(i + 1, len(argv)):
                if argv[j] in ("-c", "-lc", "-ic"):
                    if j + 1 >= len(argv):
                        raise Refuse("`%s -c` without a command" % head)
                    if not resolved[j + 1]:
                        raise Refuse("`%s -c` argument is not a literal "
                                     "string" % head)
                    nested.append(argv[j + 1])
                    return argv[i:], nested
            return argv[i:], nested
        if head in WRAPPERS:
            i += 1
            while i < len(argv) and argv[i].startswith("-"):
                i += 1
            if head == "env":
                # `env FOO=1 cmd` -- these are assignments, not the command
                while i < len(argv) and ASSIGN_RE.match(argv[i]):
                    i += 1
            for _ in range(WRAPPER_OPERANDS.get(head, 0)):
                if i < len(argv) and not argv[i].startswith("-"):
                    i += 1
            if head == "xargs":
                raise Refuse("`xargs` builds its command from stdin; targets "
                             "cannot be checked")
            continue
        break
    return argv[i:], nested


# --------------------------------------------------------------------------
# dangerous patterns
# --------------------------------------------------------------------------

def is_code(path):
    return os.path.splitext(path)[1].lower() in CODE_EXT


def in_project(path, cwd):
    root = os.path.realpath(cwd)
    full = os.path.realpath(os.path.join(cwd, os.path.expanduser(path)))
    return full == root or full.startswith(root + os.sep)


def write_targets(argv):
    """Files this simple command writes, from its own semantics."""
    if not argv:
        return []
    head = os.path.basename(argv[0])
    flags = [a for a in argv[1:] if a.startswith("-")]
    args = [a for a in argv[1:] if not a.startswith("-")]

    if head in VCS:
        return []
    if head in WRITES_ARGS:
        return args
    if head in INPLACE:
        return args if any(f.startswith("-i") for f in flags) else []
    if head == "dd":
        return [a.split("=", 1)[1] for a in argv[1:] if a.startswith("of=")]
    if head in DEST_LAST:
        return args[-1:] if args else []
    return []


def recursive_delete(argv, cwd):
    """Project directories a recursive delete would take out."""
    if not argv or os.path.basename(argv[0]) != "rm":
        return []
    flags = "".join(a for a in argv[1:] if a.startswith("-"))
    if "r" not in flags and "R" not in flags:
        return []
    return [a for a in argv[1:]
            if not a.startswith("-") and in_project(a, cwd)
            and os.path.isdir(os.path.join(cwd, os.path.expanduser(a)))]


def analyze(command, cwd, depth=0):
    """Dangerous findings for a command string. Raises Refuse to fail closed."""
    if depth > 3:
        raise Refuse("command nesting is too deep to check")

    src = command.encode()
    tree = PARSER.parse(src)
    if tree.root_node.has_error:
        raise Refuse("the command is not valid bash")
    check_types(tree.root_node, src)

    commands, redirects = statements(tree.root_node, src)
    findings = []
    candidates = list(redirects)

    for position, cmd in enumerate(commands):
        argv, resolved = command_words(cmd, src)
        by_word = dict(zip(argv, resolved))
        effective, nested = unwrap(argv, resolved)
        head = os.path.basename(effective[0]) if effective else ""

        # a shell downstream of a pipe takes its command from stdin, so the
        # command it will run is not in this string at all
        if position > 0 and head in SHELLS:
            raise Refuse("a shell reading its command from a pipe cannot be "
                         "checked")
        action = next((a for a in effective[1:] if a in FIND_ACTIONS), None)
        if head == "find" and action:
            raise Refuse("`find %s` acts on a set of files that cannot be "
                         "enumerated here" % action)

        for sub in nested:
            findings.extend(analyze(sub, cwd, depth + 1))

        for target in write_targets(effective):
            candidates.append((target, by_word.get(target, True)))
        for d in recursive_delete(effective, cwd):
            findings.append("recursively deletes project directory: %s" % d)

    for target, ok in candidates:
        if not ok:
            raise Refuse("write target `%s` depends on an expansion or glob "
                         "and cannot be checked" % target)
        if is_code(target) and in_project(target, cwd):
            findings.append("writes code file: %s" % target)

    return findings


# --------------------------------------------------------------------------

def deny(reason):
    json.dump(
        {
            "systemMessage": "Bash blocked: " + reason.split("\n")[0],
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            },
        },
        sys.stdout,
    )


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return
    if (payload.get("tool_name") or "") != "Bash":
        return
    cwd = payload.get("cwd") or os.getcwd()
    command = (payload.get("tool_input") or {}).get("command", "")

    try:
        findings = analyze(command, cwd)
    except Refuse as e:
        deny("%s\n\nRun one command per call and use the Edit or Write tool "
             "for file changes. The command was not run." % e)
        return
    except Exception as e:                 # fail closed on our own bugs
        deny("the guard could not check this command (%s: %s). "
             "The command was not run." % (type(e).__name__, e))
        return

    if findings:
        deny("This command is refused:\n  " + "\n  ".join(findings) +
             "\n\nUse the Edit or Write tool for code files. The command was "
             "not run; no file was changed.")


if __name__ == "__main__":
    main()
