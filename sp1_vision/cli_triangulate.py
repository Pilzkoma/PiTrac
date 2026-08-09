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
import numpy as np

from sp1_vision import (calibration_capture, frame_analysis, ground_plane,
                        stereo_geometry, triangulate)

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


def _load_manifest(out_dir):
    """Load run.json from out_dir, returning its shots list.

    Returns an empty list if no manifest exists yet - that is the normal
    state for a brand-new run directory, not an error. A manifest that
    exists but cannot be parsed, or parses without a "shots" key, is a
    different situation: the tape readings it should hold cannot be
    reconstructed from the images alone, so this prints an operator-facing
    message naming the run directory and exits rather than guessing.
    """
    manifest_path = os.path.join(out_dir, RUN_MANIFEST)
    if not os.path.exists(manifest_path):
        return []
    try:
        with open(manifest_path) as fh:
            return json.load(fh)["shots"]
    except (json.JSONDecodeError, KeyError, OSError) as e:
        print("ERROR: run.json in {} is corrupt or unreadable: {}".format(
            out_dir, e))
        print("  The images on disk are still present.")
        print("  The tape readings for this run are lost.")
        sys.exit(1)


def _write_manifest(out_dir, shots):
    """Atomically (re)write run.json in out_dir with the given shots list.

    Writes to a temp file in the same directory - so os.replace is atomic
    even if out_dir is a different filesystem from the system temp dir -
    then replaces the manifest in one step. If anything raises before the
    replace, the temp file is removed and the previous manifest, if any, is
    left untouched.
    """
    manifest_path = os.path.join(out_dir, RUN_MANIFEST)
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


def _resume_start_number(dirs, shots):
    """Decide the next shot number to use when resuming into an existing run.

    Compares the highest gs_NN number found on disk (in cam1's directory)
    against the number of shots already recorded in the manifest. A crash
    between writing an image pair and writing the manifest entry for it can
    leave these disagreeing in either direction; starting from the max of
    the two is the only choice that never overwrites an existing image.
    Divergence is reported naming both counts, since it means the run
    directory saw a crash and is worth a second look regardless.
    """
    max_on_disk = _find_max_shot_number(dirs[1])
    max_in_manifest = len(shots)
    if max_on_disk != max_in_manifest:
        print("WARNING: manifest has {} shots but disk has images up to gs_{:02d}".format(
            max_in_manifest, max_on_disk))
        if max_on_disk > max_in_manifest:
            print("  Restarting numbering from gs_{:02d}".format(max_on_disk + 1))
    return max(max_on_disk, max_in_manifest) + 1


def run_shots(count, out_dir, exposure_units):
    dirs = {n: os.path.join(out_dir, "cam{}".format(n)) for n in (1, 2)}
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)

    shots = _load_manifest(out_dir)
    if shots:
        print("{} shots already in {} - new ones are numbered after them."
              .format(len(shots), out_dir))

    start_num = _resume_start_number(dirs, shots)

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
            _write_manifest(out_dir, shots)

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


# A residual above this means the two rays did not really meet, so the point
# is not evidence about anything. Half a pixel is detection noise; two
# pixels is a mis-detection or a wrong correspondence.
MAX_REPROJECTION_PX = 2.0


def _measure_shot(rig, run_dir, shot):
    """Return (xyz_m, worst_reprojection_px) or (None, reason).

    A shot is accepted only when BOTH hold:
      - the worse of the two reprojection residuals is within
        MAX_REPROJECTION_PX;
      - the triangulated point is in front of camera 1 (xyz[2] > 0).

    The residual by itself is not a sufficient guard against a left/right
    camera swap. On a rig that happened to be exactly rectified, a swapped
    correspondence solves in closed form to Z' = -Z - a real ray
    intersection, just behind the camera - with a reprojection residual of
    EXACTLY ZERO (worked through in triangulate.py's module docstring). This
    rig is not exactly rectified - it carries 0.92 deg of pitch - so the
    residual happens to also catch a swap here, but that is a property of
    THIS mount, not of the check: the residual's swap sensitivity is
    roughly 2*f*theta px, which goes to zero as the mount is ever shimmed
    flatter. The sign of Z is the guard that holds regardless, so it stays
    even though it looks redundant with the residual check on this
    particular rig. Do not remove it as redundant.
    """
    frames = {}
    for n in (1, 2):
        path = os.path.join(run_dir, "cam{}".format(n), shot["name"])
        frame = cv2.imread(path)
        if frame is None:
            return None, "missing {}".format(path)
        frames[n] = frame

    circles = {}
    for n, frame in frames.items():
        found, circle = frame_analysis.find_ball(frame)
        if not found:
            return None, "no ball in cam{}".format(n)
        circles[n] = circle

    uv1 = circles[1][:2]
    uv2 = circles[2][:2]
    xyz = triangulate.triangulate_point(rig, uv1, uv2)
    e1, e2 = triangulate.reprojection_error(rig, xyz, uv1, uv2)
    worst = max(e1, e2)

    if worst > MAX_REPROJECTION_PX:
        return None, "reproj {:.2f} px > {:.1f} px".format(worst, MAX_REPROJECTION_PX)
    if xyz[2] <= 0.0:
        return None, ("behind camera 1 (Z {:.1f} mm) - check for a "
                      "left/right camera swap".format(xyz[2] * 1000.0))
    return xyz, worst


def run_analysis(run_dir, extrinsics_path, config_path):
    try:
        rig = stereo_geometry.load_rig(extrinsics_path, config_path)
        stereo_geometry.validate_rig(rig)
    except stereo_geometry.StereoRigError as e:
        print("ERROR: {}".format(e))
        return 1
    print("rig: baseline {:.3f} mm, fx {:.1f} / {:.1f}".format(
        rig.baseline_m * 1000.0, rig.k1[0, 0], rig.k2[0, 0]))

    shots = _load_manifest(run_dir)

    print("\n{:<12} {:>7} {:>9} {:>9} {:>9} {:>9} {:>7} {:>5}".format(
        "shot", "series", "X mm", "Y mm", "Z mm", "tape mm", "reproj", "use"))
    buckets = {"depth": [], "spread": [], "target": []}
    for shot in shots:
        if shot.get("series") not in buckets:
            print("{:<12} {:>62}".format(
                shot["name"], "unknown series " + repr(shot.get("series"))))
            continue
        xyz, info = _measure_shot(rig, run_dir, shot)
        if xyz is None:
            # info is a rejection reason - distinct text for a missing
            # file, a missed detection, a residual over threshold, and a
            # negative-depth (swap) rejection, so the table shows which of
            # those four happened rather than a single flat "NO".
            print("{:<12} {:>7} {:>54}".format(
                shot["name"], shot["series"], info))
            continue
        print("{:<12} {:>7} {:9.1f} {:9.1f} {:9.1f} {:9.1f} {:7.2f} {:>5}".format(
            shot["name"], shot["series"], xyz[0] * 1000, xyz[1] * 1000,
            xyz[2] * 1000, shot["tape_mm"], info, "yes"))
        buckets[shot["series"]].append((shot, xyz))

    # The plane wants every floor position it can get - spread across the
    # image width is exactly what makes it determined. The scale fit does
    # NOT: it equates a 3D distance with a difference of two tape readings,
    # and that identity holds only along the collinear depth line.
    floor = buckets["depth"] + buckets["spread"]
    if len(floor) < 3:
        print("\nOnly {} usable floor shots; a plane needs 3.".format(len(floor)))
        return 1

    # --- attitude -------------------------------------------------------
    try:
        plane = ground_plane.fit_plane(np.array([xyz for _, xyz in floor]))
        pitch, roll = ground_plane.attitude_from_plane(plane)
    except ground_plane.PlaneFitError as e:
        # fit_plane's near-collinear message names exactly what to do about
        # it - spread the ball positions across the image width - so it is
        # written for the operator reading this output, and is wasted
        # inside a stack trace instead.
        print("\nERROR: {}".format(e))
        return 1
    print("\nfloor plane: rms {:.2f} mm, conditioning {:.3f}".format(
        plane.rms_m * 1000.0, plane.conditioning))
    print("  pitch {:+.3f} deg   roll {:+.3f} deg".format(pitch, roll))

    yaw = None
    if len(buckets["target"]) >= 2:
        ordered = sorted(buckets["target"], key=lambda item: item[1][2])
        try:
            yaw = ground_plane.yaw_from_target_line(
                plane, ordered[0][1], ordered[-1][1])
            print("  yaw   {:+.3f} deg".format(yaw))
        except ground_plane.PlaneFitError as e:
            print("  yaw     could not be measured: {}".format(e))
    else:
        print("  yaw     not measured - needs 2 usable target-line shots")

    # --- scale ----------------------------------------------------------
    depth_ordered = sorted(buckets["depth"], key=lambda item: item[0]["tape_mm"])
    measured, taped = [], []
    for (shot_a, xyz_a), (shot_b, xyz_b) in zip(depth_ordered, depth_ordered[1:]):
        gap_tape = (shot_b["tape_mm"] - shot_a["tape_mm"]) / 1000.0
        if gap_tape <= 0.0:
            print("  skipping {} -> {}: tape did not increase ({:.1f} -> "
                  "{:.1f} mm)".format(shot_a["name"], shot_b["name"],
                                       shot_a["tape_mm"], shot_b["tape_mm"]))
            continue
        measured.append(float(np.linalg.norm(xyz_b - xyz_a)))
        taped.append(gap_tape)

    if len(measured) >= 3:
        scale, rms = triangulate.fit_scale_factor(measured, taped)
        print("\nscale against tape: {:.4f} over {} displacements "
              "(residual {:.2f} mm)".format(scale, len(measured), rms * 1000.0))
        print("  implied baseline: {:.3f} mm against the file's {:.3f} mm".format(
            rig.baseline_m * 1000.0 / scale, rig.baseline_m * 1000.0))
    else:
        # len(depth_ordered), not len(measured) + 1 - a skipped non-
        # increasing pair above would otherwise undercount how many depth
        # positions are actually present.
        print("\nscale: needs 4+ usable collinear depth positions, "
              "have {}".format(len(depth_ordered)))

    # --- what to type into the config -----------------------------------
    offset = stereo_geometry.camera2_offset_from_camera1(rig)
    print("\n--- values for golf_sim_config.json (enter by hand) ---")
    print('  "kCamera2OffsetFromCamera1OriginMeters": '
          "[{:.6f}, {:.6f}, {:.6f}]".format(*offset))
    print('  "kCamera1Angles": [{:+.3f}, {:+.3f}]  (pan, tilt)'.format(
        0.0 if yaw is None else yaw, pitch))
    # Tilt's sign is anchored, not guessed: PiTrac ships kCamera1Angles =
    # [18.72, -24.18] for a camera physically tilted DOWN toward the tee,
    # and docs/camera/camera-calibration.md:171 says "Y/tilt is negative as
    # the camera starts to face down" - exactly attitude_from_plane's
    # convention (negative pitch for nose-down). Do not re-derive this.
    print("  tilt {:+.3f} deg - sign checked against PiTrac's own "
          "camera-tilted-down convention.".format(pitch))
    if yaw is None:
        print("  pan: not measured - needs 2 usable target-line shots.")
    else:
        # Pan has NO such anchor. yaw_from_target_line's convention is
        # "positive means the target line runs to the camera's right";
        # PiTrac's pan is the camera's own twist, positive counter-
        # clockwise viewed from above - plausibly the opposite sign, or not
        # even the same quantity. A wrong sign here lands 1:1 in horizontal
        # launch angle, silently, so this is not printed as settled.
        print("  pan {:+.3f} deg - SIGN UNVERIFIED. This is the angle from "
              "the camera's forward axis to the target line, positive "
              "meaning the target line runs to the camera's right. Whether "
              "that matches PiTrac's own pan convention has not been "
              "checked - confirm against the physical target-line "
              "placement when this capture run is actually done.".format(yaw))
    print("  roll {:+.3f} deg has nowhere to go in this two-element "
          "constant - kCamera1Angles carries no roll term, so this "
          "measured quantity is dropped here, not zero.".format(roll))
    return 0


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
    parser.add_argument("--analyse", metavar="RUNDIR",
                        help="analyse a captured run directory")
    parser.add_argument("--extrinsics",
                        default=stereo_geometry.DEFAULT_EXTRINSICS_PATH)
    parser.add_argument("--config", default=stereo_geometry.DEFAULT_CONFIG_PATH)
    args = parser.parse_args(argv)

    if args.analyse and args.shots:
        parser.error("--analyse and --shots do different things; pick one")
    if args.shots:
        return run_shots(args.shots, args.out, args.exposure)
    if args.analyse:
        return run_analysis(args.analyse, args.extrinsics, args.config)
    parser.error("give either --shots N or --analyse RUNDIR")


if __name__ == "__main__":
    sys.exit(main())
