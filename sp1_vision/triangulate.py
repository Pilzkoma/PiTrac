#!/usr/bin/env python3
"""Two image points in, one 3D point out - plus the check that it is real.

The reprojection residual returned alongside catches a mis-detected ball
and a genuinely inconsistent pair (correspondences that do not come from
one real point under this rig's geometry). It does NOT reliably catch a
left/right swap or an inverted translation: the residual is computed from
the same rig - K, R and T - that produced the point, so it is self-
consistent with whatever extrinsics it is handed, wrong sign and all. Its
sensitivity to a swap is proportional to the rig's departure from
rectified, roughly 2*f*theta px for a pitch or roll of theta radians - about
21 px at this rig's measured 0.92 deg pitch, and zero at R = I. The
structural guard against a swap is the sign of Z, not this residual; that
check belongs in the caller, not here.

It is necessary and not sufficient. A small residual means the two rays
intersect; it says nothing about scale. Scale comes from the baseline, and
the baseline is checked against a tape measure, not against this.
"""

import cv2
import numpy as np


class TriangulationError(ValueError):
    """The two rays do not yield a finite point."""


def triangulate_point(rig, uv1, uv2):
    """Return the 3D point in camera 1's frame, metres, OpenCV axes.

    uv1 and uv2 are distorted pixel coordinates, straight from the detector.
    """
    def normalise(uv, k, d):
        pts = np.array([[[float(uv[0]), float(uv[1])]]], dtype=np.float64)
        return cv2.undistortPoints(pts, k, d).reshape(2, 1)

    n1 = normalise(uv1, rig.k1, rig.d1)
    n2 = normalise(uv2, rig.k2, rig.d2)

    p1, p2 = rig.projection_matrices()
    homogeneous = cv2.triangulatePoints(p1, p2, n1, n2)

    w = homogeneous[3, 0]
    if not np.isfinite(w) or abs(w) < 1e-12:
        raise TriangulationError(
            "degenerate triangulation for {} / {}: the two rays do not "
            "converge to a finite point under this rig's geometry".format(
                uv1, uv2))
    return (homogeneous[:3, 0] / w).astype(np.float64)


def reprojection_error(rig, xyz_m, uv1, uv2):
    """Pixel residuals in camera 1 and camera 2 for a solved point."""
    xyz = np.asarray(xyz_m, dtype=np.float64).reshape(1, 3)
    zero = np.zeros(3)

    proj1, _ = cv2.projectPoints(xyz, zero, zero, rig.k1, rig.d1)
    rvec, _ = cv2.Rodrigues(rig.r)
    proj2, _ = cv2.projectPoints(xyz, rvec, rig.t_m, rig.k2, rig.d2)

    e1 = float(np.linalg.norm(proj1.reshape(2) - np.asarray(uv1, dtype=np.float64)))
    e2 = float(np.linalg.norm(proj2.reshape(2) - np.asarray(uv2, dtype=np.float64)))
    return e1, e2


def depth_sensitivity_mm_per_px(rig, depth_m):
    """How much depth error one pixel of disparity error buys, in mm.

    Z^2 / (b * f), so it grows as the square of depth and no one number
    covers the 350-700 mm series. The figure at the working distance is
    3.53 mm/px, at Z = 0.500 m. Every distance the project owner supplied
    was measured in the vertical plane - the long cathetus from the lens
    plane to the ball, not the hypotenuse from camera to ball - so 500 mm
    is the horizontal leg, and because the unit stands level the optical
    axis is horizontal and that leg IS the ball's Z coordinate. It is the
    depth this formula wants, unmodified. This is what the analysis prints
    in its rig header.

    3.65 mm/px is NOT a second valid reading of the same geometry. It came
    from putting 508.7 mm - the straight-line RANGE to the ball's centre,
    sqrt(0.500^2 + 0.0937^2) - into a formula that takes a depth. It
    answers "what if the ball's depth were 508.7 mm", which it is not. The
    number survives in the spec and in this file's own unit test, where it
    is correct arithmetic on a stated input and is left alone; read it as
    an error carried forward, not as an alternative convention, and do not
    reconcile the two by adopting it.

    508.7 mm is not a useless quantity - it is the RIGHT one for
    kCameraNPositionsFromExpectedBallMeters, which is consumed as an
    expected line-of-sight distance to seed the ball-search radius prior:
    apparent radius scales with true 3D distance, not with depth. Do not
    "correct" that constant to 500 mm on the strength of this docstring.
    The two constants want two different distances to the same ball.

    Halve the result for the roughly half-pixel matching the detector
    achieves: that is what sets what counts as agreement with a tape
    measure.
    """
    depth = float(depth_m)
    if depth <= 0.0:
        # Z = 0 is the camera's own centre and Z < 0 is behind it. Squaring
        # would quietly turn a negative depth into a plausible-looking
        # positive tolerance, which is worse than no answer.
        raise ValueError(
            "depth must be positive, got {:.4f} m - a point at or behind the "
            "camera centre has no depth tolerance".format(depth))
    fx = float(rig.k1[0, 0])
    return 1000.0 * (depth ** 2) / (rig.baseline_m * fx)


class ScaleFit:
    """How the triangulated world's size compares with the tape's.

    scale is dimensionless: 1.006 means triangulation reads 0.6% long, which
    is what a baseline 0.6% too large produces. offset_m is where camera 1's
    z = 0 plane sits relative to the tape's zero, which is unknown and is
    not evidence about scale - it exists so that it cannot leak into one.

    scale_stderr is the point of the whole class. The question this run is
    asked to settle is 0.6% wide, and a scale printed without its own
    uncertainty cannot answer it either way.
    """

    def __init__(self, scale, scale_stderr, offset_m, residuals_m):
        self.scale = float(scale)
        self.scale_stderr = float(scale_stderr)
        self.offset_m = float(offset_m)
        self.residuals_m = np.asarray(residuals_m, dtype=np.float64)

    @property
    def n(self):
        return int(self.residuals_m.size)

    @property
    def rms_m(self):
        return float(np.sqrt(np.mean(self.residuals_m ** 2)))


def fit_scale_regression(depth_m, tape_m):
    """Fit depth = scale * tape + offset over every depth position.

    Both arguments are ABSOLUTE readings, not differences: the intercept is
    what makes that safe, and it carries the unknown lens-plane offset that
    differences were previously used to cancel.

    This replaces a least-squares fit through the origin on consecutive
    differences. For equally spaced positions that estimator telescopes to
    (Z_last - Z_first) / (tape_last - tape_first) exactly - the interior
    positions cancel out and contribute nothing - and it discarded repeated
    measurements at one position outright, since their tape gap is zero.
    Repeats are the cheapest precision available on the floor, so an
    estimator that throws them away is the wrong one.
    """
    depth = np.asarray(depth_m, dtype=np.float64).ravel()
    tape = np.asarray(tape_m, dtype=np.float64).ravel()
    if depth.shape != tape.shape:
        raise ValueError(
            "depth and tape must be the same length, got {} and {}".format(
                depth.shape, tape.shape))
    # Three, not two: two points fit any line exactly, and would report a
    # zero residual and a zero uncertainty that describe the arithmetic
    # rather than the measurement.
    if depth.size < 3:
        raise ValueError(
            "a scale needs at least 3 depth positions, got {}".format(
                depth.size))

    tape_centred = tape - tape.mean()
    sxx = float(np.dot(tape_centred, tape_centred))
    # Not "sxx <= 0". Three identical readings of 0.40 do not centre to
    # exactly zero - their mean lands one ulp away and leaves ~5e-17 of
    # spread per point - so a literal zero test lets a series that never
    # moved through and divides by it, producing a confident scale from
    # rounding noise. The comparison is relative because the guard is about
    # float residue, not about how far the operator should have moved: a
    # series that moved only a little is caught by its own huge stderr,
    # which is a better answer than a threshold guessed here.
    tape_spread = float(np.sqrt(sxx / tape.size))
    if tape_spread <= 1e-9 * max(1.0, float(np.max(np.abs(tape)))):
        raise ValueError(
            "the tape readings are all the same; a series that never moved "
            "determines no scale")

    scale = float(np.dot(tape_centred, depth - depth.mean()) / sxx)
    offset = float(depth.mean() - scale * tape.mean())
    residuals = depth - (scale * tape + offset)

    # Textbook OLS slope error. The n - 2 is why three positions is the
    # floor: two would divide by zero here, which is the same statement as
    # "two points determine a line and say nothing about how well".
    variance = float(np.dot(residuals, residuals)) / (depth.size - 2)
    return ScaleFit(scale=scale, scale_stderr=float(np.sqrt(variance / sxx)),
                    offset_m=offset, residuals_m=residuals)


def pooled_repeat_spread_m(values_m, keys):
    """Per-shot repeatability from positions measured more than once.

    Returns the pooled standard deviation of values_m within groups of
    equal keys, or None if no key occurs twice - None rather than zero,
    because a series with no repeats did not measure perfect repeatability,
    it measured nothing.

    This exists because fit_scale_regression's standard error is computed
    from scatter about the fitted line and therefore assumes scatter is the
    only error. A detection bias that grows with depth lands entirely in the
    slope and leaves the residuals small, so the stderr can be tiny while
    the scale is wrong by several times it. Repeats bound the random part
    and say nothing about the systematic part - and repeats taken without
    re-placing the ball do not even do that, since they share the same
    sub-pixel phase.
    """
    values = np.asarray(values_m, dtype=np.float64).ravel()
    key_array = np.asarray(keys, dtype=np.float64).ravel()
    if values.shape != key_array.shape:
        raise ValueError(
            "values and keys must be the same length, got {} and {}".format(
                values.shape, key_array.shape))

    sum_squares = 0.0
    degrees_of_freedom = 0
    for key in np.unique(key_array):
        group = values[key_array == key]
        if group.size < 2:
            # A singleton has no deviation from its own mean and no degree
            # of freedom. Counting it would pull the estimate toward zero.
            continue
        sum_squares += float(np.sum((group - group.mean()) ** 2))
        degrees_of_freedom += group.size - 1

    if degrees_of_freedom == 0:
        return None
    return float(np.sqrt(sum_squares / degrees_of_freedom))


class LineFit:
    """The direction the depth series ran, and how far it wandered off it.

    direction is a unit vector in camera 1's frame, always oriented away
    from the camera. obliquity_deg is its angle to the optical axis, split
    for reading into horizontal_deg (positive to the camera's right, the
    same sense as yaw_from_target_line) and vertical_deg (positive
    descending, since Y is down - so for a level floor line this reads the
    camera's own pitch).
    """

    def __init__(self, direction, rms_m):
        self.direction = np.asarray(direction, dtype=np.float64)
        self.rms_m = float(rms_m)

    @property
    def obliquity_deg(self):
        return float(np.degrees(np.arccos(np.clip(self.direction[2], -1.0, 1.0))))

    @property
    def horizontal_deg(self):
        return float(np.degrees(np.arctan2(self.direction[0], self.direction[2])))

    @property
    def vertical_deg(self):
        return float(np.degrees(np.arctan2(self.direction[1], self.direction[2])))


def fit_line(points_m):
    """Best-fit 3D line through the depth positions.

    The scale fit compares a difference of triangulated Z against a
    difference of tape readings. Those are the same quantity only insofar as
    the line the balls sat on ran along the optical axis; an angle psi
    between them multiplies the measured side by cos(psi). Two degrees is
    0.06% and five is 0.38%, against a 0.6% question, and nothing else in
    the run measures psi. These points do.
    """
    pts = np.asarray(points_m, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] != 3:
        raise ValueError("expected an (N, 3) array, got {}".format(pts.shape))
    if pts.shape[0] < 3:
        raise ValueError(
            "a line fit needs at least 3 points, got {}".format(pts.shape[0]))

    centred = pts - pts.mean(axis=0)
    _, singular, vt = np.linalg.svd(centred, full_matrices=False)

    direction = vt[0]
    # SVD hands back an arbitrary sign. Unfixed, half of all runs would
    # report 175 deg for a line laid 5 deg off, and the cos(psi) that reads
    # as a 0.4% correction would read as a factor of -1.
    if direction[2] < 0.0:
        direction = -direction

    # The two smaller singular values ARE the perpendicular spread: the
    # squared distances to the best-fit line sum to s[1]^2 + s[2]^2. Taking
    # it from them rather than as (total - along^2) matters - that
    # subtraction cancels two nearly equal large numbers and leaves 2e-9 m
    # of pure rounding on a line that is exactly straight but not
    # axis-aligned, which is a millimetre-scale readout claiming precision
    # it does not have.
    perpendicular_sq = float(singular[1] ** 2 + singular[2] ** 2)
    return LineFit(direction=direction,
                   rms_m=float(np.sqrt(perpendicular_sq / pts.shape[0])))
