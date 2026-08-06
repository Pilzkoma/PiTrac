#!/usr/bin/env python3
"""Stereo extrinsics for the Jetson LM camera pair.

Consumes the two per-camera .npz files written by CameraCalibration.py
--save-npz, plus the paired image directories, and reports the rotation and
translation between the cameras.

The CAD says the baseline is 80.00 mm with parallel optical axes
(Hardware/JetsonLM.step, read from the two M12 lens barrel placements). This
measures the same thing independently, which makes it a check on the
calibration and on the physical mount at once. A disagreement is a finding,
not a failure - most likely a camera sitting off its seat.

    python3 StereoCalibration.py --cam1-npz cam1.npz --cam2-npz cam2.npz \
        --cam1-images ../../sp1_vision/calibration_images/cam1 \
        --cam2-images ../../sp1_vision/calibration_images/cam2
"""

import argparse
import glob
import math
import os
import sys

import cv2 as cv
import numpy as np

from CameraCalibration import CHESSBOARD_SIZE, SUBPIX_CRITERIA, object_points

CAD_BASELINE_MM = 80.00

# Frame height, for expressing a vertical misalignment as a fraction of the
# image. The OV9281 gives 1280x800.
FRAME_HEIGHT_PX = 800

# Termination for the stereo solve. Deliberately not SUBPIX_CRITERIA, which is
# tuned for nudging a corner half a pixel: 30 iterations at eps 1e-3 is far too
# loose for a bundle adjustment over ~20 views.
STEREO_CRITERIA = (cv.TERM_CRITERIA_EPS + cv.TERM_CRITERIA_MAX_ITER, 100, 1e-5)

# Below this, rectification crops a couple of percent of frame height and
# there is nothing to do. Above it, shimming the offending camera is worth the
# trouble before accepting the calibration.
ACCEPTABLE_MISALIGNMENT_DEG = 3.0


def paired_corners(dir1, dir2):
    """Find boards in both images of each pair, keeping only complete pairs."""
    names1 = {os.path.basename(p) for p in glob.glob(os.path.join(dir1, "*.png"))}
    names2 = {os.path.basename(p) for p in glob.glob(os.path.join(dir2, "*.png"))}
    shared = sorted(names1 & names2)
    if not shared:
        raise SystemExit(
            "no image pairs share a filename between the two directories. "
            "Pairs must be captured simultaneously and written under matching "
            "names - sequential per-camera series cannot yield extrinsics.")

    objp = object_points()
    objpoints, pts1, pts2, used, dropped = [], [], [], [], []
    size = None

    for name in shared:
        img1 = cv.imread(os.path.join(dir1, name), cv.IMREAD_GRAYSCALE)
        img2 = cv.imread(os.path.join(dir2, name), cv.IMREAD_GRAYSCALE)
        if img1 is None or img2 is None:
            dropped.append((name, "unreadable"))
            continue
        if size is None:
            size = (img1.shape[1], img1.shape[0])
        if (img1.shape[1], img1.shape[0]) != size or img1.shape != img2.shape:
            dropped.append((name, "resolution differs from the first pair"))
            continue

        ok1, c1 = cv.findChessboardCorners(img1, CHESSBOARD_SIZE, None)
        ok2, c2 = cv.findChessboardCorners(img2, CHESSBOARD_SIZE, None)
        if not (ok1 and ok2):
            missing = "cam1" if not ok1 else "cam2"
            if not ok1 and not ok2:
                missing = "both cameras"
            dropped.append((name, "board missing in " + missing))
            continue

        pts1.append(cv.cornerSubPix(img1, c1, (11, 11), (-1, -1), SUBPIX_CRITERIA))
        pts2.append(cv.cornerSubPix(img2, c2, (11, 11), (-1, -1), SUBPIX_CRITERIA))
        objpoints.append(objp)
        used.append(name)

    return objpoints, pts1, pts2, size, used, dropped


def rotation_to_axis_degrees(R):
    """Return (pitch, yaw, roll) in degrees - rotation about X, Y and Z.

    Camera frame is X right (along the baseline), Y down, Z forward. So
    rotation about X tips a camera up or down relative to the other (pitch),
    about Y toes it in or out (yaw), and about Z turns the image in its own
    plane (roll).

    The three are not equally costly, which is the whole reason for splitting
    them out. Yaw feeds horizontal disparity, and rectification absorbs it as
    an offset. Pitch and roll produce *vertical* disparity, which is what
    turns correspondence search from a one-dimensional problem into a
    two-dimensional one.

    This uses the Rodrigues vector rather than an Euler decomposition. For the
    few degrees a printed mount produces, its components are the per-axis
    angles directly, and it avoids the axis-ordering traps that make
    hand-rolled Euler conversions easy to get subtly - and silently - wrong.
    """
    rvec, _ = cv.Rodrigues(R)
    return tuple(math.degrees(float(v)) for v in rvec.ravel())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cam1-npz", required=True,
                        help="intrinsics from CameraCalibration.py --save-npz")
    parser.add_argument("--cam2-npz", required=True)
    parser.add_argument("--cam1-images", required=True,
                        help="directory of camera 1 checkerboard PNGs")
    parser.add_argument("--cam2-images", required=True)
    args = parser.parse_args(argv)

    k1 = np.load(args.cam1_npz)
    k2 = np.load(args.cam2_npz)

    objpoints, pts1, pts2, size, used, dropped = paired_corners(
        args.cam1_images, args.cam2_images)
    print("using {} complete pairs at {}x{}".format(len(used), size[0], size[1]))
    for name, why in dropped:
        print("  dropped {}: {}".format(name, why))
    if len(used) < 8:
        raise SystemExit(
            "need at least 8 complete pairs, got {}".format(len(used)))

    # Intrinsics are already measured and trusted, so solve only for the pose.
    rms, _, _, _, _, R, T, _, _ = cv.stereoCalibrate(
        objpoints, pts1, pts2,
        k1["mtx"], k1["dist"], k2["mtx"], k2["dist"], size,
        criteria=STEREO_CRITERIA,
        flags=cv.CALIB_FIX_INTRINSIC,
    )

    baseline = float(np.linalg.norm(T))
    pitch, yaw, roll = rotation_to_axis_degrees(R)
    fx = float(k1["mtx"][0, 0])

    print("\nstereo RMS         {:.4f} px".format(rms))
    print("baseline           {:.2f} mm   (CAD says {:.2f} mm, delta {:+.2f} mm)".format(
        baseline, CAD_BASELINE_MM, baseline - CAD_BASELINE_MM))
    print("translation        [{:.2f}, {:.2f}, {:.2f}] mm".format(*T.ravel()))
    print("\nrelative rotation")
    print("  pitch {:+.3f} deg  (about X)  vertical disparity, watch this".format(pitch))
    print("  roll  {:+.3f} deg  (about Z)  vertical disparity, watch this".format(roll))
    print("  yaw   {:+.3f} deg  (about Y)  toe-in/out, absorbed as an offset".format(yaw))

    worst = max(abs(pitch), abs(roll))
    shift = fx * math.tan(math.radians(worst))
    print("\nworst vertical misalignment {:.3f} deg -> {:.1f} px shift".format(
        worst, shift))
    print("rectification crops roughly {:.1f}% of frame height".format(
        100.0 * shift / FRAME_HEIGHT_PX))
    if worst < ACCEPTABLE_MISALIGNMENT_DEG:
        print("-> under {:.0f} deg, no action needed".format(
            ACCEPTABLE_MISALIGNMENT_DEG))
    else:
        print("-> over {:.0f} deg, consider shimming before accepting this "
              "calibration".format(ACCEPTABLE_MISALIGNMENT_DEG))

    print("\nBaseline and axes are also readable from Hardware/JetsonLM.step.")
    print("A large disagreement means one of the two is wrong, and the mount")
    print("is the more likely of the pair.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
