"""Dark mark blobs on the unwrapped ball, thin print removed, shapes classified.

Front end fixed by the 2026-11-18 thin-print test
(strobe_runs/2026-11-18_thin_print/): on the unwrapped sphere image
(ball_unwrap, PX_PER_MM px per mm of arc) a pixel is dark where it is below
DARK_RATIO x the local ball brightness; an opening with a disc of OPEN_MM
removes print thinner than that (a 1 mm alignment line) and keeps the
3.5 mm mark strokes; only blobs centred within EVAL_DEG of the view centre
are reported.

Classification against the map's ink areas (MarkMap.ink_area_mm2):
  dot   - area in band, round (elongation < ROUND), solid (>= SOLID)
  bar   - area in band, elongated (>= ELONGATED)
  cross - area in band, round, not solid (< SOLID)
a blob with a hole left after the glint fill (a ring) and anything else is
clutter (shape None) and is still returned, so the identifier can see a
wrong-shape blob where the pose predicts a mark.

Marks cut by the frame (REJECT_CUT_MARKS): a blob whose component touches
the frame cut - invalid pixels inside the cap (theta <= MAX_DEG - 1, so not
the cap's own rim), grown by one pixel - is clutter too (MarkBlob.cut). Cut
to 63 % of its ink a bar still falls in its area band and classified as a
bar, its centroid 5 deg off the site, and pulled the pose 2 deg off (final
review, random edge poses); refuse rather than guess. Turning it off gives
more orientations at the edge at that price.

Areas are true areas on the ball: the unwrap is azimuthal equidistant, which
stretches the tangential direction by theta / sin(theta), so each pixel
counts sin(theta) / theta. Directions are sphere tangents in the camera frame
(through ball_unwrap.tangent_at - the unwrapped image is a vertical mirror of
the camera view, so 2D angles are never camera angles).
"""
import math

import cv2
import numpy as np

from sp1_vision import ball_unwrap
from sp1_vision.ball_unwrap import PX_PER_MM, R_OUT_PX

DARK_RATIO = 0.6
BRIGHTNESS_DISC_MM = 8.0
GLINT_HOLE_MM2 = 6.0
OPEN_MM = 2.0
EVAL_DEG = 60.0
MIN_AREA_MM2 = 8.0
AREA_BAND = (0.6, 1.5)
ELONGATED = 1.8
ROUND = 1.5
SOLID = 0.85
REJECT_CUT_MARKS = True

_BLUR_SIGMA_PX = 3.0
_PX2_PER_MM2 = PX_PER_MM * PX_PER_MM


class MarkBlob(object):
    def __init__(self, normal, shape, direction, area_mm2, theta_deg, elongation,
                 solidity, xy, cut=False):
        self.normal = normal            # (3,) camera frame, at the centroid
        self.shape = shape              # "dot" | "bar" | "cross" | None
        self.direction = direction      # (3,) sphere tangent, or None
        self.area_mm2 = area_mm2        # true area on the ball
        self.theta_deg = theta_deg      # centroid angle from the view centre
        self.elongation = elongation    # major / minor axis (second moments)
        self.solidity = solidity        # area / convex-hull area
        self.xy = xy                    # centroid in the unwrapped image (col, row)
        self.cut = cut                  # component touches the frame cut

    def __repr__(self):
        return "MarkBlob(%s, %.1f mm2, %.0f deg, elong %.2f, solid %.2f%s)" % (
            self.shape, self.area_mm2, self.theta_deg, self.elongation, self.solidity,
            ", cut" if self.cut else "")


def _disc(diameter_px):
    n = max(1, int(round(diameter_px)))
    if n % 2 == 0:
        n += 1
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (n, n))


def _fill_invalid_locally(img, valid, reach_px):
    """Copy of img with invalid pixels filled from their valid neighbours.

    Iterated 3x3 grey dilation (the brightest known neighbour) out to
    reach_px; pixels further from the valid region cannot influence the
    closing of a valid pixel and keep the brightest valid grey. A local fill,
    not one global value: under a brightness gradient a global maximum would
    lift the estimate by a dim frame cut and turn the ball there into ink.
    """
    out = img.copy()
    known = valid.copy()
    ker = np.ones((3, 3), np.uint8)
    for _ in range(int(reach_px)):
        if known.all():
            break
        grown = cv2.dilate(np.where(known, out, 0).astype(np.uint8), ker)
        new = cv2.dilate(known.astype(np.uint8), ker).astype(bool) & ~known
        if not new.any():
            break
        out[new] = grown[new]
        known |= new
    out[~known] = img[valid].max()
    return out


def _local_brightness(u):
    """Grey closing with a disc larger than any mark, then a Gaussian.

    Invalid pixels must not act as dark structure (a mark touching the edge of
    the valid cap would merge with them and keep its ink in the closing), so
    they are filled from their nearest valid neighbours before the closing, and
    the Gaussian is normalised over valid pixels only (zeros outside would dim
    the edge).
    """
    valid = u.valid
    img = u.image
    if not valid.any():
        return np.zeros(img.shape, np.float32)
    disc = _disc(BRIGHTNESS_DISC_MM * PX_PER_MM)
    # the closing of a pixel reads up to two disc radii away
    filled = _fill_invalid_locally(img, valid, disc.shape[0] + 2)
    closed = cv2.morphologyEx(filled, cv2.MORPH_CLOSE, disc)
    w = valid.astype(np.float32)
    num = cv2.GaussianBlur(closed.astype(np.float32) * w, (0, 0), _BLUR_SIGMA_PX)
    den = cv2.GaussianBlur(w, (0, 0), _BLUR_SIGMA_PX)
    return num / np.maximum(den, 1e-6)


def _fill_small_holes(mask, max_px):
    """Fill non-dark regions enclosed by dark that are smaller than max_px."""
    inv = (mask == 0).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(inv, connectivity=4)
    h, w = mask.shape
    out = mask.copy()
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if area >= max_px:
            continue
        if x == 0 or y == 0 or x + bw == w or y + bh == h:
            continue
        out[lab == i] = 1
    return out


def dark_mask(u):
    """uint8 0/1: below DARK_RATIO x local ball brightness, on valid pixels,
    with glint holes (< GLINT_HOLE_MM2) inside dark components filled."""
    bright = _local_brightness(u)
    rel = u.image.astype(np.float32) / np.maximum(bright, 1.0)
    dark = ((rel < DARK_RATIO) & u.valid).astype(np.uint8)
    dark = _fill_small_holes(dark, GLINT_HOLE_MM2 * _PX2_PER_MM2)
    dark[~u.valid] = 0
    return dark


def _cross_angle(xs, ys, cx, cy):
    """Angle (rad, mod 90 deg) of the two perpendicular lines through the
    centroid that run along the most blob pixels, in 1 deg steps."""
    x0, y0 = int(xs.min()), int(ys.min())
    on = np.zeros((int(ys.max()) - y0 + 1, int(xs.max()) - x0 + 1), bool)
    on[ys - y0, xs - x0] = True
    h, w = on.shape
    reach = float(np.max(np.hypot(xs - cx, ys - cy))) + 1.0
    s = np.arange(-reach, reach + 0.25, 0.5)
    a = np.radians(np.arange(90.0))
    counts = np.zeros(90)
    for ux, uy in ((np.cos(a), np.sin(a)), (-np.sin(a), np.cos(a))):
        px = np.rint(cx + np.outer(ux, s)).astype(int) - x0
        py = np.rint(cy + np.outer(uy, s)).astype(int) - y0
        ok = (px >= 0) & (px < w) & (py >= 0) & (py < h)
        hit = np.zeros(px.shape, bool)
        hit[ok] = on[py[ok], px[ok]]
        counts += hit.sum(axis=1)
    # The count is flat while both lines stay inside the arms (3.5 x 10 mm
    # arms: +-19 deg), so its plain argmax lands anywhere on that plateau
    # (10-13 deg off in the synthetic test). Take the plateau's centre: the
    # circular mean (period 90) of the angles, weighted by the count above
    # the half-way level between the profile's minimum and maximum.
    level = 0.5 * (counts.max() + counts.min())
    excess = np.clip(counts - level, 0.0, None)
    if not excess.any():
        return float(a[int(np.argmax(counts))])
    phase = np.angle(np.sum(excess * np.exp(4j * a)))
    return float(phase / 4.0)


def _classify(area_mm2, elong, solid, ink):
    def in_band(shape):
        return AREA_BAND[0] * ink[shape] <= area_mm2 <= AREA_BAND[1] * ink[shape]
    if in_band("dot") and elong < ROUND and solid >= SOLID:
        return "dot"
    if in_band("bar") and elong >= ELONGATED:
        return "bar"
    if in_band("cross") and elong < ROUND and solid < SOLID:
        return "cross"
    return None


def _frame_cut(u):
    """bool: pixels next to (or on) the frame cut - invalid pixels inside the
    cap's rim, grown by a 3x3 dilation - or None when the frame cuts nothing."""
    cut = ~u.valid & (u.theta_deg <= ball_unwrap.MAX_DEG - 1.0)
    if not cut.any():
        return None
    return cv2.dilate(cut.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)


def detect_marks(u, mmap):
    """All dark blobs >= MIN_AREA_MM2 centred within EVAL_DEG, classified."""
    dark = dark_mask(u)
    opened = cv2.morphologyEx(dark, cv2.MORPH_OPEN, _disc(OPEN_MM * PX_PER_MM))
    n, lab, stats, cents = cv2.connectedComponentsWithStats(opened, connectivity=8)
    near_cut = _frame_cut(u)
    cut_labels = set() if near_cut is None else set(np.unique(lab[near_cut]).tolist())
    c0 = float(u.centre_px)
    blobs = []
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] < MIN_AREA_MM2 * _PX2_PER_MM2 * 0.5:
            continue                       # cannot reach MIN_AREA_MM2 even weighted up
        ys, xs = np.nonzero(lab == i)
        cx, cy = float(xs.mean()), float(ys.mean())
        theta_deg = math.degrees(math.hypot(cx - c0, cy - c0) / R_OUT_PX)
        if theta_deg > EVAL_DEG:
            continue
        th = np.hypot(xs - c0, ys - c0) / R_OUT_PX
        wgt = np.where(th > 1e-9, np.sin(th) / np.maximum(th, 1e-9), 1.0)
        area_mm2 = float(wgt.sum()) / _PX2_PER_MM2
        if area_mm2 < MIN_AREA_MM2:
            continue
        dx, dy = xs - cx, ys - cy
        cov = np.array([[np.mean(dx * dx), np.mean(dx * dy)],
                        [np.mean(dx * dy), np.mean(dy * dy)]])
        evals, evecs = np.linalg.eigh(cov)
        elong = math.sqrt(max(evals[1], 1e-12) / max(evals[0], 1e-12))
        comp = (lab[stats[i, 1]:stats[i, 1] + stats[i, 3],
                    stats[i, 0]:stats[i, 0] + stats[i, 2]] == i).astype(np.uint8)
        comp = cv2.copyMakeBorder(comp, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
        contours, hier = cv2.findContours(comp, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
        outer = [cnt for cnt, h in zip(contours, hier[0]) if h[3] < 0]
        has_hole = len(outer) < len(contours)
        contour = max(outer, key=cv2.contourArea)
        hull_area = cv2.contourArea(cv2.convexHull(contour))
        solid = float(cv2.contourArea(contour)) / hull_area if hull_area > 0 else 0.0
        # glint holes (< GLINT_HOLE_MM2) are already filled; a hole left now
        # (a ring of print) is no mark, though its outline looks like a dot
        cut = i in cut_labels
        shape = (None if has_hole or (cut and REJECT_CUT_MARKS)
                 else _classify(area_mm2, elong, solid, mmap.ink_area_mm2))
        x, y = cx - c0, cy - c0
        normal = ball_unwrap.normal_at(u, x, y)
        direction = None
        if shape == "bar":
            v = evecs[:, 1]
            direction = ball_unwrap.tangent_at(u, x, y, v[0], v[1])
        elif shape == "cross":
            a = _cross_angle(xs, ys, cx, cy)
            direction = ball_unwrap.tangent_at(u, x, y, math.cos(a), math.sin(a))
        blobs.append(MarkBlob(normal, shape, direction, area_mm2, theta_deg, elong,
                              solid, (cx, cy), cut))
    return blobs
