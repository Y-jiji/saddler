---
name: codeguide
description: set up software engineering instructions for this project
disable-model-invocation: true
---

`WORKFLOW.md`, `PRODUCTION.md` and `GIT.md` in this skill's directory hold the instructions. `PRODUCTION.md` has
sections, each a `# ` header line followed by bullet blocks. A bullet block is a line starting `+ **NAME**` and every
more-indented line after it: `**GENERAL**`, a language (`**RUST**`, `**TYPESCRIPT**`, `**CPP**`, `**PYTHON**`), or,
nested inside a language block, `**Extension (X)**` for language X.

Do these in order:
1. Read `WORKFLOW.md`, `PRODUCTION.md` and `GIT.md`.
2. Ask with AskUserQuestion, one call:
   - "Which languages? (1/2)" (multiSelect): `RUST`, `TYPESCRIPT`, `TSX`, `SVELTE`
   - "Which languages? (2/2)" (multiSelect): `CPP`, `CUDA`, `PYTHON`
   - "Add GIT.md lines?": `Yes`, `No`
3. Build the text, keeping the files' order:
   - every line of `WORKFLOW.md`
   - from `PRODUCTION.md`: every header line and blank line, every `**GENERAL**` block, and the block of each selected
     language; TSX and SVELTE also select TYPESCRIPT, CUDA also selects CPP
   - inside a copied language block, an `**Extension (X)**` block only if X is selected
   - every line of `GIT.md` if `Yes`
4. Put the text into `<project>/CLAUDE.md` between the lines `<!-- codeguide begin -->` and `<!-- codeguide end -->`:
   replace what is between them when they are there, otherwise append both lines with the text between them at the
   end, creating the file if missing.

Rules:
- Copy exact lines from `WORKFLOW.md`, `PRODUCTION.md` and `GIT.md` and only from them, besides the two marker lines.
  Do not invent, reword or reorder.
- Leave every line of `CLAUDE.md` outside the markers as it is.
- Do not copy the files into the project, and do not add `@WORKFLOW.md`, `@PRODUCTION.md` or `@GIT.md`.
