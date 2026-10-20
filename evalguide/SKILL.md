---
name: evalguide
description: set up a repository for system evaluation
disable-model-invocation: true
---

Do these in order:
1. Read `EVAL.md` in this skill's directory.
2. Select the parts the project needs, and present the selection with AskUserQuestion for confirmation.
3. Inline the selected lines into `<project>/CLAUDE.md`, creating it if missing and skipping lines already there.

Rules:
- Copy exact lines from `EVAL.md` and ONLY from it. Do not invent.
- Do not copy the file into the project, do not add `@EVAL.md`.
