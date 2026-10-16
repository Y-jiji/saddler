---
name: evalguide
description: set up a repository for system evaluation
disable-model-invocation: true
---

Do these in order:
1. From this skill's directory, copy `EVAL.md` unchanged to `<project>/EVAL.md`.
2. Add the line `@EVAL.md` to `<project>/CLAUDE.md` unless it is already there, creating the file if it is missing.

Why:
- `EVAL.md` lays out an evaluation repository: evaluated repos as submodules, each study in a `#NNN` folder with research question, metrics, run, analyze and figure sections.
- Most code here is disposable, so it carries no propose / sanction rules.
- `@EVAL.md` in `CLAUDE.md` makes Claude Code load that file with it.
