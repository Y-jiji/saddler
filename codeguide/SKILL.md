---
name: codeguide
description: set up software engineering instructions for this project
disable-model-invocation: true
---

Do these in order:
1. From this skill's directory, copy `CODE.md` unchanged to `<project>/CODE.md`.
2. Add the line `@CODE.md` to `<project>/CLAUDE.md` unless it is already there, creating the file if it is missing.
3. Ask the user with AskUserQuestion whether to add `GIT.md` too; if yes, copy it unchanged to `<project>/GIT.md` and add the line `@GIT.md` to `<project>/CLAUDE.md` the same way.

Why:
- `CODE.md` holds the propose / sanction rules, then the skeleton, naming and test conventions per language; it is copied unchanged so the project carries the exact lines.
- `GIT.md` holds commit conventions; it is optional since not every project commits the same way.
- `@<file>` in `CLAUDE.md` makes Claude Code load that file with it.
