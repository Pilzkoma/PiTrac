#!/usr/bin/env python3
"""Frame maths used by the calibration tool. No cameras, no I/O."""

import cv2
import numpy as np

# Inner corners of the board in Software/CalibrateCameraDistortions/checkerboard.png.
# Verified 2026-08-06 against both that file and
# checkerboard_test_image_for_undistortion.png.
CHESSBOARD_SIZE = (9, 6)

# cornerSubPix termination, matching PiTrac's CameraCalibration.py.
SUBPIX_CRITERIA = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)


def _as_gray(frame):
    if frame.ndim == 3:
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return frame


def sharpness_score(frame, roi_fraction=0.4):
    """Variance of the Laplacian over a centred ROI.

    Higher is sharper. The absolute value is meaningless - it depends on
    scene content - so it is only useful while turning a lens and watching
    the number move. Restricting to the centre keeps a cluttered background
    from drowning out the subject.
    """
    gray = _as_gray(frame)
    if roi_fraction < 1.0:
        h, w = gray.shape[:2]
        rh, rw = int(h * roi_fraction), int(w * roi_fraction)
        y0, x0 = (h - rh) // 2, (w - rw) // 2
        gray = gray[y0:y0 + rh, x0:x0 + rw]
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def find_board(frame, refine=True):
    """Locate the calibration board.

    Returns (found, corners). Corners are sub-pixel refined when found -
    PiTrac's original computed the refinement and then appended the coarse
    corners instead, discarding it. Sub-pixel precision is what makes the
    stereo extrinsics trustworthy, so it is not optional here.
    """
    gray = _as_gray(frame)
    found, corners = cv2.findChessboardCorners(gray, CHESSBOARD_SIZE, None)
    if not found:
        return False, None
    if refine:
        corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), SUBPIX_CRITERIA)
    return True, corners
