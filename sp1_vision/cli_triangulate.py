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
          where the lens plane sits.
  spread  4 positions off to the sides at assorted distances, AT LEAST 2.
          They do nothing for scale and everything for the plane: without
          lateral spread across the image width the floor fit is
          undetermined however small its residual, and pitch, roll AND yaw
          are all lost with it. Shot count does not substitute - six depth
          positions are one line no matter how many of them there are.
  target  2 positions along the intended target line. The floor plane cannot
          give yaw - it is rotationally symmetric about its own normal - and
          this pair is the only thing that can. It cannot be added afterwards
          without repeating the run.

HOW TO HOLD THE TAPE, since the analysis depends on it: every reading is the
PERPENDICULAR distance from the unit's front face to the ball - the distance
you would get by sliding a set square along the face - and NOT the
straight-line distance from one fixed mark. The images can be re-analysed
later; the operator's reading cannot. Only differences between depth readings
are used, so a constant error in where the face sits costs nothing, while a
change of method partway through the series costs everything.
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

# Spelt out at every shot rather than once at the top, because the two ways of
# holding a tape differ by a few millimetres over a 350 mm reading and the
# whole baseline question is 0.6%. The analysis compares DIFFERENCES of these
# against differences of triangulated Z, which is a perpendicular distance
# from the camera - so a perpendicular reading is the one that matches.
TAPE_PROMPT = ("  tape distance in mm, measured PERPENDICULAR to the unit's\n"
               "  front face (not straight-line from a mark): ")


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


REQUIRED_SHOT_FIELDS = (("name", str), ("tape_mm", (int, float)),
                        ("series", str))


def _shot_problem(shot):
    """Return a description of what is wrong with a manifest entry, or None.

    Structural validation only - it does not check that "series" is one of
    the three known labels, because run_analysis already prints an
    unknown-series row for that and carries on, which is the better answer
    for a typo'd label.
    """
    if not isinstance(shot, dict):
        return "is {}, not an object".format(type(shot).__name__)
    for key, expected in REQUIRED_SHOT_FIELDS:
        if key not in shot:
            return 'has no "{}"'.format(key)
        value = shot[key]
        if isinstance(value, bool) or not isinstance(value, expected):
            return '"{}" is {}, not {}'.format(
                key, repr(value),
                "a number" if key == "tape_mm" else "a string")
    return None


def _load_manifest(out_dir):
    """Load run.json from out_dir, returning its shots list.

    Returns an empty list if no manifest exists yet - that is the normal
    state for a brand-new run directory, not an error. A manifest that
    exists but cannot be parsed, or parses without a "shots" key, is a
    different situation: the tape readings it should hold cannot be
    reconstructed from the images alone, so this prints an operator-facing
    message naming the run directory and exits rather than guessing.

    Each entry is then checked for the three fields everything downstream
    indexes. A hand-edited manifest is not a hypothetical - the resume
    warning above tells the operator the file and the images disagree, and
    editing run.json is what they will do about it. A missing "tape_mm"
    would otherwise surface as a bare KeyError halfway down the analysis
    table, a long way from the file that caused it and from this message,
    which is the one written for them.
    """
    manifest_path = os.path.join(out_dir, RUN_MANIFEST)
    if not os.path.exists(manifest_path):
        return []
    try:
        with open(manifest_path) as fh:
            shots = json.load(fh)["shots"]
        if not isinstance(shots, list):
            raise TypeError('"shots" is {}, not a list'.format(
                type(shots).__name__))
    except (json.JSONDecodeError, KeyError, OSError, TypeError) as e:
        print("ERROR: run.json in {} is corrupt or unreadable: {}".format(
            out_dir, e))
        print("  The images on disk are still present.")
        print("  The tape readings for this run are lost.")
        sys.exit(1)

    problems = []
    for i, shot in enumerate(shots):
        problem = _shot_problem(shot)
        if problem is not None:
            problems.append("  shot {} (entry {}) {}".format(
                shot.get("name", "?") if isinstance(shot, dict) else "?",
                i, problem))
    if problems:
        print("ERROR: run.json in {} is readable but {} of its {} entries "
              "are incomplete:".format(out_dir, len(problems), len(shots)))
        for line in problems:
            print(line)
        print('  Every entry needs "name", "tape_mm" and "series".')
        print("  The images on disk are still present; fix the entries or "
              "delete them.")
        sys.exit(1)
    return shots


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
            tape_mm = _ask_float(TAPE_PROMPT)
            series = _ask_series()
            input("  place the ball, stand clear, press Enter: ")

            frames, skew = pair.grab_with_skew()
            found = {}
            for n, frame in frames.items():
                found[n], _ = frame_analysis.find_ball(frame)
                cv2.imwrite(os.path.join(dirs[n], name), frame)

            both = bool(found[1] and found[2])
            print("  cam1 {}  cam2 {}  skew {:.1f} ms  -> {}".format(
                "ball" if found[1] else " --  ",
                "ball" if found[2] else " --  ",
                skew * 1000.0,
                "keep" if both else "MOVE THE BALL AND RETAKE"))

            # "found" is recorded, not just printed. Without it the
            # completeness gate below counts shots that have no ball in them
            # and can green-light a series with, say, four depth entries of
            # which two the analysis will reject outright.
            shots.append({"name": name, "tape_mm": tape_mm, "series": series,
                          "found": both})
            _write_manifest(out_dir, shots)

    return _report_completeness(shots)


def _usable_counts(shots):
    """Per-series counts of shots that actually had a ball in both frames.

    Entries written before "found" was recorded are counted as usable: the
    alternative is declaring an older run empty, and the analysis will
    reject any of them that really are ball-less anyway.
    """
    return {label: sum(1 for s in shots
                       if s.get("series") == label and s.get("found", True))
            for label in sorted(set(SERIES.values()))}


def _report_completeness(shots):
    """Print what the series has and what it still needs; 0 if complete."""
    counts = _usable_counts(shots)
    usable = sum(counts.values())
    print("\n{} shots on disk, {} usable: {}".format(
        len(shots), usable,
        ", ".join("{} {}".format(v, k) for k, v in sorted(counts.items()))))

    short = []
    if counts["target"] < 2:
        short.append("yaw needs 2 usable target-line positions and cannot be "
                     "recovered later from a floor-only series")
    if counts["depth"] < 4:
        short.append("the scale fit needs 4+ usable collinear depth positions")
    if counts["spread"] < 2:
        # The gate this replaces was depth + spread >= 3, which six depth
        # shots satisfy on their own - and six depth shots are a LINE. The
        # plane fit then raises, and pitch, roll and yaw are all lost
        # together, after the operator has packed up. Spread is a
        # requirement in its own right for that reason.
        short.append("the floor plane needs 2+ usable spread positions: what "
                     "makes the plane determined is LATERAL spread across the "
                     "image width, not the number of shots. Depth positions "
                     "are collinear by design and fit any plane through their "
                     "line, so a depth-only series loses pitch, roll and yaw "
                     "at once")
    if counts["depth"] + counts["spread"] < 3:
        short.append("the floor plane needs 3+ usable floor positions in total")
    for line in short:
        print("INCOMPLETE: " + line)
    return 1 if short else 0


# A residual above this means the two rays did not really meet, so the point
# is not evidence about anything. Half a pixel is detection noise; two
# pixels is a mis-detection or a wrong correspondence.
MAX_REPROJECTION_PX = 2.0

# The distance the depth tolerance in the rig header is quoted at. The series
# spans roughly 350-700 mm, and the sensitivity goes as Z^2, so no single
# number covers it; 500 mm is the decided working distance and the midpoint of
# the suggested layout, which makes it the useful one to quote.
NOMINAL_WORKING_DISTANCE_M = 0.50


def _measure_shot(rig, run_dir, shot):
    """Return (xyz_m, worst_reprojection_px) or (None, reason).

    The reasons are all distinguishable in the printed table: a missing
    file, a frame at the wrong resolution, a missed detection, a degenerate
    ray pair, a residual over threshold, and a negative-depth (swap)
    rejection.

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
        # shape is (rows, cols, ...) so [1::-1] is (width, height), the order
        # rig.image_size uses. calibration_capture asks the driver for the
        # calibrated resolution best-effort and says itself that negotiation
        # can fall back; if it did, every intrinsic is wrong for these frames
        # and nothing downstream would say so.
        size = tuple(frame.shape[1::-1])
        if size != rig.image_size:
            return None, "cam{} is {}x{}, not {}x{}".format(
                n, size[0], size[1], rig.image_size[0], rig.image_size[1])
        frames[n] = frame

    circles = {}
    for n, frame in frames.items():
        found, circle = frame_analysis.find_ball(frame)
        if not found:
            return None, "no ball in cam{}".format(n)
        circles[n] = circle

    uv1 = circles[1][:2]
    uv2 = circles[2][:2]
    try:
        xyz = triangulate.triangulate_point(rig, uv1, uv2)
    except triangulate.TriangulationError as e:
        # The fifth rejection reason. This function is built around handing
        # back a reason per shot so one bad pair costs one row; letting a
        # degenerate pair escape as a traceback would cost the whole table,
        # including the rows already computed but not yet printed.
        return None, "degenerate: {}".format(e)
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
    # Printed here, above the table, because it is the tolerance the operator
    # needs while reading the deviations in it: one pixel of disparity error
    # is worth this many millimetres of depth, so a triangulated Z within
    # about this of the tape is agreement and not a discrepancy to chase.
    print("  depth tolerance: {:.2f} mm per px of disparity error at {:.0f} mm "
          "(about {:.2f} mm at half-pixel matching)".format(
              triangulate.depth_sensitivity_mm_per_px(
                  rig, NOMINAL_WORKING_DISTANCE_M),
              NOMINAL_WORKING_DISTANCE_M * 1000.0,
              triangulate.depth_sensitivity_mm_per_px(
                  rig, NOMINAL_WORKING_DISTANCE_M) / 2.0))

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

    # --- attitude ---------------------------------------------------------
    # This is the deliverable: three physical angles describing how the
    # unit sits against the floor, from geometry that owes nothing to
    # PiTrac and would be identical if PiTrac had never existed. Whether
    # and how it gets written into PiTrac's own constant is a separate,
    # later, and lossy question - kept in its own section below so the two
    # are never confused for one another.
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

    yaw = None
    yaw_line = "  yaw    not measured - needs 2 usable target-line shots"
    if len(buckets["target"]) >= 2:
        ordered = sorted(buckets["target"], key=lambda item: item[1][2])
        try:
            yaw = ground_plane.yaw_from_target_line(
                plane, ordered[0][1], ordered[-1][1])
            yaw_line = ("  yaw    {:+.3f} deg   target line to the "
                        "camera's right, positive".format(yaw))
        except ground_plane.PlaneFitError as e:
            yaw_line = "  yaw    could not be measured: {}".format(e)

    print("\nmeasured attitude of the unit")
    print("  pitch  {:+.3f} deg   nose-up positive".format(pitch))
    print("  roll   {:+.3f} deg   right-side-down positive".format(roll))
    print(yaw_line)
    # Pitch and roll are the CAMERA's own rotation; yaw is the TARGET LINE's
    # bearing as the camera sees it. The two senses are opposite, and the
    # header above calls all three "attitude", so say it here rather than
    # leave it to be inferred - and do NOT quietly negate one to match, since
    # which sign the unit's own pan convention wants is unresolved until the
    # hardware run.
    print("  NOTE the yaw sign is not the same sense as the other two. Pitch")
    print("  and roll describe how the CAMERA is rotated; yaw describes where")
    print("  the TARGET LINE runs as the camera sees it, so it is the")
    print("  NEGATION of the unit's own yaw - a unit yawed to the right sees")
    print("  the line off to its left.")
    print("  from {} floor positions, plane rms {:.2f} mm, conditioning "
          "{:.3f}".format(len(floor), plane.rms_m * 1000.0, plane.conditioning))
    # A direct measurement of the 115 mm mounting height the rest of the
    # project only assumes. The plane runs through ball CENTRES, one radius
    # above the floor, so the radius is added back.
    print("  camera 1 sits {:.1f} mm above the floor (the spec assumes 115); "
          "ball centres are {:.1f} mm below it".format(
              ground_plane.camera_height_above_floor_m(plane) * 1000.0,
              (ground_plane.camera_height_above_floor_m(plane)
               - ground_plane.GOLF_BALL_RADIUS_M) * 1000.0))

    # --- scale ----------------------------------------------------------
    # The measured side is the DEPTH COMPONENT, xyz_b[2] - xyz_a[2], and not
    # the 3D separation norm(xyz_b - xyz_a). The tape reading is a
    # perpendicular distance to the unit's face, so a difference of two of
    # them is a difference of perpendicular distances - which is what a
    # difference of Z is, and is not what a 3D point-to-point separation is.
    #
    # The two agree only if the depth line is both perfectly straight and
    # exactly perpendicular to the face, and BOTH departures inflate only the
    # measured side: 5 mm of lateral wander on a 70 mm gap adds 0.26%, and a
    # line oblique by 5 deg adds 0.38%. Since a scale above 1 prints a
    # SMALLER implied baseline, both errors push the answer toward 78.28 and
    # away from 78.749 - and the signal being resolved between those two is
    # 0.6%. The obliquity in particular is unconstrained, because the unit's
    # forward axis is exactly what this run has not yet measured.
    #
    # Camera 1's z = 0 plane is not the physical lens plane, but that offset
    # is constant and cancels in differences. The residual tilt between the
    # two is the sub-degree attitude measured above, worth under 0.02%.
    depth_ordered = sorted(buckets["depth"], key=lambda item: item[0]["tape_mm"])
    measured, taped = [], []
    for (shot_a, xyz_a), (shot_b, xyz_b) in zip(depth_ordered, depth_ordered[1:]):
        gap_tape = (shot_b["tape_mm"] - shot_a["tape_mm"]) / 1000.0
        if gap_tape <= 0.0:
            print("  skipping {} -> {}: tape did not increase ({:.1f} -> "
                  "{:.1f} mm)".format(shot_a["name"], shot_b["name"],
                                       shot_a["tape_mm"], shot_b["tape_mm"]))
            continue
        measured.append(float(xyz_b[2] - xyz_a[2]))
        taped.append(gap_tape)

    if len(measured) >= 3:
        scale, rms = triangulate.fit_scale_factor(measured, taped)
        print("\nscale against tape: {:.4f} over {} depth displacements "
              "(residual {:.2f} mm)".format(scale, len(measured), rms * 1000.0))
        print("  implied baseline: {:.3f} mm against the file's {:.3f} mm".format(
            rig.baseline_m * 1000.0 / scale, rig.baseline_m * 1000.0))
        # Using the depth component makes the scale immune to a crooked
        # depth line, but a crooked line is still worth knowing about - it
        # means the tape readings themselves were taken along something
        # other than what was intended. Reported so it is visible rather
        # than silent.
        straightness = triangulate.straightness_rms_m(
            np.array([xyz for _, xyz in depth_ordered]))
        print("  depth line straightness: {:.1f} mm rms off its own best-fit "
              "line (scale uses Z alone, so this does not bias it)".format(
                  straightness * 1000.0))
    else:
        # len(depth_ordered), not len(measured) + 1 - a skipped non-
        # increasing pair above would otherwise undercount how many depth
        # positions are actually present.
        print("\nscale: needs 4+ usable collinear depth positions, "
              "have {}".format(len(depth_ordered)))

    # --- writing this into PiTrac's legacy constant, explicitly a lossy
    # inheritance and not the measurement itself ---------------------------
    offset = stereo_geometry.camera2_offset_from_camera1(rig)
    print("\nwriting this into PiTrac's kCameraNAngles")
    print("  A two-element [pan, tilt] from PiTrac, whose cameras are")
    print("  individually aimed and whose roll is zero by construction.")
    print("  Ours is a three-axis residual of a bolted plate, so the")
    print("  mapping drops one of the three.")
    print()
    print('  "kCamera2OffsetFromCamera1OriginMeters": '
          "[{:.6f}, {:.6f}, {:.6f}]".format(*offset))
    # An unmeasured pan is printed as a placeholder, never as 0.000. Twenty
    # lines below, roll is called "DROPPED, not zero"; printing a fabricated
    # zero for pan here - in a line shaped to be copied straight into the
    # config - would hold pan to a lower standard than roll, and it is the
    # copyable line that does the damage.
    if yaw is None:
        print('  "kCamera1Angles": [ ????, {:+.3f}]   (pan, tilt) - pan NOT '
              "MEASURED, do not paste a zero".format(pitch))
    else:
        print('  "kCamera1Angles": [{:+.3f}, {:+.3f}]   (pan, tilt)'.format(
            yaw, pitch))
    print("  kCamera2Angles is deliberately NOT printed. Camera 2 is rotated "
          "relative to camera 1 by the extrinsics' R - about a degree on this "
          "rig - so its pan and tilt are NOT the numbers above, and copying "
          "these into both lands that degree straight in HLA and VLA. "
          "Deriving camera 2's own angles needs the attitude composed with R, "
          "which is Block 2's full-rotation job, not this constant's.")
    print()
    # Tilt's sign is anchored, not guessed: PiTrac ships kCamera1Angles =
    # [18.72, -24.18] for a camera physically tilted DOWN toward the tee,
    # and docs/camera/camera-calibration.md:171 says "Y/tilt is negative as
    # the camera starts to face down" - exactly attitude_from_plane's
    # convention (negative pitch for nose-down). Do not re-derive this.
    print("  tilt = pitch.  {:+.3f} deg. Sign anchored: PiTrac ships "
          "kCamera1Angles = [18.72, -24.18] for a camera tilted DOWN toward "
          "the tee, and docs/camera/camera-calibration.md:171 says \"Y/tilt "
          "is negative as the camera starts to face down\" - matching "
          "attitude_from_plane's convention (negative pitch for "
          "nose-down).".format(pitch))
    if yaw is None:
        print("  pan  = yaw.    not measured - needs 2 usable target-line "
              "shots.")
    else:
        # Pan has NO such anchor. yaw_from_target_line's convention is
        # "positive means the target line runs to the camera's right";
        # PiTrac's pan is the camera's own twist, positive counter-
        # clockwise viewed from above - plausibly the opposite sign, or not
        # even the same quantity. A wrong sign here lands 1:1 in horizontal
        # launch angle, silently, so this is not printed as settled.
        print("  pan  = yaw.    {:+.3f} deg. SIGN UNVERIFIED. This is the "
              "angle from the camera's forward axis to the target line, "
              "positive meaning the target line runs to the camera's "
              "right (yaw_from_target_line's convention). Whether that "
              "matches PiTrac's own pan convention - positive "
              "counter-clockwise viewed from above - has not been checked. "
              "Confirm against the physical target-line placement when "
              "this capture run is actually done.".format(yaw))
    print("  roll = {:+.3f} deg is DROPPED, not zero: kCamera1Angles "
          "carries no roll term to hold it.".format(roll))
    print("\nBlock 2 should carry the attitude as a full rotation applied "
          "to triangulated points rather than as two Euler angles in this "
          "constant, since the constant cannot hold what we measure.")
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
                        default=stereo_geometry.DEFAULT_EXTRINSICS_PATH,
                        metavar="PATH",
                        help="stereo_extrinsics.json: R and T from the "
                             "calibration solve (default: %(default)s). Must "
                             "come from the SAME solve as --config; the two "
                             "are only self-consistent together")
    parser.add_argument("--config", default=stereo_geometry.DEFAULT_CONFIG_PATH,
                        metavar="PATH",
                        help="golf_sim_config.json: the camera matrices and "
                             "distortion vectors (default: %(default)s). Read "
                             "only - this tool never writes to it")
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
