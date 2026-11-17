"""Conservative slot packing and an independent schedule checker.

No spatial reuse is credited: PRBs assigned in a slot are disjoint. Sharing
a vehicle is prohibited even on different PRBs, enforcing a conservative
half-duplex rule (also forbids multiple same-slot streams at one vehicle).
Every job is one blind copy, occupies one slot, and has integer release and
deadline slots. The EDF-style greedy constructor is a heuristic: failure
does not prove infeasibility. This is a diagnostic scheduler, not a complete
NR Mode-1 implementation; feedback/control/processing overheads are not
yet modeled. The checker establishes only the explicitly encoded rules.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Job:
    key: str
    packet: str
    tx: str
    rx: str
    prbs: int
    release: int
    deadline: int  # exclusive, all occupied symbols must finish before it


@dataclass(frozen=True)
class Placement:
    job: Job
    slot: int
    first_prb: int


def validate(placements, prbs_per_slot, expected_jobs=None):
    """Return violations, including missing/duplicate copies when jobs given."""
    errors, occupied, radios, seen, packet_slots = [], {}, {}, set(), set()
    for p in placements:
        j, s, r0 = p.job, p.slot, p.first_prb
        if j.key in seen:
            errors.append(f"duplicate job: {j.key}")
        seen.add(j.key)
        if not j.release <= s < j.deadline:
            errors.append(f"deadline/release: {j.key}")
        if j.prbs < 1 or r0 < 0 or r0 + j.prbs > prbs_per_slot:
            errors.append(f"bandwidth: {j.key}")
        if j.tx == j.rx:
            errors.append(f"self-link: {j.key}")
        pair = (j.packet, s)
        if pair in packet_slots:
            errors.append(f"same-packet copies in one slot: {j.packet}")
        packet_slots.add(pair)
        used = occupied.setdefault(s, set())
        cells = set(range(r0, r0 + j.prbs))
        if used & cells:
            errors.append(f"overlap: {j.key}")
        used.update(cells)
        active = radios.setdefault(s, set())
        if active & {j.tx, j.rx}:
            errors.append(f"radio conflict: {j.key}")
        active.update((j.tx, j.rx))
    if expected_jobs is not None:
        expected = {j.key for j in expected_jobs}
        if len(expected) != len(expected_jobs):
            errors.append("non-unique expected job keys")
        errors.extend(f"missing job: {k}" for k in sorted(expected - seen))
        errors.extend(f"unexpected job: {k}" for k in sorted(seen - expected))
    return errors


def pack(jobs, prbs_per_slot):
    """Return (placements, unscheduled jobs); never assert failure is impossible."""
    remaining = sorted(jobs, key=lambda j: (j.deadline, -j.prbs, j.key))
    placements = []
    if not remaining:
        return placements, []
    for slot in range(min(j.release for j in jobs), max(j.deadline for j in jobs)):
        active, packets, used, later = set(), set(), 0, []
        for j in remaining:
            if (j.release <= slot < j.deadline and 0 < j.prbs <= prbs_per_slot - used
                    and not active.intersection((j.tx, j.rx)) and j.packet not in packets
                    and j.tx != j.rx):
                placements.append(Placement(j, slot, used))
                used += j.prbs
                active.update((j.tx, j.rx))
                packets.add(j.packet)
            else:
                later.append(j)
        remaining = later
    errors = validate(placements, prbs_per_slot)
    if errors:
        raise AssertionError(errors)
    return placements, remaining
