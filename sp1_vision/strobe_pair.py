#!/usr/bin/env python3
"""One strobe-lit stereo pair into a triangulation run directory.

    python3 -m sp1_vision.strobe_pair --out RUNDIR --tape 302 --series depth

Fires one short flash while both cameras stream, keeps the flash-lit frame
from each minus the ambient frames before it, checks at once that both show
the ball (the same stereo decision the analysis makes), and appends the shot
to RUNDIR/run.json. The run is then
analysed unchanged with

    python3 -m sp1_vision.cli_triangulate --analyse RUNDIR

This is cli_triangulate's capture with the flash instead of room light, and
non-interactive so a position can be taken per call: the tape reading comes
on the command line. Tape readings follow the same rule as there - the
ball's NEAR edge, the side facing the unit, from the same zero every time.

Capture settings are the ones strobe_runs/README.md settled on: 8 ms
exposure (every flash lands, in both cameras, although they are not in
phase), a 0.1 ms flash (ball mid-range, nothing clipped), gamma 72, and an
auto-exposure pass first to clear the image processor's stuck states.
"""

import argparse
import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sp1_vision import ball_pair, cli_triangulate, stereo_geometry  # noqa: E402
from sp1_vision import strobe_capture as sc  # noqa: E402
from sp1_vision.calibration_capture import set_manual_exposure  # noqa: E402

SERIES = {"d": "depth", "s": "spread", "t": "target"}


def lit_frame(frames, t_fire):
    """Return (flash image, ambient image, rise) for one camera.

    frames: [(kernel_ts, arrival_ts, mjpeg_buffer)] from strobe_capture.one_run.
    The ambient image is the median of the last frames before the fire; the
    rise is the 99th percentile of (flash - ambient) in grey levels.
    """
    decoded = [(ta, sc.decode(b)) for _, ta, b in frames]
    ambient = [img for ta, img in decoded if ta < t_fire - 0.05]
    if len(ambient) < 3:
        raise RuntimeError("too few frames before the flash")
    base = np.median(np.stack(ambient[-5:]), axis=0).astype(np.uint8)
    best, best_rise = None, -1.0
    for ta, img in decoded:
        if ta < t_fire:
            continue
        rise = float(np.percentile(cv2.subtract(img, base), 99))
        if rise > best_rise:
            best, best_rise = img, rise
    return best, base, best_rise


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True, help="triangulation run directory")
    ap.add_argument("--tape", type=float, required=True,
                    help="tape reading at the ball's NEAR edge, mm")
    ap.add_argument("--series", required=True,
                    choices=sorted(SERIES) + sorted(SERIES.values()),
                    help="depth line / spread / target line (d / s / t)")
    ap.add_argument("--pulse-us", type=int, default=200,
                    help="flash length; 200 keeps the ball clear of the room "
                         "under lamps without clipping (default %(default)s)")
    ap.add_argument("--exposure", type=int, default=80, help="100 us units")
    ap.add_argument("--gamma", type=int, default=sc.MEASURE_GAMMA)
    args = ap.parse_args(argv)
    series = SERIES.get(args.series, args.series)

    rig = stereo_geometry.load_rig()
    stereo_geometry.validate_rig(rig)

    dirs = {n: os.path.join(args.out, "cam{}".format(n)) for n in (1, 2)}
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)
    shots = cli_triangulate._load_manifest(args.out)
    number = cli_triangulate._resume_start_number(dirs, shots)
    name = "gs_{:02d}.png".format(number)

    sc.release_dashboard()
    teensy = sc.Teensy(sc.TEENSY)
    fire_pin = sc.FirePin()
    caps = sc.open_cameras()
    try:
        sc.set_gamma(caps, args.gamma)
        sc.settle_on_auto(caps)
        for _, dev in caps.values():
            set_manual_exposure(dev, args.exposure)
        time.sleep(sc.SETTLE_S)
        pulse = teensy.single_pulse(args.pulse_us)
        t_fire, got = sc.one_run(caps, fire_pin)
    finally:
        sc.set_gamma(caps, sc.DEFAULT_GAMMA)
        for cap, dev in caps.values():
            cap.release()
            set_manual_exposure(dev, None)
        fire_pin.close()
        teensy.close()

    # What is saved as the shot - and therefore what the analysis measures -
    # is the DIFFERENCE flash minus ambient. Everything the flash does not
    # light drops out: on the first try (2026-11-11, room lamps on, 8 ms
    # exposure) the patterned carpet in the plain flash frame gave two
    # "ball-shaped objects". The flash frame and the ambient frame are kept
    # beside it for reference.
    frames, flash, ambient, rises = {}, {}, {}, {}
    for n in (1, 2):
        flash[n], ambient[n], rises[n] = lit_frame(got[n], t_fire)
        diff = cv2.subtract(flash[n], ambient[n])
        # Stretched linearly so its brightest 0.05 % sits at 220: under room
        # lamps the difference is faint (tone curve, see strobe README) and
        # the circle detector's edge threshold is absolute. A linear stretch
        # moves no edge, so the geometry is untouched.
        top = max(float(np.percentile(diff, 99.95)), 1.0)
        frames[n] = np.clip(diff.astype(np.float32) * (220.0 / top), 0, 255).astype(np.uint8)
    unlit = [n for n in (1, 2) if rises[n] < sc.LIT_THRESHOLD]
    if unlit:
        print("NO FLASH in cam{} (rise {}) - nothing saved, take it again".format(
            ",".join(map(str, unlit)),
            " / ".join("%.0f" % rises[n] for n in (1, 2))))
        return 1

    for n in (1, 2):
        cv2.imwrite(os.path.join(dirs[n], name), frames[n])
        raw_dir = os.path.join(args.out, "raw", "cam{}".format(n))
        os.makedirs(raw_dir, exist_ok=True)
        stem = os.path.splitext(name)[0]
        cv2.imwrite(os.path.join(raw_dir, stem + "_flash.png"), flash[n])
        cv2.imwrite(os.path.join(raw_dir, stem + "_ambient.png"), ambient[n])
    bgr = {n: cv2.cvtColor(frames[n], cv2.COLOR_GRAY2BGR) for n in (1, 2)}
    ball, reason = ball_pair.find_ball_pair(rig, bgr[1], bgr[2])
    found = ball is not None
    shots.append({"name": name, "tape_mm": args.tape, "series": series,
                  "found": found, "strobe_pulse_us": pulse,
                  "exposure_us": args.exposure * 100, "gamma": args.gamma})
    cli_triangulate._write_manifest(args.out, shots)

    if found:
        print("{} {} tape {:.0f}: BALL at Z {:.0f} mm (X {:+.0f}, Y {:+.0f}; "
              "reproj {:.2f} px, size {:+.0f}%)  flash rise {:.0f} / {:.0f}".format(
                  name, series, args.tape, ball.depth_mm,
                  ball.xyz_m[0] * 1000.0, ball.xyz_m[1] * 1000.0,
                  ball.reprojection_px, ball.radius_error * 100.0,
                  rises[1], rises[2]))
    else:
        print("{} {} tape {:.0f}: NO BALL - {}  (saved; move the ball and "
              "retake)".format(name, series, args.tape, reason))
    print("{} shots in {}: {}".format(
        len(shots), args.out,
        ", ".join("{} {}".format(v, k) for k, v in
                  sorted(cli_triangulate._usable_counts(shots).items()))))
    return 0 if found else 2


if __name__ == "__main__":
    sys.exit(main())
