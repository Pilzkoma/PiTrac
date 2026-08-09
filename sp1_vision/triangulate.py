#!/usr/bin/env python3
"""Two image points in, one 3D point out - plus the check that it is real.

The reprojection residual returned alongside is not decoration. It catches
swapped images, an inverted translation and a mis-detected ball, all of
which otherwise produce a confident number that is simply wrong.

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
            "degenerate triangulation for {} / {}: the rays are parallel, "
            "which usually means the same point was fed twice".format(uv1, uv2))
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

    Z^2 / (b * f). At the 50 cm working distance this is about 3.65 mm per
    pixel, so roughly 1.8 mm at half-pixel detection - the figure that sets
    what counts as agreement with a tape measure.
    """
    fx = float(rig.k1[0, 0])
    return 1000.0 * (float(depth_m) ** 2) / (rig.baseline_m * fx)
