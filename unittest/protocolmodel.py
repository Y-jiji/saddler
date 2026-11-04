"""Explicit-state model of fileguard's checkpoint protocol, checked by breadth-first search.

Fork command slots: slot 0 and 1 are fork 0's foreground and background commands, slot n is fork n-1's foreground.
"""

import argparse
import time
from argparse import Namespace
from collections import deque
from typing import NamedTuple


class State(NamedTuple):
    """One global state: command programs, flocks, holders, real folders, faults."""

    owners: tuple[str, ...]
    forkcs: tuple[str, ...]
    cmdsha: frozenset[int]
    cmdexc: int | None
    ownmut: int | None
    gateqs: tuple[str, int] | None
    gatesh: frozenset[int]
    gateex: int | None
    forkmu: tuple[tuple[str, int] | None, ...]
    gitqus: tuple[str, int] | None
    gitsha: frozenset[int]
    gitexc: int | None
    ownerh: str
    forkhs: tuple[str, ...]
    dirtyf: bool
    realrv: int
    partly: bool
    marker: bool
    gennum: int
    forkgn: tuple[int | None, ...]
    basegn: tuple[int, int] | None
    mtimes: tuple[int | None, ...]
    period: bool
    ckdone: int
    crashn: int
    forkrg: tuple[bool, ...]
    forked: tuple[bool, ...]
    daemon: bool
    claude: bool
    faults: str


def setat(items: tuple[object, ...], index: int, value: object) -> tuple[object, ...]:
    """A copy of a tuple with one item replaced."""
    return items[:index] + (value,) + items[index + 1:]


def ownerexit(state: State, slot: int) -> State:
    """An owner wrapper ends: its flocks go, what it did to the world stays."""
    who = ("o", slot)
    return state._replace(owners=setat(state.owners, slot, "idle"), cmdsha=state.cmdsha - {slot},
                          cmdexc=None if state.cmdexc == slot else state.cmdexc,
                          ownmut=None if state.ownmut == slot else state.ownmut,
                          gateqs=None if state.gateqs == who else state.gateqs,
                          gateex=None if state.gateex == slot else state.gateex,
                          gitqus=None if state.gitqus == who else state.gitqus,
                          gitexc=None if state.gitexc == slot else state.gitexc)


def forkexit(state: State, slot: int) -> State:
    """A fork wrapper ends: its flocks go, its holder stays."""
    who = ("f", slot)
    fork = max(slot - 1, 0)
    return state._replace(forkcs=setat(state.forkcs, slot, "idle"), gatesh=state.gatesh - {slot},
                          gitsha=state.gitsha - {slot}, gateqs=None if state.gateqs == who else state.gateqs,
                          gitqus=None if state.gitqus == who else state.gitqus,
                          forkmu=setat(state.forkmu, fork, None) if state.forkmu[fork] == who else state.forkmu)


def environment(state: State, options: Namespace) -> list[tuple[str, State]]:
    """Events no script controls: time, daemons, Claude, the watcher and the end of a fork."""
    out = []
    if not state.period:
        out.append(("period elapses", state._replace(period=True)))
    if state.daemon:
        out.append(("owner daemon exits", state._replace(daemon=False)))
    if state.claude and options.ownerdies:
        out.append(("owner Claude dies", state._replace(claude=False)))
    if not state.claude and options.newowner:
        out.append(("new session claims owner", state._replace(claude=True)))
    if not state.claude and state.ownerh == "live" and not (state.daemon or state.cmdsha or state.cmdexc is not None):
        out.append(("watcher kills idle owner holder", state._replace(ownerh="dead")))
    for fork, ended in enumerate(state.forked):
        slots = [fork, 1] if fork == 0 else [fork + 1]
        if ended and state.forkrg[fork] and all(state.forkcs[slot] == "idle" for slot in slots):
            dead = "dead" if state.forkhs[fork] == "live" else state.forkhs[fork]
            out.append(("hook removes fork%d" % fork, state._replace(forkrg=setat(state.forkrg, fork, False),
                                                                     forkhs=setat(state.forkhs, fork, dead))))
    return out


def ownersteps(state: State, slot: int, options: Namespace) -> list[tuple[str, State]]:
    """Every step one overlayowner.sh can take next. SHAME(TALLFUNC)"""
    program = state.owners[slot]
    label = "owner%d " % slot
    who = ("o", slot)
    out = []

    def move(following: str, **changes: object) -> State:
        return state._replace(owners=setat(state.owners, slot, following), **changes)

    if program == "idle":
        return [(label + "starts", move("wait"))] if state.claude else []
    if program == "wait" and state.cmdexc is None:
        out.append((label + "[1] flock -s ownercmd", move("mutex", cmdsha=state.cmdsha | {slot})))
    elif program == "mutex" and state.ownmut is None:
        out.append((label + "[2] takes holder mutex", move("holder", ownmut=slot)))
    elif program == "holder":
        if state.ownerh == "live":
            out.append((label + "[2] holder live", move("run", ownmut=None)))
        elif state.ownerh == "dead":
            start = "unrecorded" if options.unfixed else "pending"
            out.append((label + "[2] spawns holder", move("record", ownerh=start)))
        else:
            failed = ownerexit(state, slot)._replace(faults="P5 holder start fails with EBUSY")
            out.append((label + "[2] EBUSY", failed))
    elif program == "record":
        out.append((label + "[2] records holder", move("run", ownerh="live", ownmut=None)))
    elif program == "run":
        if not state.dirtyf and state.ckdone < options.ckpts:
            out.append((label + "[3] writes ignored", move("run", dirtyf=True)))
        if slot == options.owners - 1 and not state.daemon and options.daemon:
            out.append((label + "[3] leaves a daemon", move("run", daemon=True)))
        if slot == 0 and options.git:
            out.append((label + "[3] runs git", move("gitqueue")))
        out.append((label + "[3] command ends", move("drop")))
    elif program == "gitqueue" and state.gitqus is None:
        out.append((label + "git queue", move("gitwrite", gitqus=who)))
    elif program == "gitwrite" and not state.gitsha and state.gitexc is None:
        out.append((label + "git write lock", move("githeld", gitqus=None, gitexc=slot)))
    elif program == "githeld":
        out.append((label + "git done", move("run", gitexc=None)))
    elif program == "drop":
        out.append((label + "[4] drops shared", move("upgrade", cmdsha=state.cmdsha - {slot})))
    elif program == "upgrade":
        if not state.cmdsha and state.cmdexc is None:
            out.append((label + "[4] gets exclusive", move("trigger", cmdexc=slot)))
        else:
            out.append((label + "[4] flock -n fails, exits", ownerexit(state, slot)))
    elif program == "trigger":
        if state.marker or (state.dirtyf and (not any(state.forkrg) or state.period)):
            out.append((label + "[5] trigger true", move("scan")))
        else:
            out.append((label + "[5] trigger false, exits", ownerexit(state, slot)))
    elif program == "scan":
        if state.daemon:
            out.append((label + "[6] daemon found, exits", ownerexit(state, slot)))
        else:
            out.append((label + "[6] namespace empty", move("gate")))
    elif program == "gate" and state.gateqs is None:
        out.append((label + "[7] closes gate", move("drain", gateqs=who)))
    elif program == "drain":
        if not state.gatesh and state.gateex is None:
            out.append((label + "[7] gets write lock", move("kill0", gateex=slot)))
        elif state.gatesh:
            out.append((label + "[7] wait expires", move("expire0")))
    elif program.rstrip("0123456789") in ("expire", "kill"):
        stem = program.rstrip("0123456789")
        fork = int(program[len(stem):])
        if state.forkmu[fork] is None:
            final = "retry" if stem == "expire" else "killowner"
            following = stem + str(fork + 1) if fork + 1 < options.forks else final
            dead = "dead" if state.forkhs[fork] == "live" else state.forkhs[fork]
            killed = move(following, forkhs=setat(state.forkhs, fork, dead))
            out.append((label + "[7] kills fork%d holder" % fork, killed))
    elif program == "retry":
        if not state.gatesh and state.gateex is None:
            out.append((label + "[7] gets write lock", move("kill0", gateex=slot)))
        elif state.gatesh:
            out.append((label + "[7] retries after 1s", move("expire0")))
    elif program == "killowner":
        running = ("mutex", "holder", "record", "run", "gitqueue", "gitwrite", "githeld", "drop")
        killed = state.daemon or any(state.owners[other] in running for other in range(options.owners) if other != slot)
        changes = {"faults": "P4 the owner is never killed"} if killed else {}
        dead = "dead" if state.ownerh == "live" else state.ownerh
        out.append((label + "[8] kills owner holder", move("mark", ownerh=dead, **changes)))
    elif program == "mark":
        out.append((label + "[9] touches marker", move("moving", marker=True)))
    elif program == "moving":
        out.append((label + "[9] starts moving", move("moved", partly=state.dirtyf or state.partly)))
    elif program == "moved":
        revision = state.realrv + (1 if state.dirtyf else 0)
        out.append((label + "[9] renames to trash", move("publish", dirtyf=False, partly=False, realrv=revision)))
    elif program == "publish":
        out.append((label + "[10] bumps generation", move("stamp", gennum=state.gennum + 1)))
    elif program == "stamp":
        out.append((label + "[10] touches lastcheckpoint", move("clear", period=False)))
    elif program == "clear":
        ended = ownerexit(state, slot)._replace(marker=False, ckdone=state.ckdone + 1)
        out.append((label + "[10] removes marker, exits", ended))
    if state.crashn < options.crashes:
        dead = "dead" if state.ownerh == "pending" and program == "record" else state.ownerh
        out.append((label + "interrupted at " + program,
                    ownerexit(state, slot)._replace(crashn=state.crashn + 1, ownerh=dead)))
    return out


def forksteps(state: State, slot: int, options: Namespace) -> list[tuple[str, State]]:
    """Every step one fork command, through sandbox.sh and overlayfork.sh, can take next. SHAME(TALLFUNC)"""
    program = state.forkcs[slot]
    fork = max(slot - 1, 0)
    foreground = slot != 1
    label = "fork%d/%s " % (fork, "fg" if foreground else "bg")
    who = ("f", slot)
    holder = state.forkhs[fork]
    out = []

    def move(following: str, **changes: object) -> State:
        return state._replace(forkcs=setat(state.forkcs, slot, following), **changes)

    if program == "idle":
        if not state.forked[fork]:
            out.append((label + "starts, registers", move("queue", forkrg=setat(state.forkrg, fork, True))))
            slots = [fork, 1] if fork == 0 else [fork + 1]
            first = slots[0] == slot and all(state.forkcs[other] == "idle" for other in slots)
            if first and state.forkrg[fork] and state.forkmu[fork] is None:
                dead = "dead" if holder == "live" else holder
                out.append((label + "fork ends, last commit", move("queue", forkhs=setat(state.forkhs, fork, dead),
                                                                   forked=setat(state.forked, fork, True))))
        return out
    if program == "queue" and state.gateqs is None:
        out.append((label + "gate: takes queue", move("read", gateqs=who)))
    elif program == "read" and state.gateex is None:
        following = "gitqueue" if foreground else "base"
        out.append((label + "gate: read lock", move(following, gatesh=state.gatesh | {slot}, gateqs=None)))
    elif program == "gitqueue" and state.gitqus is None:
        out.append((label + "git queue", move("gitread", gitqus=who)))
    elif program == "gitread" and state.gitexc is None:
        out.append((label + "git read lock", move("base", gitsha=state.gitsha | {slot}, gitqus=None)))
    elif program == "base":
        base = state.basegn if state.basegn is not None else (state.gennum, state.realrv)
        aligned = state.mtimes[fork] if state.mtimes[fork] is not None else base[1]
        out.append((label + "[1] base", move("marker", basegn=base, mtimes=setat(state.mtimes, fork, aligned))))
    elif program == "marker":
        if state.marker:
            out.append((label + "[2] marker: refuses", forkexit(state, slot)))
        else:
            out.append((label + "[2] no marker", move("mutex")))
    elif program == "mutex" and state.forkmu[fork] is None:
        out.append((label + "[2] takes mutex", move("holder", forkmu=setat(state.forkmu, fork, who))))
    elif program == "holder":
        if holder == "live":
            out.append((label + "[2] holder live", move("release" if options.unfixed else "compare")))
        elif holder == "dead":
            start = "unrecorded" if options.unfixed else "pending"
            out.append((label + "[2] spawns holder", move("record", forkhs=setat(state.forkhs, fork, start))))
        else:
            out.append((label + "[2] EBUSY", forkexit(state, slot)._replace(faults="P5 holder start fails with EBUSY")))
    elif program == "record":
        out.append((label + "[2] records holder", move("compare", forkhs=setat(state.forkhs, fork, "live"))))
    elif program == "compare":
        seen = state.forkgn[fork] if state.forkgn[fork] is not None else state.basegn[0]
        same = "write" if options.unfixed else "release"
        out.append((label + "[2] compares generation", move("fix" if seen != state.gennum else same)))
    elif program == "fix":
        if holder == "live":
            out.append((label + "[2] mtime fix", move("write", mtimes=setat(state.mtimes, fork, state.realrv))))
        elif options.unfixed:
            out.append((label + "[2] mtime fix fails", move("write")))
        else:
            out.append((label + "[2] mtime fix fails, exits", forkexit(state, slot)))
    elif program == "write":
        written = move("release", forkgn=setat(state.forkgn, fork, state.gennum))
        out.append((label + "[2] writes FORK/generation", written))
    elif program == "release":
        out.append((label + "[2] releases mutex", move("run", forkmu=setat(state.forkmu, fork, None))))
    elif program == "run":
        if holder == "live":
            out.append((label + "[3] command ends", move("commit")))
        else:
            out.append((label + "[3] preempted, exits", forkexit(state, slot)))
    elif program == "commit" and state.forkmu[fork] is None:
        out.append((label + "[4] commits", move("done", forkmu=setat(state.forkmu, fork, who))))
    elif program == "done":
        out.append((label + "exits", forkexit(state, slot)))
    if state.crashn < options.crashes:
        dead = "dead" if holder == "pending" and program == "record" else holder
        out.append((label + "interrupted at " + program,
                    forkexit(state, slot)._replace(crashn=state.crashn + 1, forkhs=setat(state.forkhs, fork, dead))))
    return out


def violation(state: State) -> str | None:
    """The first safety property a state breaks, if any."""
    if state.faults:
        return state.faults
    moving = "moving" in state.owners or "moved" in state.owners
    running = [slot for slot, program in enumerate(state.forkcs)
               if program == "run" and state.forkhs[max(slot - 1, 0)] == "live"]
    if moving and (state.ownerh == "live" or "live" in state.forkhs or running or "run" in state.owners):
        return "P1 real ignored folders change under a live mount"
    if moving and (state.ownerh == "unrecorded" or "unrecorded" in state.forkhs):
        return "P1b an unrecorded holder is mounted during a move"
    for slot in running:
        if state.marker or state.partly:
            return "P2 a fork command runs on a partly moved folder"
        if state.mtimes[max(slot - 1, 0)] != state.realrv:
            return "P3 a fork command trusts mtimes older than its lower"
    if state.gateex is not None and state.gatesh:
        return "P6 the write lock coexists with a read lock"
    return None


def initial(options: Namespace) -> State:
    """Nothing running, nothing mounted, real folders at revision 0."""
    forks = options.forks
    return State(owners=("idle",) * options.owners, forkcs=("idle",) * (forks + 1), cmdsha=frozenset(), cmdexc=None,
                 ownmut=None, gateqs=None, gatesh=frozenset(), gateex=None, forkmu=(None,) * forks, gitqus=None,
                 gitsha=frozenset(), gitexc=None, ownerh="dead", forkhs=("dead",) * forks, dirtyf=False, realrv=0,
                 partly=False, marker=False, gennum=0, forkgn=(None,) * forks, basegn=None, mtimes=(None,) * forks,
                 period=False, ckdone=0, crashn=0, forkrg=(False,) * forks, forked=(False,) * forks, daemon=False,
                 claude=True, faults="")


def explore(options: Namespace) -> None:
    """Search every state, then search backward from idle states, and print the findings. SHAME(TALLFUNC)"""
    begin = time.monotonic()
    first = initial(options)
    parent: dict[State, tuple[State, str] | None] = {first: None}
    edges: dict[State, list[State]] = {}
    queue = deque([first])
    broken: dict[str, State] = {}
    stuck = None
    bounded = False
    try:
        while queue:
            if len(parent) >= options.maxstates or time.monotonic() - begin > options.seconds:
                bounded = True
                break
            state = queue.popleft()
            fault = violation(state)
            if fault:
                broken.setdefault(fault, state)
                edges[state] = []
                continue
            found = environment(state, options)
            for slot in range(options.owners):
                found += ownersteps(state, slot, options)
            for slot in range(options.forks + 1):
                found += forksteps(state, slot, options)
            edges[state] = [following for _, following in found]
            active = [name for name, _ in found if name not in ("period elapses", "owner daemon exits")]
            if not active and stuck is None and any(p != "idle" for p in state.owners + state.forkcs):
                stuck = state
            for name, following in found:
                if following not in parent:
                    parent[following] = (state, name)
                    queue.append(following)
    except MemoryError:
        queue.clear()
        bounded = True

    def trace(state: State) -> list[str]:
        names = []
        step = parent[state]
        while step is not None:
            names.append(step[1])
            step = parent[step[0]]
        return [name for name in reversed(names) if name != "period elapses"]

    trapped = None
    if not bounded:
        back: dict[State, list[State]] = {}
        for state, followers in edges.items():
            for following in followers:
                back.setdefault(following, []).append(state)
        good = {s for s in edges if not s.marker and all(p == "idle" for p in s.owners + s.forkcs)}
        work = deque(good)
        while work:
            for previous in back.get(work.popleft(), ()):
                if previous not in good:
                    good.add(previous)
                    work.append(previous)
        trapped = next((s for s in edges if s not in good and not violation(s)), None)
    status = "BOUNDED, NOT EXHAUSTIVE" if bounded else "exhaustive"
    print("config %-34s states=%-9d %.1fs %s" % (options.name, len(parent), time.monotonic() - begin, status))
    if not (broken or stuck or trapped):
        print("  no violation, no deadlock" + ("" if bounded else ", every state can reach idle"))
    findings = [("VIOLATION " + name, state) for name, state in broken.items()]
    if stuck:
        findings.append(("DEADLOCK", stuck))
    if trapped:
        findings.append(("TRAP: can never reach idle, marker=%s claude=%s" % (trapped.marker, trapped.claude), trapped))
    for name, state in findings:
        path = trace(state)
        print("  %s (trace of %d steps)" % (name, len(path)))
        if options.trace:
            print("\n".join("    " + step for step in path))


def main() -> None:
    """Check one configuration from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="model")
    parser.add_argument("--owners", type=int, default=1, help="owner command slots")
    parser.add_argument("--forks", type=int, default=1, help="forks; fork 0 also has a background slot")
    parser.add_argument("--ckpts", type=int, default=2, help="checkpoints explored")
    parser.add_argument("--crashes", type=int, default=0, help="wrapper interrupts explored")
    parser.add_argument("--ownerdies", action="store_true", help="the owner's Claude can die")
    parser.add_argument("--newowner", action="store_true", help="a new session can claim ownership")
    parser.add_argument("--daemon", action="store_true", help="an owner command can leave a daemon")
    parser.add_argument("--git", action="store_true", help="an owner command can run git")
    parser.add_argument("--unfixed", action="store_true", help="model the holder start of commit 9fc18f0")
    parser.add_argument("--trace", action="store_true", help="print a shortest trace for each finding")
    parser.add_argument("--maxstates", type=int, default=1000000)
    parser.add_argument("--seconds", type=float, default=3.5)
    explore(parser.parse_args())


if __name__ == "__main__":
    main()
