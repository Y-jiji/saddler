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
- Delay elaboration: less information, more turns, less than human time
- Make edits visible: user knows it immediately when things indeed go wrong
- Essential presets: so user doesn't have to enter them each time
- Progressive: stop at steps where human may disagree with the agent; let errors happen earlier

## User Obligation

Agent's intelligence dilutes with context length. User must know that.  
