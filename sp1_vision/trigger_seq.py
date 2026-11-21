"""Schedules for the Teensy's SEQ command (firmware v0.4).

A schedule is a list of (t_us, event): "E1" / "E2" = rising trigger edge on
camera 1 / 2 at t, "F<us>" = a flash of that length from t. seq_command turns
it into the serial line; the firmware (seq_schedule.h) checks it again and
refuses what it cannot play (two edges per camera, overlapping flashes, ...).

offset_schedule is part 3 of the ball-marks design
(docs/superpowers/specs/2026-11-13-ball-marks-spin-design.md, decision 5):
cam2 edged offset_us after cam1, each camera with its own flash delay_us
after its own edge. Exposure starts ~0.78 ms after an edge (trigger_sweep,
2026-11-12), so with 0.5 ms exposures the defaults give windows at
0.78-1.28 and 1.78-2.28 ms and each flash lands in its own camera only.
"""

import re

OFFSET_US = 1000
DELAY_US = 900
PULSE_US = 100

_EVENT = re.compile(r"^(E1|E2|F[1-9][0-9]*)$")


def seq_command(events):
    """'SEQ,<t>:<event>,...' with the events in time order."""
    if not events:
        raise ValueError("empty schedule")
    for t, ev in events:
        if int(t) != t or t < 0 or not _EVENT.match(ev):
            raise ValueError("bad event %r at %r" % (ev, t))
    ordered = sorted(events, key=lambda e: e[0])
    return "SEQ," + ",".join("%d:%s" % (t, ev) for t, ev in ordered)


def offset_schedule(offset_us=OFFSET_US, delay_us=DELAY_US, pulse_us=PULSE_US):
    """Both cameras' edges, cam2 offset_us late; one flash each (none if pulse 0)."""
    events = [(0, "E1"), (offset_us, "E2")]
    if pulse_us:
        events += [(delay_us, "F%d" % pulse_us), (offset_us + delay_us, "F%d" % pulse_us)]
    return events


def sweep_schedule(offset_us, flash_at_us, pulse_us):
    """Both edges and ONE flash flash_at_us after cam1's edge (none if pulse 0)."""
    events = [(0, "E1"), (offset_us, "E2")]
    if pulse_us:
        events.append((flash_at_us, "F%d" % pulse_us))
    return events
