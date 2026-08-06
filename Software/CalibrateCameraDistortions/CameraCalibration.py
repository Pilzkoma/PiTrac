#!/usr/bin/env python3
"""Camera calibration for the Jetson LM.

Derived from PiTrac's original:
  - resolution is read from the images, not 1456x1088 baked in for the IMX296
  - image paths are arguments, not hardcoded globs
  - reprojection error is reported per image, so outliers can be dropped
  - the sub-pixel refined corners are actually used; the original computed
    cornerSubPix and then appended the coarse corners, discarding it
  - the board geometry comes from sp1_vision.frame_analysis rather than being
    declared again here. Two copies with nothing enforcing equality is how
    this project already lost a day to a stale USB port constant.

Output is a JSON block in golf_sim_config.json's shape, rather than .txt
files whose 3x3 matrix and 5-vector have to be transcribed by hand.

It also reports fx x 3.0 um, which is the measured focal length this whole
exercise exists to obtain: the configured 6.0 mm is the IMX296's, and the
2.74 mm we expect instead is derived from a manufacturer FOV figure rather
than observed.

    python3 CameraCalibration.py --images ../../sp1_vision/calibration_images/cam1 \
                                 --label Camera1
"""

import argparse
import glob
import json
import os
import sys

import cv2 as cv
import numpy as np

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sp1_vision.frame_analysis import CHESSBOARD_SIZE, SUBPIX_CRITERIA  # noqa: E402

# Square size only scales the translation vectors; the camera matrix and the
# distortion coefficients are unaffected. It is set for completeness, not
# because the print has to be exact.
SQUARE_SIZE_MM = 20.0

# OV9281: 1/4", 1280x800, 3.0 um square pixels.
PIXEL_PITCH_MM = 0.003


def object_points():
    objp = np.zeros((CHESSBOARD_SIZE[0] * CHESSBOARD_SIZE[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:CHESSBOARD_SIZE[0], 0:CHESSBOARD_SIZE[1]].T.reshape(-1, 2)
    return objp * SQUARE_SIZE_MM


def collect(image_dir):
    """Return (objpoints, imgpoints, size, used_files, skipped_files)."""
    files = sorted(glob.glob(os.path.join(image_dir, "*.png")))
    if not files:
        raise SystemExit("no PNGs found in " + image_dir)

    objp = object_points()
    objpoints, imgpoints, used, skipped = [], [], [], []
    size = None

    for path in files:
        img = cv.imread(path, cv.IMREAD_GRAYSCALE)
        if img is None:
            skipped.append((path, "unreadable"))
            continue
        if size is None:
            size = (img.shape[1], img.shape[0])
        elif (img.shape[1], img.shape[0]) != size:
            skipped.append((path, "size {}x{} differs from {}x{}".format(
                img.shape[1], img.shape[0], size[0], size[1])))
            continue

        found, corners = cv.findChessboardCorners(img, CHESSBOARD_SIZE, None)
        if not found:
            skipped.append((path, "no board"))
            continue
        # Use the refined corners. The original discarded them.
        corners = cv.cornerSubPix(img, corners, (11, 11), (-1, -1), SUBPIX_CRITERIA)
        objpoints.append(objp)
        imgpoints.append(corners)
        used.append(path)

    return objpoints, imgpoints, size, used, skipped


def per_image_errors(objpoints, imgpoints, rvecs, tvecs, mtx, dist):
    errors = []
    for i in range(len(objpoints)):
        projected, _ = cv.projectPoints(objpoints[i], rvecs[i], tvecs[i], mtx, dist)
        errors.append(cv.norm(imgpoints[i], projected, cv.NORM_L2) / len(projected))
    return errors


def config_block(label, mtx, dist):
    """Emit the two golf_sim_config.json keys, ready to paste."""
    return json.dumps({
        "kCamera{}CalibrationMatrix".format(label): [
            ["{:.12f}".format(v) for v in row] for row in mtx
        ],
        "kCamera{}DistortionVector".format(label): [
            "{:.12f}".format(v) for v in dist.ravel()
        ],
    }, indent=2)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", required=True,
                        help="directory of checkerboard PNGs")
    parser.add_argument("--label", default="1",
                        help="camera label for the config keys, 1 or 2")
    parser.add_argument("--save-npz",
                        help="write intrinsics here for the stereo step")
    parser.add_argument("--undistort-check", metavar="PNG",
                        help="write an original|undistorted side-by-side here, "
                             "so the result can be judged by eye")
    args = parser.parse_args(argv)

    objpoints, imgpoints, size, used, skipped = collect(args.images)
    print("using {} images at {}x{}".format(len(used), size[0], size[1]))
    for path, why in skipped:
        print("  skipped {}: {}".format(os.path.basename(path), why))
    if len(used) < 8:
        raise SystemExit("need at least 8 usable images, got {}".format(len(used)))

    rms, mtx, dist, rvecs, tvecs = cv.calibrateCamera(
        objpoints, imgpoints, size, None, None)

    errors = per_image_errors(objpoints, imgpoints, rvecs, tvecs, mtx, dist)
    print("\nreprojection error per image:")
    for path, err in sorted(zip(used, errors), key=lambda p: -p[1]):
        flag = "  <- outlier, consider removing" if err > 0.5 else ""
        print("  {:<28} {:.4f}{}".format(os.path.basename(path), err, flag))
    print("\n  mean {:.4f} px      RMS {:.4f} px".format(float(np.mean(errors)), rms))

    fx, fy = mtx[0, 0], mtx[1, 1]
    print("\nfx {:.2f} px   fy {:.2f} px   fy/fx {:.4f}".format(fx, fy, fy / fx))
    print("focal length  fx x {:.4f} mm/px = {:.3f} mm".format(
        PIXEL_PITCH_MM, fx * PIXEL_PITCH_MM))
    print("              fy x {:.4f} mm/px = {:.3f} mm".format(
        PIXEL_PITCH_MM, fy * PIXEL_PITCH_MM))
    print("sensor        {:.3f} x {:.3f} mm".format(
        size[0] * PIXEL_PITCH_MM, size[1] * PIXEL_PITCH_MM))
    if abs(fy / fx - 1.0) > 0.01:
        print("\nWARNING: fx and fy differ by more than 1%. The 3.0 um square-pixel")
        print("         assumption may be wrong - do not write these to config yet.")

    if args.undistort_check:
        # Numbers can look fine while the result is wrong. Straight edges
        # being straight is the check a person can actually make.
        sample = cv.imread(used[0])
        h, w = sample.shape[:2]
        newmtx, _ = cv.getOptimalNewCameraMatrix(mtx, dist, (w, h), 1, (w, h))
        mapx, mapy = cv.initUndistortRectifyMap(
            mtx, dist, None, newmtx, (w, h), cv.CV_16SC2)
        rectified = cv.remap(sample, mapx, mapy, cv.INTER_LINEAR)
        cv.imwrite(args.undistort_check, np.hstack([sample, rectified]))
        print("\nundistortion check written to {}".format(args.undistort_check))
        print("  left is the original, right is undistorted. The board's rows")
        print("  and columns must be straight on the right, and the squares")
        print("  the same size across the frame.")

    print("\ngolf_sim_config.json block:\n")
    print(config_block(args.label, mtx, dist))

    if args.save_npz:
        np.savez(args.save_npz, mtx=mtx, dist=dist, size=size,
                 objpoints=np.array(objpoints), imgpoints=np.array(imgpoints))
        print("\nintrinsics saved to " + args.save_npz)
    return 0


if __name__ == "__main__":
    sys.exit(main())
