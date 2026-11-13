#!/usr/bin/env python3
"""Find a shot in a continuous-strobe recording and measure the ball's motion.

    python3 -m sp1_vision.strobe_event /tmp/shot1

Works on what sp1_vision.strobe_shot saved (RECDIR/raw/cam1|cam2/*.jpg).
The chain is the one the device itself will need, done offline:

1. Rest ball: the stereo ball search (ball_pair.find_ball_pair, size and
   disparity checked) on the plain strobe frames, every REST_STEP_S.
2. Impact: the first moment after which the rest position stays dark - the
   bright disc at the ball's image position is gone in camera 1 for good.
3. Reference: the still scene just BEFORE impact (two medians, fewer and one
   more flash, as in strobe_shot.Reference). Taking it close in time keeps
   the player and the club in it; a whole-recording median did not, and the
   circle search then found "balls" in every frame (2026-11-11).
4. Flight: frames after impact, POSITIVE difference only (where it got
   brighter) - the hole the ball leaves at its rest position drops out -
   searched with the same stereo ball search, camera 1 frame paired with the
   camera 2 frame nearest in time.
5. Motion: a robust straight-line fit of position over time (fit_motion)
   keeps only the positions that agree on one constant velocity - the
   stereo checks alone still let through circles on feet and club - and
   gives speed and direction. Frame times are arrival times; the two
   cameras' frames are up to half a frame apart, which is fine for a putt
   and not for a drive - fast shots need the flash pattern to tell the ball
   images apart.

Slow (minutes for a 25 s recording): every frame after a rest detection is
decoded at full size in Python. The device will watch a small window round
the ball as frames arrive instead.
"""

import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sp1_vision import ball_pair, stereo_geometry  # noqa: E402
from sp1_vision import strobe_capture as sc  # noqa: E402
from sp1_vision import strobe_shot as ss  # noqa: E402

REST_STEP_S = 0.25          # rest-ball search interval
GONE_FRACTION = 0.5         # presence below this share of the rest value = gone
GONE_HOLD_S = 0.15          # ...for at least this long
REF_FROM_S, REF_TO_S = 0.25, 0.08   # reference window before impact
FLIGHT_S = 0.6              # searched after impact
PAIR_MAX_DT_S = 0.006       # cam1/cam2 frames paired at most this far apart

# Triggered recordings (0.5 ms exposure, 2026-11-12) are dark: frame median
# ~17 grey levels against ~100 at 8 ms. The rest ball is there (78 on a 24
# surround) but its edge under the near-axial flash is soft - Sobel median 19
# against Hough's Canny threshold of 100 - and the circle search found it in
# 0 of 17 moments; brightened x2.5 first, in 16 of 17.
DARK_FRAME_MEDIAN = 40
DARK_FRAME_GAIN = 2.5

# The positive (ball-only) image is scaled so its 99.9th percentile reaches
# 220. Without a floor on that percentile a ball-free triggered frame, whose
# brightest residue is ~9 grey levels of noise, was scaled x25 into 1768
# Hough circles; frames with a ball have it near 100 and are unaffected.
POSITIVE_MIN_TOP = 100.0
MAX_CANDIDATES = 200        # either camera: a noise image, skipped unsearched


def bgr(img):
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)


def brightened(img):
    """A dark (triggered) frame scaled by DARK_FRAME_GAIN; others as they are."""
    if float(np.median(img)) >= DARK_FRAME_MEDIAN:
        return img
    return np.clip(img.astype(np.float32) * DARK_FRAME_GAIN, 0, 255).astype(np.uint8)


def nearest(frames, t):
    i = int(np.argmin([abs(ft - t) for ft, _ in frames]))
    return frames[i]


def presence(buf, u, v, r):
    """Brightness of the ball disc minus its surround: high while it lies there.

    Decoded at half size and evaluated on a crop round the ball only - this
    runs on every frame after a rest detection.
    """
    img = cv2.imdecode(np.asarray(buf).reshape(-1), cv2.IMREAD_REDUCED_GRAYSCALE_2)
    u, v, r = u / 2.0, v / 2.0, r / 2.0
    x0, x1 = max(0, int(u - 2 * r)), min(img.shape[1], int(u + 2 * r) + 1)
    y0, y1 = max(0, int(v - 2 * r)), min(img.shape[0], int(v + 2 * r) + 1)
    crop = img[y0:y1, x0:x1]
    yy, xx = np.ogrid[y0:y1, x0:x1]
    d2 = (xx - u) ** 2 + (yy - v) ** 2
    inner = crop[d2 < (0.6 * r) ** 2]
    ring = crop[(d2 > (1.4 * r) ** 2) & (d2 < (1.9 * r) ** 2)]
    if inner.size == 0 or ring.size == 0:
        return 0.0
    return float(inner.mean()) - float(ring.mean())


def find_rest_balls(rig, got):
    """[(t, BallPair)] for the rest ball found on plain strobe frames."""
    found = []
    t_end = got[1][-1][0]
    t = ss.REFERENCE_SKIP_S
    while t < t_end:
        t1, b1 = nearest(got[1], t)
        t2, b2 = nearest(got[2], t1)
        if abs(t2 - t1) <= PAIR_MAX_DT_S:
            f1, f2 = brightened(sc.decode(b1)), brightened(sc.decode(b2))
            ball, _ = ball_pair.find_ball_pair(rig, bgr(f1), bgr(f2))
            if ball is not None:
                found.append((t1, ball))
        t += REST_STEP_S
    return found


def next_same_spot(rest, i):
    """Time of the next rest detection at the same image position, or None."""
    (u, v), r = rest[i][1].uv1, rest[i][1].radius1_px
    for t, b in rest[i + 1:]:
        if (b.uv1[0] - u) ** 2 + (b.uv1[1] - v) ** 2 <= r * r:
            return t
    return None


def find_impacts(got, rest):
    """[(t_impact, BallPair at rest)]: for each rest position, when it emptied.

    Each search stops shortly after the next rest detection at the same spot:
    the ball was still there then, so that detection's own search covers
    everything later. Without the stop every sample of a ball that never
    leaves rescans to the end of the recording (quadratic - over half an
    hour for 45 s of chips, 2026-11-12).
    """
    impacts = []
    used_until = -1.0
    for i, (t_rest, ball) in enumerate(rest):
        if t_rest < used_until:
            continue
        u, v = ball.uv1
        r = ball.radius1_px
        t_next = next_same_spot(rest, i)
        t_stop = float("inf") if t_next is None else t_next + GONE_HOLD_S + REST_STEP_S
        frames = [(t, b) for t, b in got[1] if t_rest <= t <= t_stop]
        base = presence(frames[0][1], u, v, r)
        if base <= 10:
            continue
        gone_since = None
        for t, b in frames:
            p = presence(b, u, v, r)
            if p < GONE_FRACTION * base:
                gone_since = t if gone_since is None else gone_since
                if t - gone_since >= GONE_HOLD_S:
                    impacts.append((gone_since, ball))
                    used_until = gone_since + FLIGHT_S
                    break
            else:
                gone_since = None
    return impacts


class PositiveReference(ss.Reference):
    def __init__(self, frames):
        imgs = [sc.decode(b) for _, b in frames]
        means = np.array([im.mean() for im in imgs])
        cut = np.median(means)
        low = [im for im, m in zip(imgs, means) if m <= cut]
        high = [im for im, m in zip(imgs, means) if m > cut] or low
        self.a = np.median(np.stack(low), axis=0).astype(np.float32)
        self.b = np.median(np.stack(high), axis=0).astype(np.float32)
        aa, ab, bb = (self.a * self.a).sum(), (self.a * self.b).sum(), (self.b * self.b).sum()
        self.inv = np.linalg.pinv(np.array([[aa, ab], [ab, bb]], dtype=np.float64))

    def positive(self, buf):
        img = sc.decode(buf)
        f = img.astype(np.float32)
        ca, cb = self.inv @ np.array([(f * self.a).sum(), (f * self.b).sum()])
        d = np.clip(f - ca * self.a - cb * self.b, 0, None)
        top = max(float(np.percentile(d, 99.9)), POSITIVE_MIN_TOP)
        return img, np.clip(d * (220.0 / top), 0, 255).astype(np.uint8)


def flight(rig, got, t_imp):
    refs = {n: PositiveReference([(t, b) for t, b in got[n]
                                  if t_imp - REF_FROM_S <= t < t_imp - REF_TO_S])
            for n in (1, 2)}
    track, shown = [], []
    for t1, b1 in [(t, b) for t, b in got[1] if t_imp - 0.02 <= t < t_imp + FLIGHT_S]:
        t2, b2 = nearest(got[2], t1)
        if abs(t2 - t1) > PAIR_MAX_DT_S:
            continue
        img1, d1 = refs[1].positive(b1)
        img2, d2 = refs[2].positive(b2)
        ball, reason = ball_pair.find_ball_pair(rig, bgr(d1), bgr(d2),
                                                max_candidates=MAX_CANDIDATES)
        if ball is not None:
            track.append((0.5 * (t1 + t2), ball))
            shown.append((t1, img1, d1, len(track),
                          [(ball.uv1[0], ball.uv1[1], ball.radius1_px)]))
    return track, shown


# A shot counts when at least MIN_INLIERS positions fit one constant velocity
# to within INLIER_TOL_M and that velocity exceeds MIN_SPEED_MPS. On the first
# recording (2026-11-11) every impact candidate collected pairs that passed
# the stereo checks on feet and putter; the real putt had 12 of 24 points on
# one line, every false one at most 3 (and one still object 6 at 0.09 m/s).
INLIER_TOL_M = 0.015
MIN_INLIERS = 6
MIN_SPEED_MPS = 0.3


def fit_motion(track, iters=3000, seed=0):
    """Robust constant-velocity fit: (inlier mask, velocity m/s, rms m).

    Pairs of points propose a velocity; the proposal most points agree with
    wins, and the final line is a least-squares fit through those points.
    """
    t = np.array([tt for tt, _ in track])
    xyz = np.array([b.xyz_m for _, b in track])
    n = len(t)
    rng = np.random.default_rng(seed)
    best = np.zeros(n, dtype=bool)
    for _ in range(iters):
        i, j = rng.choice(n, 2, replace=False)
        if abs(t[i] - t[j]) < 0.005:
            continue
        v = (xyz[j] - xyz[i]) / (t[j] - t[i])
        res = np.linalg.norm(xyz - (xyz[i] + np.outer(t - t[i], v)), axis=1)
        inl = res < INLIER_TOL_M
        if inl.sum() > best.sum():
            best = inl
    if best.sum() < 2:
        return best, np.zeros(3), float("nan")
    A = np.vstack([t[best], np.ones(best.sum())]).T
    coef = np.linalg.lstsq(A, xyz[best], rcond=None)[0]
    resid = xyz[best] - A @ coef
    return best, coef[0], float(np.sqrt((resid ** 2).sum(axis=1).mean()))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__)
        return 2
    rec = argv[0]
    rig = stereo_geometry.load_rig()
    stereo_geometry.validate_rig(rig)
    got = ss.load_raw(rec)

    rest = find_rest_balls(rig, got)
    print("rest ball found at %d of the sampled moments" % len(rest))
    for t, b in rest[:3] + ([("...", None)] if len(rest) > 3 else []):
        if b is not None:
            print("  t %.2f s: X %+.0f Y %+.0f Z %.0f mm" % (
                t, b.xyz_m[0] * 1000, b.xyz_m[1] * 1000, b.depth_mm))
    impacts = find_impacts(got, rest)
    print("%d impact(s): %s" % (len(impacts), " ".join("%.3f s" % t for t, _ in impacts)))

    for k, (t_imp, ball0) in enumerate(impacts, 1):
        track, shown = flight(rig, got, t_imp)
        print("\nshot %d at %.3f s, ball at rest X %+.0f Z %.0f mm: ball found in %d frame pairs"
              % (k, t_imp, ball0.xyz_m[0] * 1000, ball0.depth_mm, len(track)))
        for t, b in track:
            print("  %+.3f s  X %+7.1f  Y %+6.1f  Z %6.1f mm  reproj %.2f  size %+.0f%%" % (
                t - t_imp, b.xyz_m[0] * 1000, b.xyz_m[1] * 1000, b.depth_mm,
                b.reprojection_px, b.radius_error * 100))
        result = {"t_impact": t_imp, "pairs": [
            {"t": t - t_imp, "xyz_m": b.xyz_m.tolist(), "reproj_px": b.reprojection_px,
             "size_err": b.radius_error} for t, b in track]}
        if len(track) >= 3:
            inl, vel, rms = fit_motion(track)
            speed = float(np.linalg.norm(vel))
            accepted = int(inl.sum()) >= MIN_INLIERS and speed > MIN_SPEED_MPS
            # Horizontal direction in camera 1's frame: X across the image,
            # Z away from the unit. 0 deg = straight across.
            across = np.degrees(np.arctan2(vel[2], abs(vel[0])))
            print("  %s: %d of %d positions on one line, speed %.2f m/s (%.1f km/h), "
                  "%s across the view, %.1f deg %s, rms %.1f mm" % (
                      "SHOT" if accepted else "rejected", int(inl.sum()), len(track),
                      speed, speed * 3.6,
                      "right-to-left" if vel[0] < 0 else "left-to-right",
                      abs(across), "away from the unit" if across > 0 else "towards it",
                      rms * 1000))
            result.update({"accepted": accepted, "inliers": inl.tolist(),
                           "velocity_mps": vel.tolist(), "speed_mps": speed,
                           "rms_m": rms})
            shown = [s for s, keep in zip(shown, inl) if keep] or shown
        with open(os.path.join(rec, "shot%d.json" % k), "w") as fh:
            json.dump(result, fh, indent=1)
        ss.contact_sheet(shown[:24], os.path.join(rec, "shot%d_cam1.png" % k), cols=4, width=400)
    return 0


if __name__ == "__main__":
    sys.exit(main())
