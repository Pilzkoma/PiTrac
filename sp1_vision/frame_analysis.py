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


def board_sharpness(frame):
    """Sharpness measured over the calibration board itself.

    Returns (score, found). When no board is visible, falls back to the centred
    ROI and reports found=False, so the caller can say which it is showing.

    This exists because the centre ROI is a poor proxy while focusing. A board
    held below the middle of the frame leaves the ROI measuring a blank wall,
    and the number then reports the texture of the room rather than of the
    thing being focused - which is exactly how an evening once went, with a
    perfectly sharp lens reading 20 and a real focus problem hidden underneath
    it.
    """
    found, corners = find_board(frame, refine=False)
    if not found:
        return sharpness_score(frame), False
    gray = _as_gray(frame)
    xs, ys = corners[:, 0, 0], corners[:, 0, 1]
    y0, y1 = int(ys.min()), int(ys.max())
    x0, x1 = int(xs.min()), int(xs.max())
    if y1 - y0 < 8 or x1 - x0 < 8:
        return sharpness_score(frame), False
    return float(cv2.Laplacian(gray[y0:y1, x0:x1], cv2.CV_64F).var()), True


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


# A golf ball is 42.67 mm across. At fx = 900 px that is a 48 px radius at
# 40 cm, so the 35-70 cm measurement range spans roughly 55 px down to 27 px.
# The bounds below leave margin on both ends without admitting the lens
# barrel or a reflection on the floor.
BALL_MIN_RADIUS_PX = 20
BALL_MAX_RADIUS_PX = 70

# One ball is in frame, so any second detection is a false positive rather
# than a competing candidate. minDist is set wide enough that Hough cannot
# return two circles for the same ball.
BALL_MIN_SEPARATION_PX = 200


def find_ball(frame, min_radius=BALL_MIN_RADIUS_PX, max_radius=BALL_MAX_RADIUS_PX):
    """Locate the ball, returning (found, (u, v, r)) in pixels.

    Both images of a pair must be measured by this same function with the
    same parameters. The centre of a sphere's silhouette is not exactly the
    projection of its centre - it migrates outward with off-axis angle, by
    around 0.3 px at our geometry - but that bias is common to both cameras
    and largely cancels in disparity. A *difference* in how the two images
    are measured does not cancel, and is far larger. Hence one function.

    Returns (False, None) rather than a best guess when nothing is found:
    a wrong centre produces a confident, wrong 3D point, and only the
    reprojection residual would catch it.
    """
    gray = _as_gray(frame)
    gray = cv2.medianBlur(gray, 5)
    circles = cv2.HoughCircles(
        gray, cv2.HOUGH_GRADIENT, dp=1.0, minDist=BALL_MIN_SEPARATION_PX,
        param1=100, param2=30, minRadius=int(min_radius), maxRadius=int(max_radius),
    )
    if circles is None:
        return False, None
    # OpenCV returns candidates strongest-accumulator first.
    u, v, r = circles[0][0]
    return True, (float(u), float(v), float(r))
