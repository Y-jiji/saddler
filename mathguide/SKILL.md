---
name: mathguide
description: set up instructions for a formally verified (Lean) math project
disable-model-invocation: true
---

Do these in order:
1. From this skill's directory, copy `MATH.md` unchanged to `<project>/MATH.md`.
2. Add the line `@MATH.md` to `<project>/CLAUDE.md` unless it is already there, creating the file if it is missing.

Why:
- `MATH.md` holds the propose / sanction rules, then the Lean skeleton, naming and property-check conventions; the type check is the proof, so there is no test step.
- `@MATH.md` in `CLAUDE.md` makes Claude Code load that file with it.
