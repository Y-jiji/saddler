#!/usr/bin/env python3
"""Move projects from the old edit_guard hooks to the fileguard sandbox.

For every project under ROOT whose .claude/settings.json runs an OLD hook,
drop those hook entries and the scripts inside the project, copy the NEW
hooks beside this file into .claude/hooks/ and register them. Dry run unless
--apply. Run it outside the sandbox, which hides other projects.
"""

import argparse
import json
import os
import re
import shutil
from pathlib import Path
from typing import Final, TypeAlias

ROOT: Final = "~/Documents/Project"
OLD: Final = ("edit_guard.py", "edit_hint.py", "write_guard.py")
NEW: Final = ("sessionstartsandbox.py", "pretoolusewrite.py")
SESSION_START: Final = 'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/sessionstartsandbox.py"'
WRITE_GUARD: Final = 'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/pretoolusewrite.py" || exit 2'
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


def strip(settings: Settings, project: Path) -> list[Path]:
    """Drop every hook entry that runs an OLD script, then the groups and
    events left empty; return the scripts those entries ran."""
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return []
    dropped = []
    for event in list(hooks):
        groups = []
        for group in hooks[event]:
            kept = []
            for hook in group.get("hooks", []):
                scripts = oldscripts(hook.get("command", ""), project)
                dropped += scripts
                if not scripts:
                    kept.append(hook)
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
    """Add the SessionStart and Write|Edit|NotebookEdit entries for the NEW
    hooks unless that event already runs them; True when one was added."""
    hooks = settings.setdefault("hooks", {})
    added = False
    for event, matcher, command, name in (
            ("SessionStart", "", SESSION_START, NEW[0]),
            ("PreToolUse", "Write|Edit|NotebookEdit", WRITE_GUARD, NEW[1])):
        groups = hooks.setdefault(event, [])
        if name in json.dumps(groups):
            continue
        entry = {"type": "command", "command": command, "timeout": 10}
        groups.append({"matcher": matcher, "hooks": [entry]} if matcher
                      else {"hooks": [entry]})
        added = True
    return added


def migrate(project: Path, apply: bool) -> list[str]:
    """What migrating one project does, one line per action, and with apply
    also does it; empty when the project runs no OLD hook."""
    path = project / ".claude" / "settings.json"
    try:
        settings = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    dropped = strip(settings, project)
    if not dropped:
        return []
    here = Path(__file__).resolve().parent
    hooksdir = project / ".claude" / "hooks"
    stale = sorted({p for p in dropped if p.is_file()
                    and p.resolve().is_relative_to(project.resolve())})
    actions = ["drop hooks running "
               + ", ".join(sorted({p.name for p in dropped}))]
    actions += ["delete " + os.path.relpath(p, project) for p in stale]
    actions += ["copy %s to .claude/hooks/" % name for name in NEW]
    if register(settings):
        actions.append("register SessionStart and Write|Edit|NotebookEdit")
    if apply:
        hooksdir.mkdir(parents=True, exist_ok=True)
        for name in NEW:
            shutil.copy2(here / name, hooksdir / name)
        for p in stale:
            p.unlink()
        path.write_text(json.dumps(settings, indent=2) + "\n")
    return actions


def main() -> None:
    """Print the plan for every project under the given root, ROOT by
    default; with --apply, carry it out."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", nargs="?", default=ROOT,
                    help="folder holding the projects (default: %(default)s)")
    ap.add_argument("--apply", action="store_true",
                    help="change the projects instead of only printing")
    args = ap.parse_args()
    root = Path(args.root).expanduser()
    count = 0
    for project in sorted(p for p in root.iterdir() if p.is_dir()):
        actions = migrate(project, args.apply)
        if actions:
            count += 1
            print(project)
            print("\n".join("  " + line for line in actions))
    if count == 0:
        print("no project under %s runs the old hooks" % root)
    elif not args.apply:
        print("dry run; pass --apply to change these %d projects" % count)


if __name__ == "__main__":
    main()
