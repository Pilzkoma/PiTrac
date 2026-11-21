"""Perspective unwrap of the camera-facing cap of a ball onto a fixed-scale
sphere image.

Output pixel at offset (x, y) from the middle: theta = hypot(x, y) / R_OUT_PX
(radians of arc from the view axis w), phi = atan2(y, x).  The surface normal
there is n = cos(theta) w + sin(theta) (cos(phi) e1 + sin(phi) e2), and the
source pixel is the projection of centre + r n.  One output pixel is the same
arc length everywhere, so a mark keeps its true size near the limb.
Pixels beyond MAX_DEG, or whose source falls outside the frame, are invalid
and zero (never border-replicated).
"""
import math

import cv2
import numpy as np

from sp1_vision.mark_map import BALL_RADIUS_MM

R_OUT_PX = 100
PX_PER_MM = R_OUT_PX / BALL_RADIUS_MM
MAX_DEG = 70.0
_MARGIN_PX = 2.0
# half-size covers MAX_DEG along the axes; the exact middle is pixel
# CENTRE_PX (integer) in both x and y, offsets (x, y) are measured from it
CENTRE_PX = int(math.ceil(R_OUT_PX * math.radians(MAX_DEG))) + 1
_SIZE = 2 * CENTRE_PX + 1


class Unwrapped(object):
    def __init__(self, image, valid, theta_deg, basis, centre_cam_m):
        self.image = image
        self.valid = valid
        self.theta_deg = theta_deg
        self.basis = basis
        self.centre_cam_m = centre_cam_m
        self.centre_px = CENTRE_PX


def _basis(centre):
    w = -np.asarray(centre, float)
    w = w / np.linalg.norm(w)
    e1 = np.array([1.0, 0.0, 0.0])
    e1 = e1 - (e1 @ w) * w
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(w, e1)
    return np.vstack([w, e1, e2])


def _normals(basis, x, y):
    theta = np.hypot(x, y) / R_OUT_PX
    phi = np.arctan2(y, x)
    w, e1, e2 = basis
    st = np.sin(theta)
    return (np.cos(theta)[..., None] * w
            + (st * np.cos(phi))[..., None] * e1
            + (st * np.sin(phi))[..., None] * e2), theta


def unwrap(gray, K, dist, centre_cam_m):
    centre = np.asarray(centre_cam_m, float).reshape(3)
    basis = _basis(centre)
    c = float(CENTRE_PX)
    ys, xs = np.mgrid[0:_SIZE, 0:_SIZE].astype(np.float64)
    n, theta = _normals(basis, xs - c, ys - c)
    pts = centre + (BALL_RADIUS_MM / 1000.0) * n.reshape(-1, 3)
    uv, _ = cv2.projectPoints(pts.reshape(-1, 1, 3), np.zeros(3), np.zeros(3),
                              np.asarray(K, float), np.asarray(dist, float))
    uv = uv.reshape(_SIZE, _SIZE, 2)
    mx = uv[..., 0].astype(np.float32)
    my = uv[..., 1].astype(np.float32)
    img = cv2.remap(gray, mx, my, cv2.INTER_CUBIC,
                    borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    h, w = gray.shape[:2]
    inside = ((uv[..., 0] >= _MARGIN_PX) & (uv[..., 0] <= w - 1 - _MARGIN_PX)
              & (uv[..., 1] >= _MARGIN_PX) & (uv[..., 1] <= h - 1 - _MARGIN_PX))
    theta_deg = np.degrees(theta)
    valid = (theta_deg <= MAX_DEG) & inside
    img = np.where(valid, img, 0).astype(np.uint8)
    return Unwrapped(img, valid, theta_deg, basis, centre)


def normal_at(u, x, y):
    n, _ = _normals(u.basis, np.array(float(x)), np.array(float(y)))
    return n / np.linalg.norm(n)


def tangent_at(u, x, y, dx, dy):
    """Unit tangent on the sphere for an unwrapped direction (dx, dy)."""
    eps = 1e-3
    d = np.array([dx, dy], float)
    d = d / np.linalg.norm(d)
    n0 = normal_at(u, x, y)
    n1 = normal_at(u, x + eps * d[0], y + eps * d[1])
    t = n1 - n0
    t = t - (t @ n0) * n0
    return t / np.linalg.norm(t)


def centre_from_circle(K, dist, uv, radius_px):
    """Monocular ball centre from its circle (range = fx r / radius_px)."""
    K = np.asarray(K, float)
    p = cv2.undistortPoints(np.array([[uv]], dtype=np.float64), K,
                            np.asarray(dist, float)).reshape(2)
    ray = np.array([p[0], p[1], 1.0])
    ray /= np.linalg.norm(ray)
    rng = K[0, 0] * (BALL_RADIUS_MM / 1000.0) / float(radius_px)
    return ray * rng
