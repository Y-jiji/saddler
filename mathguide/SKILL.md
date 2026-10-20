---
name: mathguide
description: set up instructions for a formally verified (Lean) math project
disable-model-invocation: true
---

Do these in order:
1. Read `MATH.md` in this skill's directory.
2. Select the parts the project needs, and present the selection with AskUserQuestion for confirmation.
3. Inline the selected lines into `<project>/CLAUDE.md`, creating it if missing and skipping lines already there.

Rules:
- Copy exact lines from `MATH.md` and ONLY from it. Do not invent.
- Do not copy the file into the project, do not add `@MATH.md`.
