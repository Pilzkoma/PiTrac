#!/usr/bin/env python3
"""Short-pulse test: how bright is a resting ball, and are its dimples visible?

Both cameras in trigger mode, 0.5 ms exposure, one SHOT per frame with the
flash 0.9 ms after the edge, pulse lengths from 0 to 300 us. Saves enlarged
ball crops per pulse and prints brightness and fine-texture figures.
"""
import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.expanduser("~/JetsonLM"))
from sp1_vision import strobe_capture as sc, ball_pair, stereo_geometry, strobe_event as se  # noqa
from sp1_vision.calibration_capture import set_manual_exposure  # noqa

OUT = sys.argv[1]
PULSES = [0, 10, 20, 30, 50, 100, 200, 300]
REPEATS = 4
os.makedirs(OUT, exist_ok=True)

sc.release_dashboard()
teensy = sc.Teensy(sc.TEENSY)
caps = sc.open_cameras()
frames = {}
try:
    sc.set_gamma(caps, sc.MEASURE_GAMMA)
    sc.settle_on_auto(caps)
    for _, dev in caps.values():
        set_manual_exposure(dev, 5)
    time.sleep(sc.SETTLE_S)
    teensy.cmd("TRIG_ARM")
    sc.set_trigger_mode(caps, True)
    time.sleep(0.3)
    # flush: a few no-flash shots, read whatever comes
    for _ in range(3):
        teensy.cmd("SHOT,3,900,0")
        for cap, _ in caps.values():
            cap.read()
        time.sleep(0.05)
    for p in PULSES:
        for k in range(REPEATS):
            teensy.cmd("SHOT,3,900,{}".format(p))
            for n, (cap, _) in caps.items():
                ok, buf = cap.read()
                frames.setdefault((n, p), []).append(sc.decode(buf.copy()) if ok else None)
            time.sleep(0.05)
finally:
    sc.set_trigger_mode(caps, False)
    try:
        teensy.cmd("TRIG_DISARM")
    except Exception:
        pass
    sc.set_gamma(caps, sc.DEFAULT_GAMMA)
    for cap, dev in caps.values():
        cap.release()
        set_manual_exposure(dev, None)
    teensy.close()

# locate the ball on the brightest pulse, both cameras
rig = stereo_geometry.load_rig()
f1 = frames[(1, 300)][0]
f2 = frames[(2, 300)][0]
ball, reason = ball_pair.find_ball_pair(rig, se.bgr(f1), se.bgr(f2))
if ball is None:
    print("ball not found:", reason)
    sys.exit(1)
print("ball at X %.0f Y %.0f Z %.0f mm, r %.1f / %.1f px" % (
    *(ball.xyz_m * 1000), ball.radius1_px, ball.radius2_px))
where = {1: (ball.uv1, ball.radius1_px), 2: (ball.uv2, ball.radius2_px)}

rows = []
sheet_rows = []
for n in (1, 2):
    (u, v), r = where[n]
    tiles = []
    for p in PULSES:
        imgs = [f for f in frames[(n, p)] if f is not None]
        img = np.mean(np.stack(imgs), axis=0).astype(np.float32)
        yy, xx = np.ogrid[:img.shape[0], :img.shape[1]]
        d = np.hypot(xx - u, yy - v)
        inner = img[d < 0.6 * r]
        ring = img[(d > 1.4 * r) & (d < 1.9 * r)]
        # fine texture: single frame minus its blurred self, inside 0.6 r,
        # minus the same figure on the no-flash frame (sensor noise)
        one = imgs[0].astype(np.float32)
        hp = one - cv2.GaussianBlur(one, (0, 0), 2.0)
        tex = float(hp[d < 0.6 * r].std())
        rows.append((n, p, float(inner.mean()), float(ring.mean()), float(img[d < r].max()), tex))
        x0, y0 = int(u - 1.3 * r), int(v - 1.3 * r)
        x1, y1 = int(u + 1.3 * r), int(v + 1.3 * r)
        crop = imgs[0][max(0, y0):y1, max(0, x0):x1]
        crop = cv2.resize(crop, (240, 240), interpolation=cv2.INTER_NEAREST)
        # stretch each crop so its texture is visible regardless of level
        lo, hi = np.percentile(crop, 1), np.percentile(crop, 99.5)
        crop = np.clip((crop.astype(np.float32) - lo) * 255.0 / max(hi - lo, 1), 0, 255).astype(np.uint8)
        cv2.putText(crop, "cam%d %dus" % (n, p), (4, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, 255, 1)
        tiles.append(crop)
    sheet_rows.append(np.hstack(tiles))
cv2.imwrite(os.path.join(OUT, "pulse_crops.png"), np.vstack(sheet_rows))

print("cam pulse_us  ball  surround  ball-surr  max  texture")
for n, p, ball_m, ring_m, mx, tex in rows:
    print(" %d   %4d   %5.1f   %5.1f    %+6.1f   %3.0f   %4.2f" % (n, p, ball_m, ring_m, ball_m - ring_m, mx, tex))
