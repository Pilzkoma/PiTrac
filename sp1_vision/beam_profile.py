#!/usr/bin/env python3
"""The IR beam's vertical profile from one flash on a flat wall, and the
array tilts that would light the flight best.

    python3 -m sp1_vision.beam_profile --out RUNDIR [--pulse-us 100]

Agreed with the owner 2026-11-21. Set the unit square to a flat wall (any
colour; dark green is fine if the flash is long enough) about 50 cm away,
the ball on its rest spot in front of it. One flash; the difference image
(flash minus ambient) is the beam as the cameras see it on the wall.

Per pixel the ray's angle above the camera axis is computed from the
calibration. A flat wall square to the axis receives cos^3 less light at an
off-axis angle a (cos^2 from the longer distance, cos from the oblique
incidence), so the image divided by cos^3(a) is what a ball at a constant
distance would get in that direction - beam and lens fall-off together,
which is what matters for seeing the ball. The vertical profile is the
median of a band 5 deg either side of the image's vertical centre line.

The two arrays sit round the two lenses, identical and parallel, and fire
together, so the profile is one array's. Tilting arrays as a whole by t1,
t2 degrees moves their profiles by t1, t2: the combined light at angle
theta is the mean of the profile at theta - t1 and theta - t2. The tool
searches 1-deg steps for the pair whose WORST point over the needed range
(the rest ball's angle up to the image top) is brightest. Outside the
measured range the profile is mirrored about its peak (an assumption, said
so in the output).
"""

import argparse
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sp1_vision import ball_pair, stereo_geometry  # noqa: E402

BAND_DEG = 5.0          # half-width of the vertical band the profile is taken from
BIN_DEG = 1.0
MIN_BIN_PX = 20
RISE_LINEAR_MAX = 140   # above this the tone curve compresses (strobe README)
RISE_WEAK = 15
TILT_RANGE = (-10, 25)  # degrees, 1-deg steps
DEFAULT_REST_DEG = -13.0


def ray_angles(k, dist, size):
    """Per pixel (vertical deg, horizontal deg, off-axis deg) of its ray.
    Vertical is positive above the axis (OpenCV y points down)."""
    w, h = size
    us, vs = np.meshgrid(np.arange(w, dtype=np.float64), np.arange(h, dtype=np.float64))
    pts = np.stack([us.ravel(), vs.ravel()], axis=1).reshape(-1, 1, 2)
    xy = cv2.undistortPoints(pts, np.asarray(k, dtype=np.float64),
                             np.asarray(dist, dtype=np.float64)).reshape(h, w, 2)
    x, y = xy[..., 0], xy[..., 1]
    vert = np.degrees(np.arctan2(-y, np.sqrt(1.0 + x * x)))
    horiz = np.degrees(np.arctan2(x, 1.0))
    off = np.degrees(np.arccos(1.0 / np.sqrt(1.0 + x * x + y * y)))
    return vert, horiz, off


def plane_factor(off_axis_deg):
    """Light a flat wall square to the axis receives at this off-axis angle,
    relative to the axis (distance and incidence): cos^3."""
    return np.cos(np.radians(off_axis_deg)) ** 3


def vertical_profile(img, vert, horiz, off, mask=None, band_deg=BAND_DEG, bin_deg=BIN_DEG,
                     min_deg=None):
    """(bin centres deg, profile normalised to its maximum) of the wall-
    corrected image along the vertical band |horizontal| < band_deg, only
    above min_deg if given (to keep to one surface, e.g. above a skirting
    board)."""
    corr = np.asarray(img, dtype=np.float64) / plane_factor(off)
    sel = np.abs(horiz) < band_deg
    if min_deg is not None:
        sel &= vert >= min_deg
    if mask is not None:
        sel &= ~mask
    v, c = vert[sel], corr[sel]
    edges = np.arange(np.floor(v.min()), np.ceil(v.max()) + bin_deg, bin_deg)
    centres, values = [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (v >= lo) & (v < hi)
        if m.sum() >= MIN_BIN_PX:
            centres.append(0.5 * (lo + hi))
            values.append(float(np.median(c[m])))
    values = np.array(values)
    return np.array(centres), values / max(float(values.max()), 1e-12)


def half_power_angles(angles, prof):
    """(below, above): where the profile falls to half its peak, interpolated;
    None on a side where it does not fall that far within the range."""
    i = int(np.argmax(prof))

    def walk(step):
        j = i
        while 0 <= j + step < len(prof):
            if prof[j + step] < 0.5:
                a0, a1, p0, p1 = angles[j], angles[j + step], prof[j], prof[j + step]
                return float(a0 + (0.5 - p0) * (a1 - a0) / (p1 - p0))
            j += step
        return None

    return walk(-1), walk(1)


def _profile_at(angles, prof, x):
    """The profile at angles x. Outside the measured range: the mirror image
    about the peak if that lies inside, else the darker end value (never the
    peak - mirroring and then clipping handed out the peak, 2026-11-21)."""
    peak = float(angles[int(np.argmax(prof))])
    x = np.asarray(x, dtype=np.float64)
    lo, hi = float(angles[0]), float(angles[-1])
    mirror = 2.0 * peak - x
    inside = (x >= lo) & (x <= hi)
    mirror_inside = (mirror >= lo) & (mirror <= hi)
    dark = float(min(prof[0], prof[-1]))
    return np.where(inside, np.interp(np.clip(x, lo, hi), angles, prof),
                    np.where(mirror_inside, np.interp(np.clip(mirror, lo, hi), angles, prof), dark))


def combined(angles, prof, tilts, theta):
    """Mean light at angles theta with the arrays tilted by `tilts` degrees."""
    return np.mean([_profile_at(angles, prof, np.asarray(theta) - t) for t in tilts], axis=0)


class Tilts:
    def __init__(self, tilts, min_rel):
        self.tilts = tilts
        self.min_rel = min_rel


def best_tilts(angles, prof, need, tilt_range=TILT_RANGE):
    """The pair of whole-array tilts whose darkest point over `need`
    (low deg, high deg) is brightest, relative to today's peak."""
    theta = np.arange(need[0], need[1] + 0.25, 0.5)
    steps = range(tilt_range[0], tilt_range[1] + 1)
    shifted = {t: _profile_at(angles, prof, theta - t) for t in steps}
    best = None
    for t1 in steps:
        for t2 in steps:
            if t2 > t1:
                continue
            worst = float(np.min(0.5 * (shifted[t1] + shifted[t2])))
            if best is None or worst > best.min_rel:
                best = Tilts((float(t1), float(t2)), worst)
    return best


# ------------------------------------------------------------------ device

def _chart(curves, need, size=(900, 420)):
    """A simple line chart: x = angle, y = relative light (0..1)."""
    w, h = size
    img = np.full((h, w, 3), 255, np.uint8)
    x0, x1, y0, y1 = 60, w - 20, 20, h - 40
    lo, hi = -30.0, 30.0

    def px(a, p):
        return (int(x0 + (a - lo) / (hi - lo) * (x1 - x0)), int(y1 - p * (y1 - y0)))

    cv2.rectangle(img, px(need[0], 1.0), px(need[1], 0.0), (235, 245, 235), -1)
    for a in range(-30, 31, 10):
        cv2.line(img, px(a, 0), px(a, 1), (220, 220, 220), 1)
        cv2.putText(img, "%+d" % a, (px(a, 0)[0] - 12, y1 + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
    for p in (0.5, 1.0):
        cv2.line(img, px(lo, p), px(hi, p), (200, 200, 200), 1)
        cv2.putText(img, "%.1f" % p, (10, px(lo, p)[1] + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
    for i, ((angles, prof), colour, label) in enumerate(curves):
        pts = np.array([px(a, p) for a, p in zip(angles, prof)], np.int32)
        cv2.polylines(img, [pts], False, colour, 2)
        cv2.putText(img, label, (x0 + 10, y0 + 18 + 18 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.5, colour, 1)
    cv2.putText(img, "deg above camera axis (green band: needed range)", (x0 + 200, h - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
    return img


def main(argv=None):
    from sp1_vision import flash_pair     # device-only imports
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--pulse-us", type=int, default=100)
    ap.add_argument("--min-deg", type=float, default=None,
                    help="use only the wall above this angle (one surface, e.g. above a "
                         "skirting board); below it the profile is mirrored")
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)

    rig = stereo_geometry.load_rig()
    fp = flash_pair.capture_flash_pairs(1, pulse_us=args.pulse_us)[0]
    lines = ["beam profile, flash %d us" % fp.pulse_us]
    for n in (1, 2):
        cv2.imwrite(os.path.join(args.out, "cam%d_flash.png" % n), fp.flash[n])
        cv2.imwrite(os.path.join(args.out, "cam%d_ambient.png" % n), fp.ambient[n])

    bgr = {n: cv2.cvtColor(fp.diff[n], cv2.COLOR_GRAY2BGR) for n in (1, 2)}
    ball, reason = ball_pair.find_ball_pair(rig, bgr[1], bgr[2], max_candidates=200)

    profiles, rest = {}, []
    for n, (k, d) in ((1, (rig.k1, rig.d1)), (2, (rig.k2, rig.d2))):
        raw = cv2.subtract(fp.flash[n], fp.ambient[n]).astype(np.float64)
        vert, horiz, off = ray_angles(k, d, rig.image_size)
        mask = np.zeros(raw.shape, bool)
        if ball is not None:
            (u, v), r = (ball.uv1, ball.radius1_px) if n == 1 else (ball.uv2, ball.radius2_px)
            yy, xx = np.ogrid[:raw.shape[0], :raw.shape[1]]
            mask = (xx - u) ** 2 + (yy - v) ** 2 < (1.6 * r) ** 2
            rest.append(float(vert[int(round(v)), int(round(u))]))
        region = ~mask & (np.abs(horiz) < BAND_DEG)
        if args.min_deg is not None:
            region &= vert >= args.min_deg
        wall = raw[region]
        top = float(np.percentile(wall, 99.5))
        lines.append("cam%d: wall rise up to %.0f grey levels%s" % (
            n, top, "  - TOO BRIGHT, tone curve compresses: shorter --pulse-us" if top > RISE_LINEAR_MAX
            else "  - WEAK, noisy: longer --pulse-us" if top < RISE_WEAK else ""))
        profiles[n] = vertical_profile(raw, vert, horiz, off, mask=mask, min_deg=args.min_deg)
        lo, hi = half_power_angles(*profiles[n])
        peak = profiles[n][0][int(np.argmax(profiles[n][1]))]
        lines.append("cam%d: peak at %+.1f deg, half light at %s below and %s above" % (
            n, peak, "%+.1f" % lo if lo is not None else "beyond the image",
            "%+.1f" % hi if hi is not None else "beyond the image"))

    top_deg = float(min(profiles[1][0][-1], profiles[2][0][-1]))
    rest_deg = float(np.mean(rest)) if rest else DEFAULT_REST_DEG
    lines.append("rest ball at %+.1f deg%s; image top at %+.1f deg" % (
        rest_deg, "" if rest else " (assumed - no ball found: %s)" % reason, top_deg))

    # One profile for both arrays: the two cameras' on a common grid.
    grid = np.arange(max(profiles[1][0][0], profiles[2][0][0]), top_deg + 0.01, BIN_DEG)
    if args.min_deg is not None:
        lines.append("profile measured from %+.1f deg up only; below that it is mirrored about "
                     "its peak (assumes a beam symmetric about its peak)" % grid[0])
    prof = 0.5 * (np.interp(grid, *profiles[1]) + np.interp(grid, *profiles[2]))
    prof /= prof.max()
    need = (rest_deg, top_deg)
    today = float(np.min(combined(grid, prof, (0.0, 0.0), np.arange(need[0], need[1] + 0.25, 0.5))))
    best = best_tilts(grid, prof, need)
    t_up, t_down = best.tilts
    rest_today = float(combined(grid, prof, (0.0, 0.0), np.array([rest_deg]))[0])
    rest_new = float(combined(grid, prof, best.tilts, np.array([rest_deg]))[0])
    lines += [
        "",
        "today: darkest point of the needed range %.2f of the peak" % today,
        "suggested: one array %+.0f deg, the other %+.0f deg -> darkest point %.2f" % (t_up, t_down, best.min_rel),
        "rest ball: %.2f of today's peak now, %.2f with the suggested tilts" % (rest_today, rest_new),
        "(outside the measured angles the profile is mirrored about its peak - an assumption)",
    ]
    chart = _chart([(profiles[1], (200, 80, 40), "cam1"), (profiles[2], (40, 120, 200), "cam2"),
                    ((grid, combined(grid, prof, best.tilts, grid)), (40, 160, 40),
                     "suggested tilts %+.0f / %+.0f" % (t_up, t_down))], need)
    cv2.imwrite(os.path.join(args.out, "profile.png"), chart)
    with open(os.path.join(args.out, "results.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
