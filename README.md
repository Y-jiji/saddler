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
- [ ] BUG1: Writers outside the protocol: a terminal or hook writing to a shared ignored folder while a fork is live can bring back the wrong binary.
- [ ] BUG2: Marker trap: after an interrupted move with the owner gone, forks stay blocked until a new session runs a command, and their error message does not say so.
- [ ] BUG3: Hidden left-behind processes: a process in its own nested namespace escapes the owner's scan, so the upper stays busy and holder starts fail with `EBUSY`.
- [ ] BUG4: List-only checkpoints: a new ignored file or folder counts as a change, so it can kill running fork commands at the next tick with no owner writes.
- [ ] BUG5: PID reuse: the fork path trusts `kill -0` on a recorded PID, while the owner path also checks the namespace.

Known limits:
- [ ] LIMIT1: `cargo clean` empties `target/`, then fails with `Device or resource busy`, because `target/` is a mountpoint.
- [ ] LIMIT2: Real ignored folders can lag while a fork is alive or a long owner command runs, and from the owner's last command until its next, because session end does not flush them.
- [ ] LIMIT3: A fork command longer than period plus wait can be killed at every tick, and nothing warns about this.
- [ ] LIMIT4: Each base copies single ignored files in full, however big they are.

Not yet verified:
- [ ] TEST1: A real preemption or period-driven checkpoint with a live subagent.
- [ ] TEST2: A real interrupted move and its recovery.
- [ ] TEST3: A second session running as a fork in live use.
- [ ] TEST4: A real `cargo` build on a large `target/`.
- [ ] TEST5: A project-level `env` block reaching `sandbox.sh`, and whether a running session picks up a change.
- [ ] TEST6: Model gaps: the two-fork run was partial, two owners were never combined with interrupts, new-owner recovery never finished a full search, and ignored-list changes are not modelled.
