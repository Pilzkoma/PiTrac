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

Outline points: per ray the outermost outward-falling edge in a narrow band
round the circle fit's outline (see _limb_points for why not the wide-band
rule of frame_analysis), parabolically interpolated, sampled by an exact
bilinear interpolation (see bilinear),
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


ANGULAR_RAYS = 72          # one outline point per 5 degrees
RAY_STEP_PX = 0.25
FIRST_BAND = 0.20          # first pass: +-20 % of the circle fit's radius
NEXT_BAND_PX = 3.0         # later passes: +-3 px round the outline the cone predicts
LIMB_STRENGTH = 0.25       # of the typical (median over rays) limb strength


def _limb_points(blurred, u, v, r, band):
    """Per ray from (u, v): the outermost bright-to-dark edge within r +- band
    that reaches LIMB_STRENGTH of the typical limb strength. (xs, ys) or None.
    r is a scalar or one expected radius per ray (ANGULAR_RAYS, from -pi).

    Why not frame_analysis._outermost_edge_per_ray's rule (the outermost edge
    reaching 3/4 of the strongest edge ON ITS RAY): on the real ball the lower
    limb is dim (IR beam from above) and a dark mark's edge out-crisps it, so
    that rule took mark edges there - 13-15 px inside, centre 3.8 px off on
    the 2026-11-21 static pair. Here the band is narrow (seeded by the circle
    fit, which is robust but biased by ~1 px), only outward-falling edges
    count (ball brighter than the dark strobe background), and the threshold
    is relative to the limb across all rays, not to the mark on the same ray.
    """
    offsets = np.arange(-band, band + RAY_STEP_PX, RAY_STEP_PX)
    angles = np.linspace(-np.pi, np.pi, ANGULAR_RAYS, endpoint=False)
    radii = np.maximum(1.0, np.broadcast_to(np.asarray(r, np.float64), angles.shape)[:, None]
                       + offsets[None, :])
    map_x = u + np.cos(angles)[:, None] * radii
    map_y = v + np.sin(angles)[:, None] * radii
    h, w = blurred.shape[:2]
    inside = ((map_x >= 0) & (map_y >= 0) & (map_x <= w - 1) & (map_y <= h - 1)).all(axis=1)
    profiles = bilinear(blurred, map_x, map_y).astype(np.float64)
    fall = -np.gradient(profiles, RAY_STEP_PX, axis=1)        # > 0: darker outward
    fall[~inside] = 0.0
    peak = np.zeros_like(fall, dtype=bool)
    peak[:, 1:-1] = (fall[:, 1:-1] >= fall[:, :-2]) & (fall[:, 1:-1] > fall[:, 2:])
    ray_max = np.where(peak, fall, 0.0).max(axis=1)
    typical = float(np.median(ray_max[inside])) if inside.any() else 0.0
    if typical <= 0.0:
        return None
    peak &= fall >= LIMB_STRENGTH * typical
    rows = np.nonzero(peak.any(axis=1))[0]
    if rows.size == 0:
        return None
    cols = peak.shape[1] - 1 - np.argmax(peak[rows, ::-1], axis=1)
    left, mid, right = fall[rows, cols - 1], fall[rows, cols], fall[rows, cols + 1]
    curvature = left - 2.0 * mid + right
    offset = np.where(curvature < 0.0, 0.5 * (left - right) / np.where(curvature < 0.0,
                                                                        curvature, -1.0), 0.0)
    at = radii[rows, 0] + (cols + offset) * RAY_STEP_PX
    return u + at * np.cos(angles[rows]), v + at * np.sin(angles[rows])


def limb_rays(gray, K, dist, u, v, r, band):
    """(rays (N, 3), pixels (N, 2)) of the ball's outline within r +- band, or None.
    r: scalar, or the expected radius per ray (see _limb_points).

    Rays whose band leaves the image are dropped (a ball cut by the frame
    simply has fewer).
    """
    gray = fa._as_gray(gray)
    height, width = gray.shape[:2]
    half = int(np.ceil(np.max(r) + band)) + 6
    x0, y0 = max(0, int(u) - half), max(0, int(v) - half)
    x1, y1 = min(width, int(u) + half + 1), min(height, int(v) + half + 1)
    roi = gray[y0:y1, x0:x1]
    if roi.size == 0 or min(roi.shape[:2]) < 8:
        return None
    blurred = cv2.GaussianBlur(roi, (5, 5), 0).astype(np.float32)
    # rays leaving the ROI because the ROI was clipped by the image edge are
    # dropped inside _limb_points (all samples must be on the ROI)
    outline = _limb_points(blurred, float(u) - x0, float(v) - y0, r, float(band))
    if outline is None or outline[0].size < fa.REFINE_TRIM_MIN_POINTS:
        return None
    pix = np.stack([outline[0] + x0, outline[1] + y0], axis=1).astype(np.float64)
    und = cv2.undistortPoints(pix.reshape(-1, 1, 2), np.asarray(K, np.float64),
                              np.asarray(dist, np.float64)).reshape(-1, 2)
    rays = np.concatenate([und, np.ones((len(und), 1))], axis=1)
    rays /= np.linalg.norm(rays, axis=1, keepdims=True)
    return rays, pix


def predicted_outline(K, dist, axis, alpha):
    """The outline a cone (axis, alpha) makes in the image, as the ray origin
    (u, v) - the mean of the projected outline - and the expected radius on
    each of the ANGULAR_RAYS rays from it. Off axis the outline is an ellipse
    (and bent by the lens), not a circle round the projected axis."""
    axis = np.asarray(axis, np.float64)
    a = np.cross(axis, [0.0, 1.0, 0.0])
    a /= np.linalg.norm(a)
    b = np.cross(axis, a)
    phi = np.linspace(0.0, 2.0 * np.pi, 4 * ANGULAR_RAYS, endpoint=False)
    rays = (np.cos(alpha) * axis[None, :]
            + np.sin(alpha) * (np.cos(phi)[:, None] * a + np.sin(phi)[:, None] * b))
    pts, _ = cv2.projectPoints(rays.reshape(-1, 1, 3), np.zeros(3), np.zeros(3),
                               np.asarray(K, np.float64), np.asarray(dist, np.float64))
    pts = pts.reshape(-1, 2)
    u, v = pts.mean(axis=0)
    ang = np.arctan2(pts[:, 1] - v, pts[:, 0] - u)
    rad = np.hypot(pts[:, 0] - u, pts[:, 1] - v)
    order = np.argsort(ang)
    grid = np.linspace(-np.pi, np.pi, ANGULAR_RAYS, endpoint=False)
    return float(u), float(v), np.interp(grid, ang[order], rad[order], period=2.0 * np.pi)


def _project(K, dist, direction):
    p, _ = cv2.projectPoints(np.asarray(direction, np.float64).reshape(1, 1, 3),
                             np.zeros(3), np.zeros(3), np.asarray(K, np.float64),
                             np.asarray(dist, np.float64))
    return p.reshape(2)


def refine_ball_cone(frame, u, v, r, K, dist):
    """(u, v, r) with (u, v) the projected sphere centre, r = fx tan(alpha); or None.

    Seeded by the circle fit (frame_analysis.refine_ball, else
    refine_ball_by_contrast, else the seed itself): outline within +-20 % of
    its radius, cone fit, then REFINE_ITERATIONS - 1 passes within +-3 px of
    the outline that cone predicts (predicted_outline). The result must stay within frame_analysis's seed
    guards (a refinement is a correction, not a new detection).
    """
    circle = fa.refine_ball(frame, u, v, r) or fa.refine_ball_by_contrast(frame, u, v, r)
    ou, ov, radii = (float(x) for x in (circle if circle is not None else (u, v, r)))
    band = FIRST_BAND * radii
    fit = None
    for _ in range(fa.REFINE_ITERATIONS):
        got = limb_rays(frame, K, dist, ou, ov, radii, band)
        if got is None:
            return None
        fit = fit_cone(got[0])
        if fit is None or fit[0][2] <= 0:
            return None
        ou, ov, radii = predicted_outline(K, dist, *fit)
        band = NEXT_BAND_PX
    axis, alpha = fit
    cu, cv_ = (float(x) for x in _project(K, dist, axis))
    cr = float(np.asarray(K)[0, 0]) * float(np.tan(alpha))
    return fa._within_seed_guards(u, v, r, (cu, cv_, cr))


def cone_refiner(K, dist):
    """refine_ball_cone bound to one camera: the refine(frame, u, v, r) ball_pair takes."""
    def refine(frame, u, v, r):
        return refine_ball_cone(frame, u, v, r, K, dist)
    return refine
