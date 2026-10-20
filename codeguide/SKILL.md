---
name: codeguide
description: set up software engineering instructions for this project
disable-model-invocation: true
---

Do these in order:
1. Read `CODE.md` and `GIT.md` in this skill's directory.
2. Ask with AskUserQuestion, one call:
   - "Which languages? (1/2)" (multiSelect): `RUST`, `TYPESCRIPT`, `TSX`, `SVELTE`
   - "Which languages? (2/2)" (multiSelect): `CPP`, `CUDA`, `PYTHON`
   - "Add GIT.md lines?": `Yes`, `No`
3. Inline into `<project>/CLAUDE.md`, creating it if missing and skipping lines already there:
   - every line of `CODE.md` outside the language bullet blocks
   - under each header line, the bullet block of each selected language; TSX / SVELTE also pull TYPESCRIPT, CUDA pulls CPP
   - every line of `GIT.md` if `Yes`

Rules:
- Copy exact lines from `CODE.md` / `GIT.md` and ONLY from them, in their original order. Do not invent.
- Do not copy the files into the project, do not add `@CODE.md` / `@GIT.md`.
