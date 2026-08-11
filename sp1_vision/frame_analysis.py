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

# The same idea for the radius. Hough's radius is coarse - a quarter off on
# a bad day - but never off by half, so a fit that leaves this window has
# latched onto something that is not the seed's object. Both directions are
# on record from real frames: plain least squares collapsed 42.7 px to
# 25.5 px onto dimple texture, and an outermost-edge collector inflated
# 60.8 px to 87.3 px onto a cast shadow's rim.
REFINE_MAX_RADIUS_CHANGE = 0.25

# Angular resolution for silhouette collection: five degrees per direction.
REFINE_ANGULAR_BINS = 72

# MAD multiplier for the trimmed refit. Outline points further than this
# many spreads from the consensus of the rest are somebody else's contour.
REFINE_TRIM_K = 2.5

# The trim works on the distilled outline - at most one point per angular
# bin - so its floor is lower than REFINE_MIN_EDGE_POINTS, which guards the
# raw edge harvest. Three parameters through ten points spread over the
# circle is still overdetermined threefold.
REFINE_TRIM_MIN_POINTS = 10


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


def _outermost_per_direction(xs, ys, u, v):
    """The outermost edge point in each angular direction from (u, v).

    Dimples, a printed logo and wood grain all put Canny edges INSIDE the
    radial band, and on real frames they outnumber the silhouette wherever
    the shadow flank has no contrast. Whatever else those interior edges
    are, they are never the outline: along any one direction the silhouette
    is the last edge the ball can produce. This does NOT hold for edges
    beyond the ball - a cast shadow's rim is outside the silhouette and
    crisper than the shadow-side flank - which is why the selection is
    followed by a trimmed fit rather than trusted on its own.
    """
    dx, dy = xs - u, ys - v
    dist = np.hypot(dx, dy)
    angle = np.arctan2(dy, dx)
    bins = ((angle + np.pi) / (2.0 * np.pi)
            * REFINE_ANGULAR_BINS).astype(int) % REFINE_ANGULAR_BINS
    # Group-max without a Python loop: sort by (bin, distance), then the
    # last entry of each bin's run is that bin's outermost point.
    order = np.lexsort((dist, bins))
    sorted_bins = bins[order]
    run_ends = np.nonzero(np.append(sorted_bins[1:] != sorted_bins[:-1],
                                    True))[0]
    outermost = order[run_ends]
    return xs[outermost], ys[outermost]


def _trimmed_circle_fit(xs, ys):
    """Circle fit that discards points the consensus circle cannot explain.

    Plain least squares weights every point equally, and on a real ball
    that is the whole defect: the minority that is somebody else's contour
    - a shadow rim, a neighbouring object's edge - drags the fit off the
    majority that is the silhouette. Fit, measure each point's radial
    residual, drop the points more than REFINE_TRIM_K spreads from the
    consensus, refit. The spread is the median absolute deviation, which a
    minority of outliers cannot inflate the way it inflates a variance.

    A RANSAC-style consensus fit was tried in this spot and measured on the
    real pairs before being rejected. It recovers the true RADIUS better -
    the trimmed fit keeps some interior texture and reads 10-15% small -
    but it picks a slightly different inlier shell in each camera, and for
    stereo that is the wrong trade: the trimmed fit's bias is the SAME in
    both cameras and cancels in the disparity (goal pair 0.45 px, radius
    ratio 1.015), while the consensus fit's per-camera choices do not
    (1.22 px, ratio 0.928). The pair gates tolerate a common bias; nothing
    downstream tolerates a cross-camera difference.
    """
    fit = None
    for _ in range(REFINE_ITERATIONS):
        fit = _fit_circle(xs, ys)
        if fit is None:
            return None
        u, v, r = fit
        residual = np.hypot(xs - u, ys - v) - r
        med = float(np.median(residual))
        mad = float(np.median(np.abs(residual - med)))
        if mad < 1e-9:
            break
        keep = np.abs(residual - med) < REFINE_TRIM_K * mad
        if int(keep.sum()) < REFINE_TRIM_MIN_POINTS:
            break
        if int(keep.sum()) == xs.size:
            break
        xs, ys = xs[keep], ys[keep]
    return fit


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

    So this throws the polarity away and fits geometry: Canny edges around
    the seed, the OUTERMOST edge per angular direction (dimples and logos
    are interior, the silhouette is the last edge the ball can produce),
    then a MAD-trimmed fit over the distilled outline (a cast shadow's rim
    is EXTERIOR and can out-crisp the shadow-side flank, so the outermost
    selection must not be trusted on its own - the trim drops what the
    consensus of the rest cannot explain). Both halves are load-bearing,
    and both defects are on record from real frames: least squares over
    every band edge collapsed 42.7 px to 25.5 px onto the texture, and
    outermost-without-trim inflated 60.8 px to 87.3 px onto a shadow rim.

    The centre it returns is biased ONLY in ways shared by both cameras
    (the fit keeps some interior texture and reads the radius 10-15%
    small, identically on both sides), which is the property the stereo
    pair actually needs: a common bias cancels in the disparity, a
    cross-camera difference never does. A consensus/RANSAC fit that
    recovers the radius better was measured and rejected on exactly that
    ground - see _trimmed_circle_fit.

    Returns None rather than a guess when the outline is too broken to fit,
    or when the fit leaves the seed's neighbourhood in centre or radius -
    a refinement is a correction, not a new detection, and a fit that runs
    away has found somebody else's contour.
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
        outline_x, outline_y = _outermost_per_direction(
            xs[keep], ys[keep], centre_u, centre_v)
        if outline_x.size < REFINE_TRIM_MIN_POINTS:
            return None
        fit = _trimmed_circle_fit(outline_x, outline_y)
        if fit is None:
            return None
        centre_u, centre_v, radius = fit

    if np.hypot(centre_u - u, centre_v - v) > REFINE_MAX_DRIFT * r:
        return None
    if not ((1.0 - REFINE_MAX_RADIUS_CHANGE) * r
            <= radius <= (1.0 + REFINE_MAX_RADIUS_CHANGE) * r):
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

    # NOT refined here, deliberately, and it was measured twice: replacing
    # every candidate with its refinement handed wins to polished junk on
    # the cluttered 24-frame set both times it was tried (2026-08-11). The
    # refinement lives in ball_pair.find_ball_pair instead, where it can be
    # applied to the SELECTED pair - and to the whole candidate list only
    # as a rescue, after the raw selection has found nothing at all.
    return [(float(u), float(v), float(r)) for u, v, r in circles[0]]
