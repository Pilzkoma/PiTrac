#!/usr/bin/env python3
"""Do PiTrac's dimple maps carry the ball's rotation on our images?

    python3 dimple_test.py DIR_A DIR_B OUTDIR

DIR_A / DIR_B: shot_frames.py output (frames.npz) of the same resting ball,
B turned by hand about the vertical axis. PiTrac's dimple front-end is
reproduced (ball_image_proc.cpp: IsolateBall with equalizeHist, Gabor 21 px,
sigma 1, lambda 6, gamma 0.2, psi 90 deg, 33 orientations, max, threshold
regulated to 39-45 % white, reflections >= 245 and the outer 8 % ignored).
Dark marks (the pen stroke, the print) are ignored as well, so they cannot
carry the match.

Tests: (1) repeatability - two frames of the unmoved ball; (2) rotation - A's
map turned on the sphere by phi about the vertical axis, compared with B's,
for phi in -40..40 deg. Dimples: the score peaks at the true turn (measured
independently from the dark mark's longitude). JPEG blocks, fixed to the
pixel grid: the peak sits at 0.
"""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.expanduser("~/JetsonLM"))
from sp1_vision import ball_pair, stereo_geometry, strobe_event as se  # noqa

IGNORE = 128


def locate(z, rig):
    top = max(int(k.split("_")[1]) for k in z.files if not k.endswith("dark"))
    f1, f2 = z["cam1_%d" % top][0], z["cam2_%d" % top][0]
    ball, _ = ball_pair.find_ball_pair(rig, se.bgr(f1), se.bgr(f2))
    if ball is None:
        ball, reason = ball_pair.find_ball_pair(rig, se.bgr(se.brightened(f1)), se.bgr(se.brightened(f2)))
        if ball is None:
            raise SystemExit("ball not found: " + reason)
    return {1: (ball.uv1, ball.radius1_px), 2: (ball.uv2, ball.radius2_px)}


def isolate(img, uv, r, size=int(os.environ.get("CROP", "128"))):
    """Square crop round the ball, resampled so the ball radius is size/2/1.05."""
    u, v = uv
    r1 = 1.05 * r
    M = np.float32([[size / (2 * r1), 0, -(u - r1) * size / (2 * r1)],
                    [0, size / (2 * r1), -(v - r1) * size / (2 * r1)]])
    crop = cv2.warpAffine(img, M, (size, size), flags=cv2.INTER_LINEAR)
    rr = size / 2 / 1.05
    return crop, rr


def gabor_map(crop, rr):
    size = crop.shape[0]
    c = size / 2.0
    yy, xx = np.mgrid[:size, :size]
    d = np.hypot(xx - c + 0.5, yy - c + 0.5)
    inside = d < 0.995 * rr
    eq = cv2.equalizeHist(crop)
    eq[~inside] = 0
    f = eq.astype(np.float32) / 255.0
    acc = np.zeros_like(f)
    for theta in np.arange(0, 360.0 + 1e-9, 11.25):
        k = cv2.getGaborKernel((21, 21), 1.0, np.deg2rad(theta), 6.0, 0.2, np.deg2rad(90.0), ktype=cv2.CV_32F)
        acc = np.maximum(acc, cv2.filter2D(f, cv2.CV_32F, k))
    accg = np.clip(acc * 255.0, 0, 255).astype(np.uint8)
    thr = 11.0
    for _ in range(60):
        m = accg > round(thr * 10)
        white = 100.0 * m.mean()
        if 39 <= white < 45:
            break
        thr += -0.5 if white < 39 else 0.5
    out = np.where(m, 255, 0).astype(np.uint8)
    # ignored: reflections, the outer 8 %, outside, and dark marks
    valid = d < 0.92 * rr
    valid &= crop < 245
    ball_level = np.median(crop[d < 0.6 * rr])
    dark = (crop < 0.6 * ball_level).astype(np.uint8)
    dark = cv2.dilate(dark, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    if os.environ.get("MASK_MARKS", "1") == "1":
        valid &= dark == 0
    return out, valid, dark.astype(bool) & (d < 0.95 * rr), thr, white


def sphere_coords(size, rr):
    c = size / 2.0
    yy, xx = np.mgrid[:size, :size].astype(np.float64)
    x = (xx - c + 0.5) / rr
    y = (yy - c + 0.5) / rr
    q = 1.0 - x * x - y * y
    z = np.sqrt(np.clip(q, 0, None))
    return x, y, z, q > 0


def rot_y(phi):
    a = np.deg2rad(phi)
    return np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])


def warp_to(map_a, valid_a, phi, rr):
    """A's map as it would look after the ball turned by phi about the vertical axis."""
    size = map_a.shape[0]
    x, y, z, ok = sphere_coords(size, rr)
    p = np.stack([x, y, z], -1) @ rot_y(phi)        # inverse rotation: target -> source
    c = size / 2.0
    su = (p[..., 0] * rr + c - 0.5).astype(np.float32)
    sv = (p[..., 1] * rr + c - 0.5).astype(np.float32)
    w = cv2.remap(map_a, su, sv, cv2.INTER_NEAREST, borderValue=0)
    wv = cv2.remap(valid_a.astype(np.uint8), su, sv, cv2.INTER_NEAREST, borderValue=0).astype(bool)
    wv &= ok & (p[..., 2] > 0.2)
    return w, wv


def agreement(m1, v1, m2, v2):
    both = v1 & v2
    if both.sum() < 200:
        return float("nan"), int(both.sum())
    return float(((m1 > 0) == (m2 > 0))[both].mean()), int(both.sum())


def mark_longitude(dark, rr):
    size = dark.shape[0]
    x, y, z, ok = sphere_coords(size, rr)
    sel = dark & ok
    if sel.sum() < 10:
        return float("nan")
    vx, vz = x[sel].mean(), z[sel].mean()
    return float(np.rad2deg(np.arctan2(vx, vz)))


def main():
    da, db, out = sys.argv[1:4]
    os.makedirs(out, exist_ok=True)
    rig = stereo_geometry.load_rig()
    za, zb = np.load(os.path.join(da, "frames.npz")), np.load(os.path.join(db, "frames.npz"))
    wa, wb = locate(za, rig), locate(zb, rig)
    sheet = []
    for n in (1, 2):
        for p in (50, 100):
            fa, fb = za["cam%d_%d" % (n, p)], zb["cam%d_%d" % (n, p)]
            ca, rr = isolate(fa[0], *wa[n])
            ca2, _ = isolate(fa[1], *wa[n])
            cb, _ = isolate(fb[0], *wb[n])
            ma, va, darka, ta, pa = gabor_map(ca, rr)
            ma2, va2, _, _, _ = gabor_map(ca2, rr)
            mb, vb, darkb, tb, pb = gabor_map(cb, rr)
            rep, nrep = agreement(ma, va, ma2, va2)
            true_phi = mark_longitude(darkb, rr) - mark_longitude(darka, rr)
            phis = np.arange(-40, 41, 2)
            scores = []
            for phi in phis:
                w, wv = warp_to(ma, va, phi, rr)
                s, _ = agreement(w, wv, mb, vb)
                scores.append(s)
            scores = np.array(scores)
            best = phis[int(np.nanargmax(scores))]
            s0 = scores[list(phis).index(0)]
            print("cam%d %3dus: white %.0f/%.0f%%  repeatability %.3f (n %d) | turn by mark %+.1f deg | "
                  "map score at 0: %.3f, best %.3f at %+d deg" % (
                      n, p, pa, pb, rep, nrep, true_phi, s0, np.nanmax(scores), best))
            print("    score(phi): " + " ".join("%+d:%.3f" % (ph, s) for ph, s in zip(phis[::4], scores[::4])))
            row = np.hstack([cv2.resize(x, (192, 192), interpolation=cv2.INTER_NEAREST)
                             for x in (ca, ma, cb, mb)])
            cv2.putText(row, "cam%d %dus" % (n, p), (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 255, 1)
            sheet.append(row)
    cv2.imwrite(os.path.join(out, "dimple_maps.png"), np.vstack(sheet))
    print("saved", os.path.join(out, "dimple_maps.png"))


if __name__ == "__main__":
    main()
