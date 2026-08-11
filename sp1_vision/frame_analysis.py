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

# The constant that used to sit here, BALL_MIN_SEPARATION_PX = 200, went with
# find_ball, and so did its reasoning: "one ball is in frame, so any second
# detection is a false positive rather than a competing candidate." That
# sentence was the whole bug. A second detection is a competing candidate,
# the room is full of them, and separating candidates by 200 px did not
# suppress false positives - it suppressed the ball whenever something
# stronger stood within 200 px of it.


# How far apart two candidates must be before Hough treats them as separate.
# Small on purpose: the point here is to MISS NOTHING, and a wide separation
# lets a strong neighbour delete the ball outright. In the 2026-08-10 run
# that is exactly what happened - at 40 px the ball in gs_03 was suppressed
# by a stronger circle beside it and never reached the pair selection.
CANDIDATE_MIN_SEPARATION_PX = 20

# Accumulator threshold. Lower admits more junk, which is the intended
# trade: junk is cheap to reject downstream with the rig, and a missed ball
# cannot be recovered at all.
#
# 30 lost the ball in camera 2 of the 2026-08-10 set; 22 lost it in camera 1
# of the 2026-08-11 set - a white ball on light wood has weaker gradient
# support than one against a dark speaker, and 22 sat right on that edge. 18
# finds it in both. Going that low was only affordable once the height band
# and the radius-ratio check existed to throw the extra junk away: on the
# same frames, 18 without them turned two good shots into "ambiguous".
CANDIDATE_ACCUMULATOR_THRESHOLD = 18


# How far out from the seed radius outline pixels are collected, as a
# fraction. Wide enough to hold a seed that is several pixels off, narrow
# enough to exclude a neighbouring object's edge.
REFINE_RADIAL_BAND = 0.45

# A circle has three parameters; fitting one to a handful of points fits the
# noise. Below this the outline is too broken to trust.
REFINE_MIN_EDGE_POINTS = 24

# How far the fit may travel from its seed before it is a different object
# rather than a correction, as a fraction of the seed radius.
REFINE_MAX_DRIFT = 0.8

REFINE_ITERATIONS = 3


def _fit_circle(xs, ys):
    """Algebraic circle fit through edge points; returns (u, v, r).

    Minimises the residual of x^2 + y^2 = 2ax + 2by + c, which is linear in
    (a, b, c) and so has a closed form. Every outline pixel counts the same
    regardless of which side of the ball it came from and regardless of
    whether it is a bright-to-dark or a dark-to-bright edge - that
    indifference is the entire point.
    """
    a_matrix = np.column_stack([xs, ys, np.ones(xs.size)])
    rhs = xs ** 2 + ys ** 2
    (two_a, two_b, c), _, _, _ = np.linalg.lstsq(a_matrix, rhs, rcond=None)
    u, v = two_a / 2.0, two_b / 2.0
    radius_sq = c + u * u + v * v
    if not np.isfinite(radius_sq) or radius_sq <= 0.0:
        return None
    return float(u), float(v), float(np.sqrt(radius_sq))


def refine_ball(frame, u, v, r):
    """Refit a candidate to the ball's OUTLINE. Returns (u, v, r) or None.

    HoughCircles votes along the image gradient, and the direction of that
    gradient flips where the ball is darker than what is behind it. A ball
    lit from one side has exactly that: one flank brighter than the surface,
    the other darker. The reversed flank votes AWAY from the true centre, so
    Hough settles on the bright arc - and settles differently in the two
    cameras, which see the shading from different angles. On real frames
    that showed up as 2.71 px of reprojection error with the ball plainly
    visible in both images, which is 10 mm of depth where the whole budget
    is 1.8 mm.

    So this throws the polarity away. It collects outline pixels around the
    seed, keeps those at a plausible radius, and fits a circle to their
    geometry alone. A dark-to-bright edge and a bright-to-dark edge are the
    same evidence about where the ball ends.

    Returns None rather than a guess when the outline is too broken to fit,
    or when the fit walks far enough from its seed to be a different object.

    NOT ON THE MEASURING PATH YET, and the reason is measured rather than
    suspected. On synthetic discs it is a clear win - 1.58 px down to
    0.26 px under a hard one-sided light, and 0.71 px (Hough's accumulator
    quantisation) down to under 0.05 px on an evenly lit one. On the real
    2026-08-11 frames, wiring it into ball_candidates made things worse:
    the cluttered 24-frame set dropped from 11 finds to 9 and its
    "no consistent pair" rejections rose from 4 to 9.

    The likely cause, to be confirmed with real frames rather than assumed:
    a real ball carries dimples and a printed logo, and the desk carries
    wood grain, so Canny returns plenty of edges INSIDE the radial band that
    have nothing to do with the silhouette. The fit weights them equally.
    What it probably needs is to keep only the outermost edge along each
    radial direction, and to reject outliers rather than least-squares
    everything it is handed.
    """
    gray = _as_gray(frame)
    height, width = gray.shape[:2]
    half = int(round(r * (1.0 + REFINE_RADIAL_BAND))) + 4
    x0, y0 = max(0, int(u) - half), max(0, int(v) - half)
    x1, y1 = min(width, int(u) + half + 1), min(height, int(v) + half + 1)
    roi = gray[y0:y1, x0:x1]
    if roi.size == 0 or min(roi.shape[:2]) < 8:
        return None

    # Thresholds from the ROI's own brightness, so the same code works on a
    # sunlit desk and a dim room. A fixed pair would be a lighting
    # assumption, and lighting is what this function exists to survive.
    median = float(np.median(roi))
    edges = cv2.Canny(cv2.GaussianBlur(roi, (5, 5), 0),
                      max(5.0, 0.66 * median), max(15.0, 1.33 * median))
    ys, xs = np.nonzero(edges)
    if xs.size < REFINE_MIN_EDGE_POINTS:
        return None
    xs = xs.astype(np.float64) + x0
    ys = ys.astype(np.float64) + y0

    centre_u, centre_v, radius = float(u), float(v), float(r)
    for _ in range(REFINE_ITERATIONS):
        distance = np.hypot(xs - centre_u, ys - centre_v)
        keep = (distance > radius * (1.0 - REFINE_RADIAL_BAND)) & \
               (distance < radius * (1.0 + REFINE_RADIAL_BAND))
        if int(keep.sum()) < REFINE_MIN_EDGE_POINTS:
            return None
        fit = _fit_circle(xs[keep], ys[keep])
        if fit is None:
            return None
        centre_u, centre_v, radius = fit

    if np.hypot(centre_u - u, centre_v - v) > REFINE_MAX_DRIFT * r:
        return None
    if not (0.5 * r <= radius <= 1.8 * r):
        return None
    return centre_u, centre_v, radius


def ball_candidates(frame, min_radius=BALL_MIN_RADIUS_PX,
                    max_radius=BALL_MAX_RADIUS_PX):
    """Every circular candidate in the frame, as a list of (u, v, r) floats.

    Deliberately permissive, and deliberately undecided. A single image
    cannot tell a golf ball from a loudspeaker cone: both are bright discs,
    and on 2026-08-10 the loudspeaker won 17 frames out of 24 because it was
    the stronger circle. Nothing in one image would ever have said so - the
    detector returned the same pixel in every frame while the ball moved
    across the table.

    What CAN tell them apart is the stereo pair: a golf ball is 42.67 mm
    across, so its apparent radius has to match the range that its own
    disparity implies, and it has to sit inside the measurement volume.
    That decision belongs in ball_pair.find_ball_pair, which is why this
    function makes none of it and hands back everything it saw.

    Both images of a pair must be measured by this same function with the
    same parameters. A silhouette centre is not exactly the projection of a
    sphere's centre - it migrates outward with off-axis angle, about 0.3 px
    at our geometry - but that bias is common to both cameras and largely
    cancels in disparity. A *difference* in how the two images are measured
    does not cancel.
    """
    gray = cv2.medianBlur(_as_gray(frame), 5)
    circles = cv2.HoughCircles(
        gray, cv2.HOUGH_GRADIENT, dp=1.0,
        minDist=CANDIDATE_MIN_SEPARATION_PX, param1=100,
        param2=CANDIDATE_ACCUMULATOR_THRESHOLD,
        minRadius=int(min_radius), maxRadius=int(max_radius),
    )
    if circles is None:
        return []

    # NOT refined here, deliberately - see refine_ball's own note. Wiring it
    # in was tried on 2026-08-11 and made real frames WORSE: the cluttered
    # set went from 11 finds to 9 and its "nothing consistent" rejections
    # from 4 to 9. It passes on synthetic discs and fails on real balls,
    # which is exactly the gap a synthetic fixture cannot show.
    return [(float(u), float(v), float(r)) for u, v, r in circles[0]]
