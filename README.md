<svg width="100%" viewBox="0 0 960 200" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="saddler — one thing at a time">
  <defs>
    <linearGradient id="sdl-bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#12161c"/>
      <stop offset="1" stop-color="#202832"/>
    </linearGradient>
  </defs>
  <rect width="960" height="200" rx="14" fill="url(#sdl-bg)"/>
  <g fill="none" stroke="#f0b429" stroke-width="7" stroke-linecap="round">
    <path d="M70 28 V 66"/>
    <path d="M44 66 H 96"/>
    <path d="M32 70 V 96 C 32 126 50 144 70 144 C 90 144 108 126 108 96 V 70"/>
    <path d="M38 142 H 102"/>
  </g>
  <text x="168" y="104" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="60" font-weight="700" fill="#f5f7fa" letter-spacing="2">saddler</text>
  <text x="172" y="140" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="19" fill="#8b98a9" letter-spacing="4">one thing at a time</text>
  <g font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="15" text-anchor="middle">
    <rect x="580" y="83" width="104" height="34" rx="17" fill="#ffffff" fill-opacity="0.05" stroke="#7cc4ff" stroke-opacity="0.55"/>
    <text x="632" y="105" fill="#7cc4ff">propose</text>
    <rect x="728" y="83" width="72" height="34" rx="17" fill="#ffffff" fill-opacity="0.05" stroke="#f0b429" stroke-opacity="0.55"/>
    <text x="764" y="105" fill="#f0b429">act</text>
    <rect x="844" y="83" width="96" height="34" rx="17" fill="#ffffff" fill-opacity="0.05" stroke="#86d99c" stroke-opacity="0.55"/>
    <text x="892" y="105" fill="#86d99c">inform</text>
  </g>
  <g fill="none" stroke="#4d5a6b" stroke-width="2" stroke-linecap="round">
    <path d="M694 100 H 716"/>
    <path d="M710 94 L 716 100 L 710 106"/>
    <path d="M810 100 H 832"/>
    <path d="M826 94 L 832 100 L 826 106"/>
  </g>
</svg>

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
