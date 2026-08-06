#!/usr/bin/env python3
"""Command-line calibration capture - the fallback when the dashboard is down.

    python3 -m sp1_vision.cli_calibrate --focus
    python3 -m sp1_vision.cli_calibrate --shots 20 --out sp1_vision/calibration_images

The dashboard's calibration page is the better tool for this: it shows the
live picture, so focusing a lens is looking rather than guessing. This exists
for when the dashboard is not running, and to keep the capture module usable
without a browser in the loop.

Note that this opens the cameras directly rather than going through
CalibrationSession. A V4L2 node has a single owner, so if the dashboard is
holding them - it releases after two idle minutes, or on the button - this
will refuse to open, and say so.
"""

import argparse
import os
import sys
import time

import cv2

from sp1_vision import calibration_capture, frame_analysis

# Below this, the analysis scripts will refuse anyway, so say so at the end
# rather than letting someone discover it later.
MINIMUM_USABLE_PAIRS = 8


def run_focus(exposure_units):
    print("Focus mode. Turn each lens until its score peaks. Ctrl-C to stop.")
    print("The number has no absolute meaning - it depends on what the camera")
    print("is looking at - so watch which way it moves, not what it says.")
    with calibration_capture.CameraPair(exposure_units=exposure_units) as pair:
        try:
            while True:
                frames = pair.grab()
                scores = {
                    n: frame_analysis.sharpness_score(f) for n, f in frames.items()
                }
                print("\rcam1 {:9.1f}   cam2 {:9.1f}".format(scores[1], scores[2]),
                      end="", flush=True)
                time.sleep(0.5)
        except KeyboardInterrupt:
            print()


def run_shots(count, out_dir, exposure_units):
    dirs = {n: os.path.join(out_dir, "cam{}".format(n)) for n in (1, 2)}
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)

    existing = len([f for f in os.listdir(dirs[1]) if f.endswith(".png")])
    if existing:
        print("{} pairs already in {} - new ones are numbered after them."
              .format(existing, out_dir))

    print("Capturing {} pairs into {}. Starting in 5 s.".format(count, out_dir))
    time.sleep(5)

    good = 0
    with calibration_capture.CameraPair(exposure_units=exposure_units) as pair:
        for i in range(existing + 1, existing + count + 1):
            time.sleep(2)
            print("READY - hold still", flush=True)
            frames, skew = pair.grab_with_skew()

            found = {}
            for n, frame in frames.items():
                found[n], _ = frame_analysis.find_board(frame)
                cv2.imwrite(os.path.join(dirs[n], "gs_{:02d}.png".format(i)), frame)

            both = found[1] and found[2]
            good += 1 if both else 0
            print("  pair {:2d}: cam1 {}  cam2 {}  skew {:.1f} ms  -> {}".format(
                i,
                "board" if found[1] else "  --  ",
                "board" if found[2] else "  --  ",
                skew * 1000,
                "keep" if both else "MOVE THE BOARD AND RETRY"))

    total = existing + count
    print("\n{} of {} new pairs usable.".format(good, count))
    if total < MINIMUM_USABLE_PAIRS:
        print("Only {} pairs on disk. The analysis needs at least {}, and "
              "around 20 gives a usable result.".format(total, MINIMUM_USABLE_PAIRS))
        return 1
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--focus", action="store_true",
                        help="live sharpness score for focusing the lenses")
    parser.add_argument("--shots", type=int, metavar="N",
                        help="capture N simultaneous checkerboard pairs")
    parser.add_argument("--out", default="sp1_vision/calibration_images",
                        help="output directory for --shots "
                             "(default: sp1_vision/calibration_images, which is "
                             "where the dashboard writes too)")
    parser.add_argument("--exposure", type=int, metavar="N",
                        help="manual exposure in 100 us units (1-5000); "
                             "omit for auto")
    args = parser.parse_args(argv)

    if args.focus and args.shots:
        parser.error("--focus and --shots do different things; pick one")
    if args.focus:
        run_focus(args.exposure)
        return 0
    if args.shots:
        return run_shots(args.shots, args.out, args.exposure)
    parser.error("give either --focus or --shots N")


if __name__ == "__main__":
    sys.exit(main())
