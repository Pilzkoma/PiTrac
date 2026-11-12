#!/usr/bin/env python3
"""When does each camera expose after its trigger edge? A flash-delay sweep.

    python3 -m sp1_vision.trigger_sweep --out ~/strobe_raw/trigger_sweep1
    python3 -m sp1_vision.trigger_sweep --out ~/strobe_raw/trigger_sweep1 --analyse

The B0332 boards take a trigger at pad F (Teensy pins 4 / 5, firmware v0.2):
in UVC trigger mode (exposure_auto_priority=1) a camera delivers one frame per
rising edge. The edge goes through the board's controller firmware, so when
the exposure actually starts is unknown. This measures it: every SHOT
triggers both cameras together and fires one short flash a set delay after
the edge. Sweeping the delay, the flash shows up only while a camera is
exposing - the delays where it is seen give each camera's exposure start,
its length, and (from how sharp the edges are over repeats) the jitter.

Shots alternate flash / no flash. The UVC driver has been seen to hold a
frame back (CLAUDE.md, "the driver holds a frame back"); a frame that is one
shot late then lights the no-flash slots, which held_back_shift detects and
undoes.

Frames are matched to shots by arrival time: a frame belongs to the last
shot sent before it, within one shot spacing. Raw frames are saved, so
--analyse can redo the analysis without capturing again.
"""

import argparse
import json
import os
import random
import subprocess
import sys
import threading
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sp1_vision import strobe_capture as sc  # noqa: E402
from sp1_vision.calibration_capture import set_manual_exposure  # noqa: E402

SPACING_S = 0.1          # between shots; frames arrive well within this
WARMUP_SHOTS = 6         # no-flash shots first, flushing anything held back
LIT_MIN = sc.LIT_THRESHOLD   # grey levels: below this nothing was seen at all
REF_SAMPLE = 200


# ----------------------------------------------------------------- analysis

def assign_frames(shot_times, frame_times, spacing_s=SPACING_S):
    """Per shot, the index of its frame (or None).

    A frame belongs to the last shot sent before it arrived, if it arrived
    within spacing_s of that shot; a second frame in the same slot is
    dropped (the first one is the triggered frame).
    """
    out = [None] * len(shot_times)
    k = -1
    for i, tf in enumerate(frame_times):
        while k + 1 < len(shot_times) and shot_times[k + 1] < tf:
            k += 1
        if k < 0 or tf - shot_times[k] > spacing_s or out[k] is not None:
            continue
        out[k] = i
    return out


def held_back_shift(flash, lit):
    """0, or 1 when every frame arrived one shot late.

    Under shift s the frame for shot i is the one in slot i + s. The shift
    whose flash shots are brighter than its no-flash shots wins.
    """
    best, best_contrast = 0, -np.inf
    n = len(flash)
    for s in (0, 1):
        on = [lit[i + s] for i in range(n - s) if flash[i] and lit[i + s] is not None]
        off = [lit[i + s] for i in range(n - s) if not flash[i] and lit[i + s] is not None]
        if not on or not off:
            continue
        contrast = float(np.median(on)) - float(np.median(off))
        if contrast > best_contrast:
            best, best_contrast = s, contrast
    return best


def apply_shift(per_shot, s):
    """per_shot[i + s] for every shot i; None past the end."""
    return [per_shot[i + s] if i + s < len(per_shot) else None for i in range(len(per_shot))]


def exposure_window(delays, lit):
    """Where the flash was seen, from flash shots only.

    Returns None if it was never seen. Otherwise start / end / width (first
    delay seen in at least half the repeats, first delay after that run seen
    in fewer than half), and the spread of each edge: from the first delay
    where it is seen at all (>10 % of repeats) to the first where it is seen
    almost always (>=90 %) - zero for a sharp edge, wide for a jittery one.
    """
    pairs = [(d, v) for d, v in zip(delays, lit) if v is not None]
    if not pairs:
        return None
    vals = np.array([v for _, v in pairs], dtype=float)
    top = float(np.percentile(vals, 99))
    if top < LIT_MIN:
        return None
    thresh = max(LIT_MIN, 0.5 * top)
    by = {}
    for d, v in pairs:
        by.setdefault(d, []).append(v > thresh)
    ds = sorted(by)
    frac = {d: float(np.mean(by[d])) for d in ds}
    lit_ds = [d for d in ds if frac[d] >= 0.5]
    if not lit_ds:
        return None
    start = lit_ds[0]
    i = ds.index(start)
    while i < len(ds) and frac[ds[i]] >= 0.5:
        i += 1
    end = ds[i] if i < len(ds) else ds[-1] + (ds[-1] - ds[-2] if len(ds) > 1 else 0)

    rise_lo = next((d for d in ds if frac[d] > 0.1), start)
    rise_hi = next((d for d in ds if d >= rise_lo and frac[d] >= 0.9), start)
    last_hi = max((d for d in ds if frac[d] >= 0.9), default=start)
    last_lo = max((d for d in ds if frac[d] > 0.1), default=last_hi)
    return {
        "start_us": start, "end_us": end, "width_us": end - start,
        "start_spread_us": rise_hi - rise_lo,
        "end_spread_us": last_lo - last_hi,
        "threshold": thresh, "top": top,
        "fraction_by_delay": {str(d): frac[d] for d in ds},
    }


def lit_metric(img, ref):
    """99th percentile of how much brighter than the reference: the flash."""
    d = img.astype(np.float32) - ref
    return float(np.percentile(d, 99))


def small(buf):
    return cv2.imdecode(np.asarray(buf).reshape(-1), cv2.IMREAD_REDUCED_GRAYSCALE_4)


# ------------------------------------------------------------------ capture

def build_plan(min_us, max_us, step_us, repeats, seed=0):
    """[(delay_us, flash)]: warm-up, then every delay x repeats, flash / dark pairs."""
    delays = [d for d in range(min_us, max_us + 1, step_us) for _ in range(repeats)]
    random.Random(seed).shuffle(delays)
    plan = [(0, False)] * WARMUP_SHOTS
    for d in delays:
        plan += [(d, True), (d, False)]
    return plan


def trigger_mode(caps, on):
    for _, dev in caps.values():
        subprocess.run(["v4l2-ctl", "--device={}".format(dev),
                        "--set-ctrl=exposure_auto_priority={}".format(1 if on else 0)],
                       check=False, capture_output=True, timeout=5)


def reader(cap, stop, out):
    while not stop.is_set():
        ok, buf = cap.read()
        if ok and buf is not None:
            out.append((time.monotonic(), buf.copy()))


def capture(args):
    plan = build_plan(args.min_us, args.max_us, args.step_us, args.repeats)
    print("%d shots, %.0f s" % (len(plan), len(plan) * SPACING_S), flush=True)
    sc.release_dashboard()
    teensy = sc.Teensy(sc.TEENSY)
    caps = sc.open_cameras()
    got = {n: [] for n in caps}
    shots = []
    stop = threading.Event()
    threads = []
    try:
        sc.set_gamma(caps, args.gamma)
        sc.settle_on_auto(caps)
        for _, dev in caps.values():
            set_manual_exposure(dev, args.exposure)
        time.sleep(sc.SETTLE_S)
        teensy.cmd("TRIG_ARM")
        trigger_mode(caps, True)
        threads = [threading.Thread(target=reader, args=(c, stop, got[n]), daemon=True)
                   for n, (c, _) in caps.items()]
        for th in threads:
            th.start()
        time.sleep(0.5)
        t_next = time.monotonic()
        for k, (delay, flash) in enumerate(plan):
            while time.monotonic() < t_next:
                time.sleep(0.001)
            t = time.monotonic()
            teensy.cmd("SHOT,3,{},{}".format(delay, args.pulse_us if flash else 0))
            shots.append({"t": t, "delay_us": delay, "flash": flash,
                          "warmup": k < WARMUP_SHOTS})
            t_next = t + SPACING_S
            if k % 100 == 0:
                print("  shot %d / %d" % (k, len(plan)), flush=True)
        time.sleep(SPACING_S)
    finally:
        stop.set()
        trigger_mode(caps, False)          # free-running again: readers return
        for th in threads:
            th.join(timeout=3)
        try:
            teensy.cmd("TRIG_DISARM")
        except Exception:                  # noqa: BLE001
            pass
        sc.set_gamma(caps, sc.DEFAULT_GAMMA)
        for cap, dev in caps.values():
            cap.release()
            set_manual_exposure(dev, None)
        teensy.close()

    os.makedirs(args.out, exist_ok=True)
    meta = {"exposure_units": args.exposure, "pulse_us": args.pulse_us,
            "spacing_s": SPACING_S, "shots": shots, "frames": {}}
    for n, frames in got.items():
        d = os.path.join(args.out, "raw", "cam%d" % n)
        os.makedirs(d, exist_ok=True)
        meta["frames"][str(n)] = [t for t, _ in frames]
        for i, (_, buf) in enumerate(frames):
            with open(os.path.join(d, "%05d.jpg" % i), "wb") as f:
                f.write(np.asarray(buf).reshape(-1).tobytes())
    with open(os.path.join(args.out, "capture.json"), "w") as f:
        json.dump(meta, f)


# ----------------------------------------------------------------- analysis

def analyse(out):
    with open(os.path.join(out, "capture.json")) as f:
        meta = json.load(f)
    shots = meta["shots"]
    t_shots = [s["t"] for s in shots]
    flash = [s["flash"] for s in shots]
    result = {"exposure_units": meta["exposure_units"], "pulse_us": meta["pulse_us"],
              "cameras": {}}
    for n, frame_times in sorted(meta["frames"].items()):
        d = os.path.join(out, "raw", "cam%s" % n)
        assigned = assign_frames(t_shots, frame_times, meta["spacing_s"])
        imgs = {}
        for i in assigned:
            if i is not None:
                with open(os.path.join(d, "%05d.jpg" % i), "rb") as f:
                    imgs[i] = small(np.frombuffer(f.read(), np.uint8))
        if not imgs:
            result["cameras"][n] = {"frames": len(frame_times), "matched": 0}
            print("cam%s: %d frames arrived, none matched a shot" % (n, len(frame_times)))
            continue
        keys = sorted(imgs)
        sample = keys[:: max(1, len(keys) // REF_SAMPLE)]
        ref = np.median(np.stack([imgs[i] for i in sample]), axis=0).astype(np.float32)
        lit = [lit_metric(imgs[i], ref) if i is not None else None for i in assigned]
        shift = held_back_shift(flash, lit)
        lit = apply_shift(lit, shift)
        frames_used = apply_shift(assigned, shift)
        sel = [k for k, s in enumerate(shots) if s["flash"] and not s["warmup"]]
        window = exposure_window([shots[k]["delay_us"] for k in sel], [lit[k] for k in sel])
        dark = [lit[k] for k, s in enumerate(shots)
                if not s["flash"] and not s["warmup"] and lit[k] is not None]
        lit_flash = [(lit[k], frames_used[k]) for k in sel if lit[k] is not None]
        if lit_flash:
            best = max(lit_flash, key=lambda p: p[0])[1]
            if best is not None:
                with open(os.path.join(d, "%05d.jpg" % best), "rb") as f:
                    with open(os.path.join(out, "cam%s_brightest.jpg" % n), "wb") as g:
                        g.write(f.read())
        cam = {"frames": len(frame_times),
               "matched": sum(1 for i in assigned if i is not None),
               "shots": len(shots), "held_back_shift": shift,
               "dark_median": float(np.median(dark)) if dark else None,
               "window": window}
        result["cameras"][n] = cam
        print("cam%s: %d frames for %d shots, %d matched, held-back shift %d, "
              "no-flash level %.1f" % (n, cam["frames"], len(shots), cam["matched"], shift,
                                       cam["dark_median"] or -1))
        if window is None:
            print("  flash never seen")
        else:
            print("  exposure %.2f .. %.2f ms after the edge (%.2f ms), "
                  "edge spread %.2f / %.2f ms, flash +%.0f grey levels" % (
                      window["start_us"] / 1000, window["end_us"] / 1000,
                      window["width_us"] / 1000, window["start_spread_us"] / 1000,
                      window["end_spread_us"] / 1000, window["top"]))
    w = [c.get("window") for c in result["cameras"].values()]
    if len(w) == 2 and all(w):
        off = w[1]["start_us"] - w[0]["start_us"]
        result["cam2_minus_cam1_start_us"] = off
        print("cam2 starts %+.2f ms after cam1" % (off / 1000))
    with open(os.path.join(out, "result.json"), "w") as f:
        json.dump(result, f, indent=1)
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--exposure", type=int, default=10, help="100 us units (default 1 ms)")
    ap.add_argument("--pulse-us", type=int, default=50)
    ap.add_argument("--min-us", type=int, default=0)
    ap.add_argument("--max-us", type=int, default=20000)
    ap.add_argument("--step-us", type=int, default=250)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--gamma", type=int, default=sc.MEASURE_GAMMA)
    ap.add_argument("--analyse", action="store_true",
                    help="analyse the capture already in --out, capture nothing")
    args = ap.parse_args(argv)
    if not args.analyse:
        capture(args)
    analyse(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
