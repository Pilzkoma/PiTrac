"""The ball centre from the cone of sight rays that touch the sphere.

A sphere seen through a pinhole is bounded by a circular cone of rays from the
camera centre: every ray that grazes the ball makes the same angle alpha with
the direction to the ball's centre, sin(alpha) = r_ball / range. Fitting that
cone to the outline gives the direction to the centre exactly. Fitting a circle
in the image does not, for two reasons that differ between the cameras
(docs/superpowers/specs/2026-11-21-ball-centre-cone-fit-design.md):

- off the optical axis the sphere's outline is an ellipse whose centre lies
  outward of the projected sphere centre (~0.4 px at 10 deg, ~0.9 px at 20 deg
  at 44 cm, f 916 px);
- the lens distortion bends the outline itself.

Outline points come from frame_analysis._outermost_edge_per_ray (subpixel:
the outermost strong radial gradient peak per ray, parabolically interpolated;
sampled by an exact bilinear interpolation, see bilinear),
are undistorted to unit rays, and the cone is fitted linearly: the axis a and
alpha satisfy d_i . a = cos(alpha) for every ray d_i, so w = a / cos(alpha)
solves D w = 1 in the least-squares sense - a closed form like the algebraic
circle fit, then trimmed on the angular residual like _trimmed_circle_fit.

refine_ball_cone has the (u, v, r) refiner shape ball_pair takes: (u, v) is
the distorted pixel of the cone axis (where the ball's centre projects), r is
fx tan(alpha). So the existing triangulation, which undistorts (u, v), uses
the true centre direction without any change.
"""

import cv2
import numpy as np

from sp1_vision import frame_analysis as fa
from sp1_vision.mark_map import BALL_RADIUS_MM

MIN_HALF_ANGLE_RAD = 1e-4   # below this the rays are parallel: no cone


def _cone_lstsq(rays):
    w, _, rank, _ = np.linalg.lstsq(rays, np.ones(len(rays)), rcond=None)
    if rank < 3:
        return None
    norm = float(np.linalg.norm(w))
    if not np.isfinite(norm) or norm <= 1.0:
        return None
    cos_alpha = 1.0 / norm
    alpha = float(np.arccos(cos_alpha))
    if alpha < MIN_HALF_ANGLE_RAD:
        return None
    return w / norm, alpha


def fit_cone(rays):
    """(axis, half_angle) of the circular cone through unit rays (N, 3), or None.

    Linear fit, then up to REFINE_ITERATIONS rounds dropping rays more than
    REFINE_TRIM_K median absolute deviations from the consensus angle.
    """
    rays = np.asarray(rays, dtype=np.float64)
    if rays.ndim != 2 or rays.shape[1] != 3 or len(rays) < fa.REFINE_TRIM_MIN_POINTS:
        return None
    fit = None
    for _ in range(fa.REFINE_ITERATIONS):
        fit = _cone_lstsq(rays)
        if fit is None:
            return None
        axis, alpha = fit
        residual = np.arccos(np.clip(rays @ axis, -1.0, 1.0)) - alpha
        med = float(np.median(residual))
        mad = float(np.median(np.abs(residual - med)))
        if mad < 1e-12:
            break
        keep = np.abs(residual - med) < fa.REFINE_TRIM_K * mad
        if int(keep.sum()) < fa.REFINE_TRIM_MIN_POINTS or int(keep.sum()) == len(rays):
            break
        rays = rays[keep]
    return fit


def centre_from_cone(axis, half_angle):
    """Ball centre in the camera frame (m): along the axis at r_ball / sin(alpha)."""
    axis = np.asarray(axis, dtype=np.float64)
    return axis / np.linalg.norm(axis) * (BALL_RADIUS_MM / 1000.0) / np.sin(half_angle)


def bilinear(img, map_x, map_y):
    """img sampled at (map_x, map_y) by exact bilinear interpolation, border replicated.

    Not cv2.remap: OpenCV 4.5.4 rounds remap's sample positions to 1/32 px,
    which moved the cone axis by up to 0.13 px on the Jetson.
    """
    h, w = img.shape[:2]
    x = np.clip(np.asarray(map_x, np.float64), 0.0, w - 1.0)
    y = np.clip(np.asarray(map_y, np.float64), 0.0, h - 1.0)
    x0 = np.minimum(np.floor(x).astype(np.int64), w - 2)
    y0 = np.minimum(np.floor(y).astype(np.int64), h - 2)
    fx, fy = x - x0, y - y0
    img = np.asarray(img, np.float64)
    top = img[y0, x0] * (1.0 - fx) + img[y0, x0 + 1] * fx
    bottom = img[y0 + 1, x0] * (1.0 - fx) + img[y0 + 1, x0 + 1] * fx
    return (top * (1.0 - fy) + bottom * fy).astype(np.float32)


def limb_rays(gray, K, dist, u, v, r):
    """(rays (N, 3), pixels (N, 2)) of the ball's outline round the seed, or None.

    Same ROI and blur as frame_analysis.refine_ball_by_contrast; at most one
    point per ray, none from samples off the image.
    """
    gray = fa._as_gray(gray)
    height, width = gray.shape[:2]
    half = int(round(r * ((1.0 + fa.REFINE_RADIAL_BAND) * (1.0 + fa.REFINE_MAX_RADIUS_CHANGE)
                          + fa.REFINE_MAX_DRIFT))) + 4
    x0, y0 = max(0, int(u) - half), max(0, int(v) - half)
    x1, y1 = min(width, int(u) + half + 1), min(height, int(v) + half + 1)
    roi = gray[y0:y1, x0:x1]
    if roi.size == 0 or min(roi.shape[:2]) < 8:
        return None
    blurred = cv2.GaussianBlur(roi, (5, 5), 0).astype(np.float32)
    outline = fa._outermost_edge_per_ray(blurred, float(u) - x0, float(v) - y0, float(r),
                                         sample=bilinear)
    if outline is None or outline[0].size < fa.REFINE_TRIM_MIN_POINTS:
        return None
    pix = np.stack([outline[0] + x0, outline[1] + y0], axis=1).astype(np.float64)
    und = cv2.undistortPoints(pix.reshape(-1, 1, 2), np.asarray(K, np.float64),
                              np.asarray(dist, np.float64)).reshape(-1, 2)
    rays = np.concatenate([und, np.ones((len(und), 1))], axis=1)
    rays /= np.linalg.norm(rays, axis=1, keepdims=True)
    return rays, pix


def _project(K, dist, direction):
    p, _ = cv2.projectPoints(np.asarray(direction, np.float64).reshape(1, 1, 3),
                             np.zeros(3), np.zeros(3), np.asarray(K, np.float64),
                             np.asarray(dist, np.float64))
    return p.reshape(2)


def refine_ball_cone(frame, u, v, r, K, dist):
    """(u, v, r) with (u, v) the projected sphere centre, r = fx tan(alpha); or None.

    Re-seeds at the projected axis REFINE_ITERATIONS times; the result must
    stay within frame_analysis's seed guards (a refinement is a correction,
    not a new detection).
    """
    cu, cv_, cr = float(u), float(v), float(r)
    fx = float(np.asarray(K)[0, 0])
    for _ in range(fa.REFINE_ITERATIONS):
        got = limb_rays(frame, K, dist, cu, cv_, cr)
        if got is None:
            return None
        fit = fit_cone(got[0])
        if fit is None:
            return None
        axis, alpha = fit
        if axis[2] <= 0:
            return None
        cu, cv_ = (float(x) for x in _project(K, dist, axis))
        cr = fx * float(np.tan(alpha))
    return fa._within_seed_guards(u, v, r, (cu, cv_, cr))


def cone_refiner(K, dist):
    """refine_ball_cone bound to one camera: the refine(frame, u, v, r) ball_pair takes."""
    def refine(frame, u, v, r):
        return refine_ball_cone(frame, u, v, r, K, dist)
    return refine
