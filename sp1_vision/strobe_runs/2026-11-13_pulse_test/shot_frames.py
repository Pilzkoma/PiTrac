#!/usr/bin/env python3
"""Single triggered shots with frames matched by arrival time, alignment proven.

    python3 shot_frames.py OUTDIR pulse_us [pulse_us ...] [--repeats N]

Each requested pulse is fired REPEATS times, every flash shot followed by a
dark shot at the same delay (as trigger_sweep does). Frames are read
continuously and matched to shots by arrival time (trigger_sweep.assign_frames);
held_back_shift must come out 0, i.e. flash shots bright and dark shots dark,
otherwise the run is refused. Reading "the next frame" after each SHOT was
wrong: frames from before trigger mode sit in the buffer (2026-11-13).

Writes OUTDIR/frames.npz (per camera, per pulse: the flash frames) and
prints, per camera, the flash-minus-dark brightening per pulse.
"""
import os
import sys
import threading
import time

import numpy as np

sys.path.insert(0, os.path.expanduser("~/JetsonLM"))
from sp1_vision import strobe_capture as sc, trigger_sweep as ts  # noqa
from sp1_vision.calibration_capture import set_manual_exposure  # noqa

args = sys.argv[1:]
repeats = 3
if "--repeats" in args:
    i = args.index("--repeats")
    repeats = int(args[i + 1])
    del args[i:i + 2]
OUT, pulses = args[0], [int(p) for p in args[1:]]
os.makedirs(OUT, exist_ok=True)

plan = []
for p in pulses:
    for _ in range(repeats):
        plan += [p, 0]
SPACING = 0.1

sc.release_dashboard()
teensy = sc.Teensy(sc.TEENSY)
caps = sc.open_cameras()
got = {n: [] for n in caps}
stop = threading.Event()
threads = []
t_shots = []
try:
    sc.set_gamma(caps, sc.MEASURE_GAMMA)
    sc.settle_on_auto(caps)
    for _, dev in caps.values():
        set_manual_exposure(dev, 5)
    time.sleep(sc.SETTLE_S)
    teensy.cmd("TRIG_ARM")
    sc.set_trigger_mode(caps, True)
    threads = [threading.Thread(target=ts.reader, args=(c, stop, got[n]), daemon=True)
               for n, (c, _) in caps.items()]
    for th in threads:
        th.start()
    time.sleep(0.5)                      # stale free-running frames arrive now
    for _ in range(4):                   # warm-up, not analysed
        teensy.cmd("SHOT,3,900,0")
        time.sleep(SPACING)
    t_next = time.monotonic()
    for p in plan:
        while time.monotonic() < t_next:
            time.sleep(0.001)
        t = time.monotonic()
        teensy.cmd("SHOT,3,900,{}".format(p))
        t_shots.append(t)
        t_next = t + SPACING
    time.sleep(SPACING)
finally:
    stop.set()
    sc.set_trigger_mode(caps, False)
    for th in threads:
        th.join(timeout=3)
    try:
        teensy.cmd("TRIG_DISARM")
    except Exception:
        pass
    sc.set_gamma(caps, sc.DEFAULT_GAMMA)
    for cap, dev in caps.values():
        cap.release()
        set_manual_exposure(dev, None)
    teensy.close()

flash = [p > 0 for p in plan]
save = {}
ok_all = True
for n, frames in got.items():
    idx = ts.assign_frames(t_shots, [t for t, _ in frames], SPACING)
    imgs = [sc.decode(frames[i][1]) if i is not None else None for i in idx]
    means = [float(im.mean()) if im is not None else None for im in imgs]
    shift = ts.held_back_shift(flash, means)
    missing = sum(1 for i in idx if i is None)
    print("cam%d: %d frames for %d shots, %d missing, held-back shift %d" % (
        n, len(frames), len(plan), missing, shift))
    if shift != 0 or missing:
        ok_all = False
    for p in pulses:
        k = [i for i, q in enumerate(plan) if q == p]
        fl = [imgs[i] for i in k if imgs[i] is not None]
        dk = [imgs[i + 1] for i in k if imgs[i + 1] is not None]
        save["cam%d_%d" % (n, p)] = np.stack(fl)
        save["cam%d_%d_dark" % (n, p)] = np.stack(dk)
        print("   %4d us: frame mean flash %.1f, dark %.1f" % (
            p, np.mean([f.mean() for f in fl]), np.mean([f.mean() for f in dk])))
np.savez_compressed(os.path.join(OUT, "frames.npz"), **save)
print("ALIGNED" if ok_all else "NOT ALIGNED - do not use")
