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


def fit_scale_factor(measured_m, tape_m):
    """Least-squares scale between triangulated and tape distances.

    Returns (scale, rms_residual_m). A scale of 1.006 means the triangulated
    world is 0.6% too large, which is what a baseline 0.6% too large would
    produce - the 78.28 against 78.749 question, answered by measurement.

    Both inputs must be DIFFERENCES between positions, not distances from
    the camera. Where exactly the lens plane sits is a guess, and a constant
    error in it would read as a scale error if absolute distances were used.

    The two differences must also be of the SAME quantity. The caller passes
    differences of triangulated DEPTH against differences of perpendicular
    tape readings; passing 3D point-to-point separations instead would
    compare a chord with a perpendicular distance, and every departure from
    a perfectly straight, perfectly perpendicular line would then inflate
    the measured side only - a one-directional bias on a 0.6% question.
    """
    measured = np.asarray(measured_m, dtype=np.float64).ravel()
    tape = np.asarray(tape_m, dtype=np.float64).ravel()
    if measured.shape != tape.shape:
        raise ValueError(
            "measured and tape must be the same length, got {} and {}".format(
                measured.shape, tape.shape))
    if measured.size == 0:
        raise ValueError("no displacements to fit a scale from")

    denominator = float(np.dot(tape, tape))
    if denominator <= 0.0:
        raise ValueError("tape displacements are all zero")

    scale = float(np.dot(measured, tape) / denominator)
    residuals = measured - scale * tape
    return scale, float(np.sqrt(np.mean(residuals ** 2)))


def straightness_rms_m(points_m):
    """RMS deviation of points from their own best-fit 3D line, metres.

    The depth series is supposed to be laid along one straight line running
    away from the unit. Nothing else checks that it was. A line laid with a
    wobble does not show up in the scale fit's residual in any way that
    distinguishes it from detection noise, so it is measured separately and
    reported next to the scale it affects.
    """
    pts = np.asarray(points_m, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] != 3:
        raise ValueError("expected an (N, 3) array, got {}".format(pts.shape))
    if pts.shape[0] < 3:
        # Two points always lie exactly on a line; fewer than that has no
        # line at all. Neither is evidence, so neither gets a number.
        raise ValueError(
            "straightness needs at least 3 points, got {}".format(pts.shape[0]))

    # The two smaller singular values ARE the perpendicular spread: the
    # squared distances to the best-fit line sum to s[1]^2 + s[2]^2. Taking
    # it from them rather than as (total - along^2) matters - that
    # subtraction cancels two nearly equal large numbers and leaves 2e-9 m
    # of pure rounding on a line that is exactly straight but not
    # axis-aligned, which is a millimetre-scale readout claiming precision
    # it does not have.
    centred = pts - pts.mean(axis=0)
    singular = np.linalg.svd(centred, compute_uv=False)
    perpendicular_sq = float(singular[1] ** 2 + singular[2] ** 2)
    return float(np.sqrt(perpendicular_sq / pts.shape[0]))


def depth_sensitivity_mm_per_px(rig, depth_m):
    """How much depth error one pixel of disparity error buys, in mm.

    Z^2 / (b * f). At the 50 cm working distance this is about 3.65 mm per
    pixel, so roughly 1.8 mm at half-pixel detection - the figure that sets
    what counts as agreement with a tape measure.
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
