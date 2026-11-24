---
name: codeguide
description: set up software engineering instructions for this project
disable-model-invocation: true
---

`PRODUCTION.md`, `DOMAIN.md` and `GIT.md` in this skill's directory hold the instructions. `PRODUCTION.md` has
sections, each a `# ` header line followed by bullet blocks. A bullet block is a line starting `+ **NAME**` and every
more-indented line after it: `**GENERAL**`, a language (`**RUST**`, `**TYPESCRIPT**`, `**CPP**`, `**PYTHON**`), or,
nested inside a language block, `**Extension (X)**` for language X.

Do these in order:
1. Read `PRODUCTION.md`, `DOMAIN.md` and `GIT.md`.
2. Ask with AskUserQuestion, one call:
   - "Which languages? (1/2)" (multiSelect): `RUST`, `TYPESCRIPT`, `TSX`, `SVELTE`
   - "Which languages? (2/2)" (multiSelect): `CPP`, `CUDA`, `PYTHON`
   - "Add DOMAIN.md lines?": `Yes`, `No`
   - "Add GIT.md lines?": `Yes`, `No`
3. Build the text, keeping the files' order:
   - from `PRODUCTION.md`: every header line and blank line, every `**GENERAL**` block, and the block of each selected
     language; TSX and SVELTE also select TYPESCRIPT, CUDA also selects CPP
   - inside a copied language block, an `**Extension (X)**` block only if X is selected
   - every line of `DOMAIN.md` if its answer is `Yes`; when the old text between the markers has a
     `# Domain Terminology` table with non-empty rows, those rows replace the table's empty row
   - every line of `GIT.md` if its answer is `Yes`
4. Put the text into `<project>/CLAUDE.md` between the lines `<!-- codeguide begin -->` and `<!-- codeguide end -->`:
   replace what is between them when they are there, otherwise append both lines with the text between them at the
   end, creating the file if missing.

Rules:
- Copy exact lines from `PRODUCTION.md`, `DOMAIN.md` and `GIT.md` and only from them, besides the two marker lines
  and the kept `# Domain Terminology` rows.
  Do not invent, reword or reorder.
- Leave every line of `CLAUDE.md` outside the markers as it is.
- Do not copy the files into the project, and do not add `@PRODUCTION.md`, `@DOMAIN.md` or `@GIT.md`.
