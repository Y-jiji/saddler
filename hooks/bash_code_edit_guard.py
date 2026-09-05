#!/usr/bin/env python3
"""PreToolUse hook for the Bash tool: refuse shell commands that write code files.

The decision is made from the command string, before anything runs. The hook
modifies nothing and invokes no git, so a wrong verdict costs a blocked command,
never destroyed work.

Reliability comes from a restricted grammar rather than from pattern guessing.
Only a pipeline of simple commands with redirections is accepted:

    cmd word... [redirect...] [| cmd word... [redirect...]]...

Everything else is refused unparsed -- command substitution, heredocs, `;`,
`&&`, `||`, background `&`, subshells, groups, loops, conditionals, functions.
Within that grammar the scanner is exact about quoting, so every word is known
literally and write targets can be read off the parse rather than guessed.

The analysis fails closed. A construct the scanner does not model, a word it
cannot resolve to a literal, or a nested command string it cannot parse is a
denial, not a pass.

Version control commands are not treated as shell writes. `git stash pop`,
`git reset` and `git checkout` write files out of the object store on purpose.
Their redirections are still analyzed.
"""

import json
import os
import re
import sys

CODE_EXT = {
    ".c", ".cc", ".cpp", ".cs", ".css", ".cxx", ".ex", ".exs", ".go", ".h",
    ".hpp", ".hs", ".html", ".java", ".jl", ".js", ".json", ".jsx", ".kt",
    ".lua", ".m", ".md", ".mjs", ".ml", ".php", ".pl", ".py", ".r", ".rb",
    ".rs", ".scala", ".scss", ".sh", ".sql", ".svelte", ".swift", ".toml",
    ".ts", ".tsx", ".vue", ".yaml", ".yml", ".zig",
}

VCS = {"git", "hg", "svn", "jj", "bzr"}

# wrappers whose tail is itself a command: analyzed recursively
WRAPPERS = {"sudo", "env", "nice", "ionice", "nohup", "stdbuf", "time",
            "timeout", "xargs", "command", "builtin", "exec", "doas"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "fish"}

# heads whose arguments name files they write
WRITES_ARGS = {"rm", "truncate", "tee", "patch", "shred", "unlink", "touch",
               "split", "chmod", "chown", "chgrp", "ln"}
INPLACE = {"sed", "perl", "ruby", "gawk", "awk"}      # only with -i
DEST_LAST = {"cp", "mv", "install", "rsync", "dd"}

REDIRECT_OPS = {">", ">>", "&>", "&>>", ">|"}          # produce a file target
FD_DUP_OPS = {">&", "<&"}                              # no file target
READ_OPS = {"<"}
BANNED_OPS = {";", "&&", "||", "&", "(", ")", "{", "}", "<<", "<<<", "<>", "\n"}

KEYWORDS = {"for", "while", "until", "if", "then", "else", "elif", "fi", "do",
            "done", "case", "esac", "select", "function", "coproc"}

GLOB_CHARS = set("*?[")

ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# leading operands some wrappers take before the command they run
WRAPPER_OPERANDS = {"timeout": 1, "nice": 0, "ionice": 0}


class Refuse(Exception):
    """Raised whenever the command cannot be proven safe."""


# --------------------------------------------------------------------------
# scanner: quote-exact tokenizer for the restricted grammar
# --------------------------------------------------------------------------

def scan(text):
    """Tokenize into ('WORD', literal, resolved) and ('OP', op, None).

    `resolved` is False when the word contains an expansion or glob, i.e. its
    runtime value is not knowable here. Refuses anything outside the grammar.
    """
    tokens = []
    word, resolved, has_word = [], True, False
    i, n = 0, len(text)

    def flush():
        nonlocal word, resolved, has_word
        if has_word:
            tokens.append(("WORD", "".join(word), resolved))
        word, resolved, has_word = [], True, False

    while i < n:
        c = text[i]

        if c in " \t":
            flush()
            i += 1
            continue

        if c == "\n":
            raise Refuse("multi-line commands are not accepted")

        if c == "#" and not has_word:
            break                                     # trailing comment

        if c == "\\":
            if i + 1 >= n:
                raise Refuse("trailing backslash")
            word.append(text[i + 1])
            has_word = True
            i += 2
            continue

        if c == "'":                                  # literal, no expansion
            j = text.find("'", i + 1)
            if j < 0:
                raise Refuse("unterminated single quote")
            word.append(text[i + 1:j])
            has_word = True
            i = j + 1
            continue

        if c == '"':
            i += 1
            while i < n and text[i] != '"':
                if text[i] == "\\" and i + 1 < n:
                    word.append(text[i + 1])
                    i += 2
                    continue
                if text[i] == "`":
                    raise Refuse("command substitution is not accepted")
                if text[i] == "$" and i + 1 < n and text[i + 1] == "(":
                    raise Refuse("command substitution is not accepted")
                if text[i] == "$":
                    resolved = False
                word.append(text[i])
                i += 1
            if i >= n:
                raise Refuse("unterminated double quote")
            has_word = True
            i += 1
            continue

        if c == "`":
            raise Refuse("command substitution is not accepted")

        if c == "$":
            if i + 1 < n and text[i + 1] == "(":
                raise Refuse("command substitution is not accepted")
            resolved = False
            word.append(c)
            has_word = True
            i += 1
            continue

        if c in "<>":
            # process substitution
            if i + 1 < n and text[i + 1] == "(":
                raise Refuse("process substitution is not accepted")
            if c == "<" and text[i:i + 3] == "<<<":
                raise Refuse("here-strings are not accepted")
            if c == "<" and text[i:i + 2] == "<<":
                raise Refuse("heredocs are not accepted")
            if c == "<" and text[i:i + 2] == "<>":
                raise Refuse("read-write redirection is not accepted")
            # a bare digit run immediately before the operator is an fd
            fd = ""
            if has_word and "".join(word).isdigit() and resolved:
                fd = "".join(word)
                word, has_word = [], False
            flush()
            op = c
            i += 1
            if i < n and text[i] == c:                # >> or <<(already caught)
                op += c
                i += 1
            elif i < n and text[i] in "&|":           # >& or >|
                op += text[i]
                i += 1
            tokens.append(("OP", fd + op if fd else op, None))
            continue

        if c == "&":
            flush()
            if text[i:i + 2] == "&&":
                raise Refuse("`&&` is not accepted; only pipes and redirects")
            if i + 1 < n and text[i + 1] == ">":
                op = "&>>" if text[i:i + 3] == "&>>" else "&>"
                tokens.append(("OP", op, None))
                i += len(op)
                continue
            raise Refuse("background `&` is not accepted")

        if c == "|":
            flush()
            if text[i:i + 2] == "||":
                raise Refuse("`||` is not accepted; only pipes and redirects")
            tokens.append(("OP", "|", None))
            i += 1
            continue

        if c == ";":
            raise Refuse("`;` is not accepted; only pipes and redirects")

        if c in "()":
            raise Refuse("subshells are not accepted")

        # a brace group is `{` standing alone; `{}` in xargs is a plain word
        if c in "{}" and not has_word and (i + 1 >= n or text[i + 1] in " \t"):
            raise Refuse("command groups are not accepted")

        if c in GLOB_CHARS:
            resolved = False
            word.append(c)
            has_word = True
            i += 1
            continue

        word.append(c)
        has_word = True
        i += 1

    flush()
    return tokens


# --------------------------------------------------------------------------
# parser: pipeline of simple commands
# --------------------------------------------------------------------------

class Command:
    def __init__(self):
        self.words = []          # [(literal, resolved)]
        self.writes = []         # [(literal, resolved)] from redirections

    @property
    def argv(self):
        return [w for w, _ in self.words]


def parse(text):
    """Return the list of Commands in the pipeline. Refuses anything else."""
    tokens = scan(text)
    if not tokens:
        raise Refuse("empty command")

    commands, cur, i = [], Command(), 0
    while i < len(tokens):
        kind, value, resolved = tokens[i]
        if kind == "WORD":
            cur.words.append((value, resolved))
            i += 1
            continue

        if value == "|":
            if not cur.words:
                raise Refuse("empty pipeline stage")
            commands.append(cur)
            cur = Command()
            i += 1
            continue

        op = value.lstrip("0123456789")
        if op in BANNED_OPS:
            raise Refuse("`%s` is not accepted; only pipes and redirects" % op)
        if op in FD_DUP_OPS:
            i += 2 if i + 1 < len(tokens) else 1      # 2>&1: consume the fd
            continue
        if op in REDIRECT_OPS or op in READ_OPS:
            if i + 1 >= len(tokens) or tokens[i + 1][0] != "WORD":
                raise Refuse("redirection without a target")
            target, tgt_resolved = tokens[i + 1][1], tokens[i + 1][2]
            if op in REDIRECT_OPS:
                cur.writes.append((target, tgt_resolved))
            i += 2
            continue
        raise Refuse("unsupported operator `%s`" % op)

    if not cur.words and not cur.writes:
        raise Refuse("empty pipeline stage")
    commands.append(cur)
    return commands


# --------------------------------------------------------------------------
# nested commands
# --------------------------------------------------------------------------

def unwrap(argv):
    """Peel wrappers off argv, yielding nested command strings to re-analyze.

    Returns (effective_argv, nested_strings). Refuses when a wrapper hides a
    command string that cannot be read literally.
    """
    nested = []
    i = 0
    while i < len(argv):
        # `FOO=1 cmd ...` -- leading assignments are not the command
        if ASSIGN_RE.match(argv[i]):
            i += 1
            continue
        head = os.path.basename(argv[i])
        if head in SHELLS:
            for j in range(i + 1, len(argv)):
                if argv[j] in ("-c", "-lc", "-ic"):
                    if j + 1 >= len(argv):
                        raise Refuse("`%s -c` without a command" % head)
                    nested.append(argv[j + 1])
                    return argv[i:], nested
            return argv[i:], nested            # interactive shell, no -c
        if head in WRAPPERS:
            i += 1
            while i < len(argv) and argv[i].startswith("-"):
                i += 1
            # `timeout 5 cmd` -- the duration is not the command
            for _ in range(WRAPPER_OPERANDS.get(head, 0)):
                if i < len(argv) and not argv[i].startswith("-"):
                    i += 1
            if head == "xargs":
                # xargs builds its command from stdin; targets are unknowable
                if i < len(argv):
                    nested.append(" ".join(argv[i:]))
                raise Refuse("`xargs` builds commands from stdin; targets "
                             "cannot be checked")
            while i < len(argv) and "=" in argv[i] and head == "env":
                i += 1
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
    """Directories a recursive delete would take out inside the project."""
    if not argv or os.path.basename(argv[0]) != "rm":
        return []
    flags = "".join(a for a in argv[1:] if a.startswith("-"))
    if "r" not in flags and "R" not in flags:
        return []
    hits = []
    for a in argv[1:]:
        if a.startswith("-") or not in_project(a, cwd):
            continue
        if os.path.isdir(os.path.join(cwd, os.path.expanduser(a))):
            hits.append(a)
    return hits


def analyze(command, cwd, depth=0):
    """Return the list of dangerous findings. Raises Refuse to fail closed."""
    if depth > 3:
        raise Refuse("command nesting is too deep to check")

    findings = []
    for cmd in parse(command):
        argv, nested = unwrap(cmd.argv)

        for sub in nested:
            findings.extend(analyze(sub, cwd, depth + 1))

        # redirection targets belong to the stage, wrappers or not
        candidates = [(t, r) for t, r in cmd.writes]
        resolved_by_word = dict((w, r) for w, r in cmd.words)
        for t in write_targets(argv):
            candidates.append((t, resolved_by_word.get(t, True)))

        for target, resolved in candidates:
            if not resolved:
                raise Refuse(
                    "write target `%s` depends on an expansion or glob and "
                    "cannot be checked" % target)
            if is_code(target) and in_project(target, cwd):
                findings.append("writes code file: %s" % target)

        for d in recursive_delete(argv, cwd):
            findings.append("recursively deletes project directory: %s" % d)

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
        deny("%s\n\nOnly a pipeline of simple commands with redirections is "
             "accepted. Run one command per call, and use the Edit or Write "
             "tool for file changes. The command was not run." % e)
        return

    if findings:
        deny("This command is refused:\n  " + "\n  ".join(findings) +
             "\n\nUse the Edit or Write tool for code files. The command was "
             "not run; no file was changed.")


if __name__ == "__main__":
    main()
