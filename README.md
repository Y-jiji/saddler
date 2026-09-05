<p align="center">
  <img src="banner.svg" alt="saddler — one thing at a time" width="100%">
</p>

# saddler

`saddler` is a Claude Code skill that saddles an agent: it scaffolds a small set
of plain-text reference files into a project and then keeps the agent inside
them. Run `./install.sh` to copy the folder into `~/.claude/skills`, then invoke
`/saddler` in any project — the skill is human-triggered only, never
model-invoked. It lists the reference files sitting next to it, asks per file
whether to install or opt in, writes `CLAUDE.md`, and sets up hooks. Prompts are
copied verbatim from the reference files; nothing is invented.

The core principle is [`SOUL.md`](SOUL.md): one thing per turn. Every turn is
exactly one of propose, act, or inform — propose states only what will be done
and asks for sanction, act implements only what was sanctioned, inform answers
only what was asked.

The other reference files split the same discipline per domain — each one says
what must be presented for sanctioning and what may then be implemented:

- [`CODE.md`](CODE.md) — code skeleton listing before code, per language, plus naming conventions
- [`RESEARCH.md`](RESEARCH.md) — section skeletons, plot skeletons, five-sentence paper surveys
- [`GIT.md`](GIT.md) — one-line commit messages, commit as you go, no worktrees
- [`BASH.md`](BASH.md) — hooks making git-tracked files read-only to `Bash`
- [`STATUSLINE.md`](STATUSLINE.md) — `<tokens> @ <folder> (<branch>)`
