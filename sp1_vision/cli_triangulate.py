#!/usr/bin/env python3
"""Capture and analyse a triangulation measurement series.

Capture:  python3 -m sp1_vision.cli_triangulate --shots 12 --out RUNDIR
Analyse:  python3 -m sp1_vision.cli_triangulate --analyse RUNDIR

The series measures three things at once, which is why it is one series and
not three:

  * whether triangulation agrees with a tape measure at all;
  * how the device sits against the floor, which nothing has ever measured;
  * which baseline is right, 78.28 mm or the 78.749 in the extrinsics file.

The suggested layout, 12 shots:

  depth   6 positions along a straight line running directly away from the
          unit, tape-measured, e.g. 350 / 420 / 490 / 560 / 630 / 700 mm.
          Consecutive gaps are known precisely, which is what settles the
          baseline - measuring DIFFERENCES isolates scale from any error in
          where the lens plane sits. These must be collinear: the scale fit
          equates 3D distance with a difference of tape readings, and that
          only holds along one line.
  spread  4 positions off to the sides at assorted distances. They do nothing
          for scale and everything for the plane: without spread across the
          image width the floor fit is undetermined, however small its
          residual.
  target  2 positions along the intended target line. The floor plane cannot
          give yaw - it is rotationally symmetric about its own normal - and
          this pair is the only thing that can. It cannot be added afterwards
          without repeating the run.
"""

import argparse
import json
import os
import re
import sys
import tempfile

import cv2

from sp1_vision import calibration_capture, frame_analysis

RUN_MANIFEST = "run.json"


def _ask_float(prompt):
    while True:
        raw = input(prompt).strip()
        try:
            return float(raw)
        except ValueError:
            print("  need a number, e.g. 420.5")


SERIES = {"d": "depth", "s": "spread", "t": "target"}


def _ask_series():
    """Which of the three series this position belongs to.

    Asked rather than inferred because the three are consumed differently and
    no amount of after-the-fact geometry recovers the distinction reliably.
    """
    while True:
        raw = input("  series - [d]epth line / [s]pread / [t]arget line: ")
        key = raw.strip().lower()[:1]
        if key in SERIES:
            return SERIES[key]
        print("  answer d, s or t")


def _find_max_shot_number(cam_dir):
    """Return the highest gs_NN number found in the directory, or 0.

    Used to detect when the manifest and disk have diverged.
    """
    if not os.path.exists(cam_dir):
        return 0
    max_num = 0
    for entry in os.listdir(cam_dir):
        match = re.match(r"^gs_(\d+)\.png$", entry)
        if match:
            max_num = max(max_num, int(match.group(1)))
    return max_num


def run_shots(count, out_dir, exposure_units):
    dirs = {n: os.path.join(out_dir, "cam{}".format(n)) for n in (1, 2)}
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)

    manifest_path = os.path.join(out_dir, RUN_MANIFEST)
    shots = []
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path) as fh:
                shots = json.load(fh)["shots"]
        except (json.JSONDecodeError, KeyError, OSError) as e:
            print("ERROR: run.json in {} is corrupt or unreadable: {}".format(
                out_dir, e))
            print("  The images on disk are still present.")
            print("  The tape readings for this run are lost.")
            sys.exit(1)
        print("{} shots already in {} - new ones are numbered after them."
              .format(len(shots), out_dir))

    # Check if manifest and disk have diverged, which a crash could cause.
    # Start numbering after the larger of the two.
    max_on_disk = _find_max_shot_number(dirs[1])
    max_in_manifest = len(shots)
    if max_on_disk != max_in_manifest:
        print("WARNING: manifest has {} shots but disk has images up to gs_{:02d}".format(
            max_in_manifest, max_on_disk))
        if max_on_disk > max_in_manifest:
            print("  Restarting numbering from gs_{:02d}".format(max_on_disk + 1))
        # In both cases, start from the max
        start_num = max(max_on_disk, max_in_manifest) + 1
    else:
        start_num = len(shots) + 1

    print(__doc__)
    with calibration_capture.CameraPair(exposure_units=exposure_units) as pair:
        for i in range(start_num, start_num + count):
            name = "gs_{:02d}.png".format(i)
            print("\n--- shot {} ---".format(i))
            tape_mm = _ask_float("  tape distance to the lens plane, mm: ")
            series = _ask_series()
            input("  place the ball, stand clear, press Enter: ")

            frames, skew = pair.grab_with_skew()
            found = {}
            for n, frame in frames.items():
                found[n], _ = frame_analysis.find_ball(frame)
                cv2.imwrite(os.path.join(dirs[n], name), frame)

            both = found[1] and found[2]
            print("  cam1 {}  cam2 {}  skew {:.1f} ms  -> {}".format(
                "ball" if found[1] else " --  ",
                "ball" if found[2] else " --  ",
                skew * 1000.0,
                "keep" if both else "MOVE THE BALL AND RETAKE"))

            shots.append({"name": name, "tape_mm": tape_mm, "series": series})
            # Write atomically: write to temp file in same directory, then replace.
            # This prevents losing the manifest if interrupted.
            fd, temp_path = tempfile.mkstemp(dir=out_dir, suffix=".tmp")
            try:
                with os.fdopen(fd, "w") as fh:
                    json.dump({"shots": shots}, fh, indent=2)
                os.replace(temp_path, manifest_path)
            except Exception:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
                raise

    counts = {label: sum(1 for s in shots if s["series"] == label)
              for label in sorted(set(SERIES.values()))}
    print("\n{} shots on disk: {}".format(
        len(shots),
        ", ".join("{} {}".format(v, k) for k, v in sorted(counts.items()))))

    short = []
    if counts["target"] < 2:
        short.append("yaw needs 2 target-line positions and cannot be "
                     "recovered later from a floor-only series")
    if counts["depth"] < 4:
        short.append("the scale fit needs 4+ collinear depth positions")
    if counts["depth"] + counts["spread"] < 3:
        short.append("the floor plane needs 3+ positions")
    for line in short:
        print("INCOMPLETE: " + line)
    return 1 if short else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--shots", type=int, metavar="N",
                        help="capture N ball positions, prompting for each")
    parser.add_argument("--out", default="sp1_vision/triangulation_run",
                        help="run directory for --shots (default: %(default)s)")
    parser.add_argument("--exposure", type=int, metavar="N",
                        help="manual exposure in 100 us units (1-5000); "
                             "omit for auto")
    args = parser.parse_args(argv)

    if args.shots:
        return run_shots(args.shots, args.out, args.exposure)
    parser.error("give --shots N")


if __name__ == "__main__":
    sys.exit(main())
