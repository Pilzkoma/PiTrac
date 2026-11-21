"""Test helper: draw a marked ball into a camera image with exact ground truth.

R maps map (stencil) frame -> camera frame: n_cam = R @ n_map.
"""

import cv2
import numpy as np

from sp1_vision.mark_map import BALL_RADIUS_MM

_SITE_LIMIT_DEG = 20.0


def _ink_mask(mmap, n_map):
    """True where the unit normals (m,3) in the map frame lie on ink."""
    shell = mmap.shell_radius_mm
    cosines = n_map @ mmap.normals.T
    site = np.argmax(cosines, axis=1)
    best = cosines[np.arange(len(n_map)), site]
    ink = np.zeros(len(n_map), dtype=bool)
    for k in np.nonzero(best > np.cos(np.radians(_SITE_LIMIT_DEG)))[0]:
        s = site[k]
        q = n_map[k] * (shell / best[k])
        e = float(q @ mmap.east[s])
        nn = float(q @ mmap.north[s])
        if abs(e) > 8.0 or abs(nn) > 8.0:
            continue
        poly = mmap.outlines_mm[s].astype(np.float32).reshape(-1, 1, 2)
        if cv2.pointPolygonTest(poly, (e, nn), False) >= 0:
            ink[k] = True
    return ink


def render_ball(mmap, K, dist, centre_cam_m, R, size=(1280, 800), ball_grey=200,
                ink_grey=40, background=15, gradient=None, glint=None, line=None,
                oversample=1):
    """The ball drawn into a size[0] x size[1] image, then a 3x3 blur.

    oversample = n: each pixel is the mean of n x n samples spread over it, so
    the silhouette edge is area-weighted (subpixel ground truth); 1 samples the
    pixel centre only, as every existing fixture was made.
    """
    K = np.asarray(K, dtype=float)
    centre = np.asarray(centre_cam_m, dtype=float)
    R = np.asarray(R, dtype=float)
    w, h = size
    img = np.full((h, w), float(background))
    r_m = BALL_RADIUS_MM / 1000.0

    u0 = K[0, 2] + K[0, 0] * centre[0] / centre[2]
    v0 = K[1, 2] + K[1, 1] * centre[1] / centre[2]
    rpx = K[0, 0] * r_m / centre[2]
    half = int(rpx * 1.5) + 4
    x0, x1 = max(int(u0) - half, 0), min(int(u0) + half + 1, w)
    y0, y1 = max(int(v0) - half, 0), min(int(v0) + half + 1, h)
    if x1 > x0 and y1 > y0:
        xs, ys = np.meshgrid(np.arange(x0, x1), np.arange(y0, y1))
        xs, ys = xs.ravel(), ys.ravel()
        n = int(oversample)
        offsets = [((i + 0.5) / n - 0.5, (j + 0.5) / n - 0.5)
                   for j in range(n) for i in range(n)] if n > 1 else [(0.0, 0.0)]
        acc = np.zeros(len(xs))
        for ox, oy in offsets:
            acc += _shade(mmap, K, dist, centre, R, xs + ox, ys + oy, u0, v0, rpx,
                          float(ball_grey), float(ink_grey), float(background),
                          gradient, glint, line)
        img[ys, xs] = acc / len(offsets)
    out = np.clip(img, 0, 255).astype(np.uint8)
    return cv2.GaussianBlur(out, (3, 3), 0)


def _shade(mmap, K, dist, centre, R, px, py, u0, v0, rpx, ball_grey, ink_grey,
           background, gradient, glint, line):
    """Grey at image points (px, py): the ball where a ray hits it, else background."""
    r_m = BALL_RADIUS_MM / 1000.0
    grey_all = np.full(len(px), background)
    pix = np.stack([px, py], axis=1).astype(np.float64)
    und = cv2.undistortPoints(pix.reshape(-1, 1, 2), K, np.asarray(dist, dtype=float))
    und = und.reshape(-1, 2)
    d = np.concatenate([und, np.ones((len(und), 1))], axis=1)
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    b = d @ centre
    disc = b * b - float(centre @ centre) + r_m * r_m
    hit = disc > 0
    t = b - np.sqrt(np.where(hit, disc, 0))
    hit &= t > 0
    idx = np.nonzero(hit)[0]
    p = d[idx] * t[idx, None]
    n_cam = (p - centre) / r_m
    n_cam /= np.linalg.norm(n_cam, axis=1, keepdims=True)
    n_map = n_cam @ R  # row-wise R.T @ n
    grey = np.where(_ink_mask(mmap, n_map), ink_grey, ball_grey)
    if gradient is not None:
        (dx, dy), factor = gradient
        nrm = float(np.hypot(dx, dy)) or 1.0
        tt = ((px[idx] - u0) * dx + (py[idx] - v0) * dy) / (nrm * 2 * rpx) + 0.5
        grey = grey * (1.0 + (factor - 1.0) * np.clip(tt, 0, 1))
    if line is not None:
        na, nb, width_mm, lgrey = line
        na = np.asarray(na, float) / np.linalg.norm(na)
        nb = np.asarray(nb, float) / np.linalg.norm(nb)
        wv = np.cross(na, nb)
        wv /= np.linalg.norm(wv)
        on = np.abs(n_cam @ wv) * BALL_RADIUS_MM < width_mm / 2.0
        on &= (np.cross(na, n_cam) @ wv >= 0) & (np.cross(n_cam, nb) @ wv >= 0)
        grey = np.where(on, float(lgrey), grey)
    if glint is not None:
        gn, grad_mm = glint
        gn = np.asarray(gn, float) / np.linalg.norm(gn)
        chord = np.linalg.norm(n_cam - gn, axis=1) * BALL_RADIUS_MM
        grey = np.where(chord < grad_mm, 255.0, grey)
    grey_all[idx] = grey
    return grey_all
