#!/usr/bin/env python3
"""Hook for the Bash tool: catch code files edited by shell commands.

PreToolUse   snapshot which code files are already dirty, and their contents.
PostToolUse  compare. A code file the command touched is reverted with git when
             its pre-command content was recoverable from git (it was clean);
             otherwise it is only reported.

Wire the same script to both events.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

CODE_EXT = {
    ".c", ".cc", ".cpp", ".cs", ".css", ".cxx", ".ex", ".exs", ".go", ".h",
    ".hpp", ".hs", ".html", ".java", ".jl", ".js", ".json", ".jsx", ".kt",
    ".lua", ".m", ".md", ".mjs", ".ml", ".php", ".pl", ".py", ".r", ".rb",
    ".rs", ".scala", ".scss", ".sh", ".sql", ".svelte", ".swift", ".toml",
    ".ts", ".tsx", ".vue", ".yaml", ".yml", ".zig",
}

# shell commands that write a file, for the no-git-repo fallback
INPLACE = {"sed", "perl", "ruby"}          # only with -i
DEST_LAST = {"cp", "mv", "install"}        # only the final argument
WRITES_ARGS = {"rm", "truncate", "tee", "patch", "shred"}
REDIRECT_RE = re.compile(r">>?\s*([^\s|;&<>()]+)")


def tokens(text):
    return [t.strip("\"'") for t in re.split(r"\s+", text.strip()) if t]


def git(root, *args):
    return subprocess.run(
        ["git", "-C", root, *args], capture_output=True, text=True
    )


def repo_root(cwd):
    r = subprocess.run(
        ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
        capture_output=True, text=True,
    )
    return r.stdout.strip() if r.returncode == 0 else None


def is_code(path):
    return os.path.splitext(path)[1].lower() in CODE_EXT


def digest(root, path):
    try:
        with open(os.path.join(root, path), "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None  # deleted


def dirty(root):
    """Code files not clean against HEAD -> content hash (None if gone)."""
    r = git(root, "status", "--porcelain=v1", "-z", "-uall")
    if r.returncode != 0:
        return {}
    out, fields, i = {}, r.stdout.split("\0"), 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if len(entry) < 4:
            continue
        code, path = entry[:2], entry[3:]
        if code[0] in "RC":  # rename/copy: source path follows in its own field
            i += 1
        if is_code(path):
            out[path] = digest(root, path)
    return out


def snapshot_path(session_id):
    d = os.path.join(tempfile.gettempdir(), "claude-bash-code-guard")
    os.makedirs(d, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "default")
    return os.path.join(d, safe + ".json")


def pre(payload, cwd):
    root = repo_root(cwd)
    snap = {"root": root, "dirty": dirty(root) if root else {}}
    with open(snapshot_path(payload.get("session_id")), "w") as f:
        json.dump(snap, f)


def post(payload, cwd):
    try:
        with open(snapshot_path(payload.get("session_id"))) as f:
            snap = json.load(f)
    except (OSError, ValueError):
        snap = None

    root = repo_root(cwd)
    if root is None or snap is None or snap.get("root") != root:
        return fallback(payload, root)

    before, after = snap["dirty"], dirty(root)
    reverted, warned = [], []
    for path, now in after.items():
        if path in before:
            if before[path] != now:
                warned.append((path, "was already modified before the command"))
            continue
        # clean before the command: HEAD still holds that content
        if git(root, "cat-file", "-e", "HEAD:" + path).returncode != 0:
            warned.append((path, "newly created, nothing to revert to"))
        elif git(root, "checkout", "HEAD", "--", path).returncode == 0:
            reverted.append(path)
        else:
            warned.append((path, "git checkout failed"))
    return report(reverted, warned)


def fallback(payload, root):
    """No usable git snapshot: name the code files the command looks like it wrote."""
    cmd = (payload.get("tool_input") or {}).get("command", "")
    hits = set()
    for segment in re.split(r"\|\||&&|[|;&\n]", cmd):
        words = tokens(segment)
        if not words:
            continue
        head = os.path.basename(words[0])
        args = [w for w in words[1:] if not w.startswith("-")]
        if head in WRITES_ARGS:
            hits.update(w for w in args if is_code(w))
        elif head in INPLACE and any(w.startswith("-i") for w in words[1:]):
            hits.update(w for w in args if is_code(w))
        elif head in DEST_LAST and args and is_code(args[-1]):
            hits.add(args[-1])
        hits.update(t for t in REDIRECT_RE.findall(segment) if is_code(t))
    where = "outside a git repository" if root is None else "no snapshot available"
    return report([], [(p, where) for p in sorted(hits)])


def report(reverted, warned):
    if not reverted and not warned:
        return
    lines = []
    for p in reverted:
        lines.append("reverted %s (restored from git)" % p)
    for p, why in warned:
        lines.append("NOT reverted %s (%s)" % (p, why))
    msg = "Bash command edited code files:\n  " + "\n  ".join(lines)
    json.dump(
        {
            "systemMessage": msg,
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": msg
                + "\nEdit code files with the Edit/Write tools, not shell commands.",
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
    if payload.get("hook_event_name") == "PreToolUse":
        pre(payload, cwd)
    else:
        post(payload, cwd)


if __name__ == "__main__":
    main()
