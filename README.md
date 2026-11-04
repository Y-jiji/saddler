<p align="center">
  <img src="banner.svg" alt="saddler — harness your project" width="100%">
</p>

# Saddler: Per-Project Harness Setup Wizard

To install: `bash install.sh`

To invoke: run claude code in project folder; in claude code, type one of
- `/fileguard`: sandbox Bash and guard Write, Edit and NotebookEdit
- `/codeguide`: software engineering instructions
- `/mathguide`: formally verified (Lean) math project instructions
- `/evalguide`: system evaluation repository layout
- `/tokenline`: status line `<TOKEN COUNT> @ <FOLDER> (<BRANCH>)`

# Design

A rough model of producitivity is `PRODUCTIVITY ∝ #TASKS / (#TURNS * AVERAGE TURN TIME)`

This is a wrong model considering task difficulty or a task may set user backwards towards overall goal. 

But here we assume it is true, since the agent is here to complete user tasks.  

We also assume human can capture agent errors instantly. 

## Minimize Redundant Turns

Count a turn as redundant if the agent does something user doesn't expect. 

Mitigation:
- Setup a feedback loop: build good enough unit tests
- Let the agent present a code skeleton: user know what will happen before it does
- Each term process one issue, so agent does not mix multiple jobs

## Minimize Average Turn Time

User must process agent's feedback. That takes time. 

Mitigation:
- Delay elaboration: less information, more turns, save reading time when you already know the context
- Make edits visible: user knows it immediately when things indeed go wrong
- Essential presets: so user doesn't have to enter them each time
- Progressive: stop at steps where human may disagree with the agent; let errors bubble earlier

## User Obligation

Agent's intelligence dilutes with context length. User must know that.  

# TODO

## fileguard

Bugs and risks:
- [x] BUG3: Hidden left-behind processes: fixed by giving the owner's holder a PID namespace, which also hides host processes from owner commands.
- [ ] BUG5: PID reuse: the fork path trusts `kill -0` on a recorded PID, while the owner path also checks the namespace.
- [x] BUG6: A folder converted from tracked to ignored replaced a live fork's copy and dropped its work from the branch: fixed by making each fork follow its snapshotted `.gitignore`.

Known limits:
- [ ] LIMIT1: `cargo clean` empties `target/`, then fails with `Device or resource busy`, because `target/` is a mountpoint.
- [ ] LIMIT2: Real ignored folders can lag while a fork is alive or a long owner command runs, and from the owner's last command until its next, because session end does not flush them.
- [ ] LIMIT3: A fork command longer than period plus wait can be killed at every tick, and nothing warns about this.
- [ ] LIMIT4: Each base copies single ignored files in full, however big they are.
- [ ] LIMIT5: Writers outside Claude: a terminal or editor writing to a shared ignored folder under a live holder, the owner's or a fork's, gives that holder an inconsistent view, and a build there can make a fork run the wrong binary. Assumes fileguard's hooks are the only hooks.
- [ ] LIMIT6: A checkpoint is assumed to succeed. If one is interrupted or fails, forks stay blocked until an owner command finishes it. With the owner gone that takes a new session, and a repeating failure needs a manual fix first.
- [ ] LIMIT7: A new single ignored file triggers a checkpoint that can kill running fork commands, though nothing needs sharing. Left as is, because new single ignored files are rare.

Not yet verified:
- [ ] TEST1: A real preemption or period-driven checkpoint with a live subagent.
- [ ] TEST2: A real interrupted move and its recovery.
- [ ] TEST3: A second session running as a fork in live use.
- [ ] TEST4: A real `cargo` build on a large `target/`.
- [ ] TEST5: A project-level `env` block reaching `sandbox.sh`, and whether a running session picks up a change.
- [ ] TEST6: Model gaps: the two-fork run was partial, two owners were never combined with interrupts, new-owner recovery never finished a full search, and ignored-list changes are not modelled.
