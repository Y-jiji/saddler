#!/usr/bin/env python3
"""Bring every project under a folder up to date with the current fileguard hooks.

Each folder holding .claude is a project. Compare its hook entries and hook files
with the ones beside this file and fix what differs. Dry run unless --apply. Run
it outside the sandbox, which hides other projects.
"""

import argparse
import filecmp
import json
import os
import re
import shutil
from pathlib import Path
from typing import Final, TypeAlias

ROOT: Final = "~/Documents/Project"
OLD: Final = ("edit_guard.py", "edit_hint.py", "write_guard.py",
              "sessionstartsandbox.py", "pretoolusewrite.py", "subagentstop.sh")
NEW: Final = ("pretoolusewrite.py", "sessionstartsandbox.py", "subagentstop.sh")
SCRIPTS: Final = ("sandbox.sh", "allowlist.sh", "gitlock.sh", "gitwrap.sh", "overlayfork.sh", "overlayowner.sh")
SKIP: Final = ("node_modules", "target")
SESSION_START: Final = 'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/sessionstartsandbox.py"'
WRITE_GUARD: Final = 'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/pretoolusewrite.py" || exit 2'
AGENT_STOP: Final = 'bash "$CLAUDE_PROJECT_DIR/.claude/hooks/subagentstop.sh" || exit 2'
MATCHER: Final = "Agent|Bash|Monitor|Write|Edit|NotebookEdit|Read|Grep|Glob"
WANTED: Final = (("SessionStart", "", SESSION_START, 10),
                 ("SessionStart", "", AGENT_STOP, 110),
                 ("PreToolUse", MATCHER, WRITE_GUARD, 110),
                 ("PostToolUse", "TaskStop", AGENT_STOP, 110),
                 ("SubagentStop", "", AGENT_STOP, 110),
                 ("SessionEnd", "", AGENT_STOP, 110))
Settings: TypeAlias = dict[str, object]


def oldscripts(command: str, project: Path) -> list[Path]:
    """Paths of the OLD scripts a hook command runs, with $CLAUDE_PROJECT_DIR
    and ~ expanded and relative paths taken from the project."""
    found = []
    for word in re.findall(r"[^\s\"']+", command):
        if os.path.basename(word) in OLD:
            word = word.replace("${CLAUDE_PROJECT_DIR}", str(project))
            word = word.replace("$CLAUDE_PROJECT_DIR", str(project))
            found.append(project / os.path.expanduser(word))
    return found


def strip(settings: Settings, project: Path, wanted: tuple[tuple[str, str, str, int], ...] = WANTED) -> list[Path]:
    """Drop every hook entry that runs an OLD script unless it is exactly as
    wanted, then the groups and events left empty; return the scripts dropped."""
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return []
    dropped = []
    for event in list(hooks):
        groups = []
        for group in hooks[event]:
            kept = []
            for hook in group.get("hooks", []):
                command = hook.get("command", "")
                scripts = oldscripts(command, project)
                if not scripts or (event, group.get("matcher", ""), command, hook.get("timeout")) in wanted:
                    kept.append(hook)
                else:
                    dropped += scripts
            if kept:
                groups.append({**group, "hooks": kept})
        if groups:
            hooks[event] = groups
        else:
            del hooks[event]
    if not hooks:
        del settings["hooks"]
    return dropped


def register(settings: Settings) -> bool:
    """Add the wanted entries that are missing; True when one was added."""
    hooks = settings.setdefault("hooks", {})
    added = False
    for event, matcher, command, timeout in WANTED:
        groups = hooks.setdefault(event, [])
        if any(g.get("matcher", "") == matcher and any(h.get("command") == command for h in g.get("hooks", []))
               for g in groups):
            continue
        entry = {"type": "command", "command": command, "timeout": timeout}
        groups.append({"matcher": matcher, "hooks": [entry]} if matcher else {"hooks": [entry]})
        added = True
    return added


def findprojects(root: Path) -> list[Path]:
    """Every folder under root holding .claude, leaving out the home folder,
    without entering symlinks, dot-folders or SKIP."""
    found = []
    for folder, names, _ in os.walk(root):
        if ".claude" in names and Path(folder).resolve() != Path.home().resolve():
            found.append(Path(folder))
        names[:] = sorted(name for name in names if not name.startswith(".") and name not in SKIP)
    return sorted(found)


def migrate(project: Path, apply: bool) -> list[str]:
    """What updating one project does, one line per action, and with apply also
    does it; empty when it is current or does not use fileguard. SHAME(TALLFUNC)"""
    here = Path(__file__).resolve().parent
    own = project / "fileguard"
    if (own / Path(__file__).name).is_file():
        if own.resolve() == here:
            return []
        files = [p.name for p in here.iterdir() if p.is_file()]
        differ = sorted(name for name in files
                        if not (own / name).is_file() or not filecmp.cmp(here / name, own / name, shallow=False))
        return ["fileguard/ differs from this copy, pull it: " + ", ".join(differ)] if differ else []
    actions = []
    path = project / ".claude" / "settings.json"
    local = project / ".claude" / "settings.local.json"
    hooksdir = project / ".claude" / "hooks"
    try:
        settings = json.loads(path.read_text()) if path.is_file() else {}
        if not isinstance(settings, dict):
            raise ValueError
    except (OSError, ValueError):
        return ["cannot read .claude/settings.json, left as is"]
    try:
        localset = json.loads(local.read_text()) if local.is_file() else {}
        if not isinstance(localset, dict):
            raise ValueError
    except (OSError, ValueError):
        localset = {}
        actions.append("cannot read .claude/settings.local.json, left as is")
    before = json.dumps(settings, sort_keys=True)
    localbefore = json.dumps(localset, sort_keys=True)
    dropped = strip(settings, project)
    localdropped = strip(localset, project, ())
    commands = {command for _, _, command, _ in WANTED}
    hooks = settings.get("hooks", {}) if isinstance(settings.get("hooks", {}), dict) else {}
    runs = any(h.get("command") in commands for groups in hooks.values() for g in groups for h in g.get("hooks", []))
    uses = bool(dropped) or runs or any((hooksdir / name).is_file() for name in NEW)
    if not uses and not localdropped:
        return actions
    if dropped or localdropped:
        names = sorted({p.name for p in dropped + localdropped})
        actions.append("drop hooks running " + ", ".join(names))
    stale = sorted({p for p in dropped + localdropped if p.is_file() and p.name not in NEW
                    and p.resolve().is_relative_to(project.resolve())})
    actions += ["delete " + os.path.relpath(p, project) for p in stale]
    copies = []
    if uses:
        copies = [name for name in NEW if not (hooksdir / name).is_file()
                  or not filecmp.cmp(here / name, hooksdir / name, shallow=False)]
        actions += ["copy %s to .claude/hooks/" % name for name in copies]
        if register(settings):
            actions.append("register the missing fileguard hook entries")
    if apply:
        if copies:
            hooksdir.mkdir(parents=True, exist_ok=True)
        for name in copies:
            shutil.copy2(here / name, hooksdir / name)
        for p in stale:
            p.unlink()
        if json.dumps(settings, sort_keys=True) != before:
            path.write_text(json.dumps(settings, indent=2) + "\n")
        if json.dumps(localset, sort_keys=True) != localbefore:
            local.write_text(json.dumps(localset, indent=2) + "\n")
    return actions


def installed() -> list[str]:
    """One line for each script in ~/.claude/saddler that differs from the ones beside this file."""
    here = Path(__file__).resolve().parent
    saddler = Path.home() / ".claude" / "saddler"
    return ["~/.claude/saddler/%s differs from this copy, run install.sh" % name for name in SCRIPTS
            if not (saddler / name).is_file() or not filecmp.cmp(here / name, saddler / name, shallow=False)]


def main() -> None:
    """Print the plan for every project under the given folder, ROOT by
    default; with --apply, carry it out."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", nargs="?", default=ROOT,
                    help="folder to scan for .claude (default: %(default)s)")
    ap.add_argument("--apply", action="store_true",
                    help="change the projects instead of only printing")
    args = ap.parse_args()
    root = Path(args.root).expanduser()
    count = 0
    for project in findprojects(root):
        actions = migrate(project, args.apply)
        if actions:
            count += 1
            print(project)
            print("\n".join("  " + line for line in actions))
    for line in installed():
        print(line)
    if count == 0:
        print("no project under %s needs a change" % root)
    elif not args.apply:
        print("dry run; pass --apply to change these %d projects" % count)


if __name__ == "__main__":
    main()
