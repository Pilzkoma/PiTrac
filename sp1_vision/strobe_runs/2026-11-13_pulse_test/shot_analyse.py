#!/usr/bin/env python3
"""Analyse shot_frames.py output: ball brightness per pulse, enlarged crops.

    python3 shot_analyse.py OUTDIR [crop_px]
"""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.expanduser("~/JetsonLM"))
from sp1_vision import ball_pair, stereo_geometry, strobe_event as se  # noqa

OUT = sys.argv[1]
CROP = int(sys.argv[2]) if len(sys.argv) > 2 else 320
z = np.load(os.path.join(OUT, "frames.npz"))
pulses = sorted({int(k.split("_")[1]) for k in z.files if not k.endswith("dark")})
top = max(pulses)

rig = stereo_geometry.load_rig()
f1, f2 = z["cam1_%d" % top][0], z["cam2_%d" % top][0]
ball, reason = ball_pair.find_ball_pair(rig, se.bgr(f1), se.bgr(f2))
if ball is None:
    ball, reason = ball_pair.find_ball_pair(rig, se.bgr(se.brightened(f1)), se.bgr(se.brightened(f2)))
if ball is None:
    print("ball not found:", reason)
    sys.exit(1)
print("ball at X %.0f Y %.0f Z %.0f mm, r %.1f / %.1f px" % (
    *(ball.xyz_m * 1000), ball.radius1_px, ball.radius2_px))
where = {1: (ball.uv1, ball.radius1_px), 2: (ball.uv2, ball.radius2_px)}

rows = []
print("cam pulse_us  ball  surround  ball-surr   max")
for n in (1, 2):
    (u, v), r = where[n]
    tiles = []
    for p in pulses:
        stack = z["cam%d_%d" % (n, p)].astype(np.float32)
        img = stack.mean(axis=0)
        yy, xx = np.ogrid[:img.shape[0], :img.shape[1]]
        d = np.hypot(xx - u, yy - v)
        inner, ring = img[d < 0.6 * r], img[(d > 1.4 * r) & (d < 1.9 * r)]
        print(" %d   %4d   %5.1f   %5.1f    %+6.1f   %3.0f" % (
            n, p, inner.mean(), ring.mean(), inner.mean() - ring.mean(), stack[:, d < r].max()))
        one = z["cam%d_%d" % (n, p)][0]
        x0, y0, x1, y1 = int(u - 1.15 * r), int(v - 1.15 * r), int(u + 1.15 * r), int(v + 1.15 * r)
        crop = cv2.resize(one[max(0, y0):y1, max(0, x0):x1], (CROP, CROP), interpolation=cv2.INTER_CUBIC)
        cv2.putText(crop, "cam%d %dus" % (n, p), (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 255, 2)
        tiles.append(crop)
    rows.append(np.hstack(tiles))
cv2.imwrite(os.path.join(OUT, "crops.png"), np.vstack(rows))
print("saved", os.path.join(OUT, "crops.png"))
