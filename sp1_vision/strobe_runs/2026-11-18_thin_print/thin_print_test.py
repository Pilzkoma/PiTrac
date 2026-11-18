#!/usr/bin/env python3
"""Does removing everything thinner than ~2 mm strip the factory print and
keep the marks?

    python thin_print_test.py OUTDIR IMAGE [IMAGE ...] [--stroke-mm 2.0]

Agreed with the owner 2026-11-18 (spec 2026-11-13-ball-marks-spin-design.md,
owner decision 4): before shape analysis, part 2 removes dark structure
thinner than ~2 mm on the ball (morphological opening), so a thin alignment
line or swoosh that touches or crosses a mark does not cost the mark. The
marks are 3.5 mm wide (dot 7 mm), a thin print stroke ~1-1.8 mm.

Per image:
  1. find the ball (bright, round blob);
  2. unwrap the visible cap onto the sphere (azimuthal equidistant about the
     ball centre as seen, orthographic - ~0.5 deg off at our geometry), at a
     fixed scale, so a 3.5 mm stroke is equally wide at the centre and near
     the limb (in the plain image it narrows by cos(angle): at 55 deg a
     3.5 mm bar looks 2 mm wide radially and the opening would kill it);
  3. dark = grey / local ball brightness < --ratio (brightness from a grey
     closing larger than any mark);
  4. opening with a disc of --stroke-mm; the same in the plain image plane
     for comparison;
  5. per dark component: area before (mm^2 on the ball), fraction surviving
     the opening (sphere and plane), angle from the view centre; and the
     components left after the opening (whether a mark touching print comes
     free).

Writes OUTDIR/sheet_NN.png (kept here as .jpg) (per image: crop | unwrapped | sphere opening |
plane opening; green kept, red removed) and OUTDIR/results.txt.
"""
import argparse
import math
import os

import cv2
import numpy as np

BALL_RADIUS_MM = 42.67 / 2
R_OUT = 100                  # unwrapped scale: ball radius in px
PX_PER_MM = R_OUT / BALL_RADIUS_MM          # 4.69 px per mm of arc
MAX_DEG = 70.0               # unwrap out to this angle from the view centre
EVAL_DEG = 60.0              # components centred beyond this are reported, flagged


def find_ball(gray, r_min=20, r_max=120):
    """(u, v, r) of the most ball-like bright blob, or None."""
    # Thresholds swept from Otsu upwards: in the triggered recordings (0.5 ms)
    # Otsu lands at ~44 grey levels and joins the ball to the lit floor.
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    otsu, _ = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    best, best_score = None, 0.0
    for t in range(int(otsu), 230, 10):
        _, bw = cv2.threshold(blur, t, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        for c in contours:
            (u, v), r = cv2.minEnclosingCircle(c)
            if not r_min <= r <= r_max:
                continue
            # Fill holes (marks) before judging roundness.
            fill = cv2.contourArea(cv2.convexHull(c)) / (math.pi * r * r)
            if fill > 0.8 and fill * r > best_score:
                best, best_score = (u, v, r), fill * r
    return best


def unwrap(gray, u, v, r):
    """The visible cap mapped azimuthal-equidistant about (u, v): output
    distance from the centre = arc length on the ball, R_OUT px per radius.
    Returns (image, valid mask, angle-from-centre map in deg)."""
    half = int(math.ceil(R_OUT * math.radians(MAX_DEG))) + 2
    ys, xs = np.mgrid[-half:half + 1, -half:half + 1].astype(np.float32)
    s = np.hypot(xs, ys)
    theta = s / R_OUT
    with np.errstate(invalid="ignore", divide="ignore"):
        k = np.where(s > 0, r * np.sin(theta) / s, r / R_OUT)
    mx = (u + xs * k).astype(np.float32)
    my = (v + ys * k).astype(np.float32)
    img = cv2.remap(gray, mx, my, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    valid = np.degrees(theta) <= MAX_DEG
    return img, valid, np.degrees(theta)


def plane_crop(gray, u, v, r):
    """The plain image round the ball at the same scale (ball radius R_OUT)."""
    half = int(math.ceil(R_OUT * math.radians(MAX_DEG))) + 2
    sc = R_OUT / r
    M = np.float32([[sc, 0, half - u * sc], [0, sc, half - v * sc]])
    size = 2 * half + 1
    img = cv2.warpAffine(gray, M, (size, size), flags=cv2.INTER_CUBIC,
                         borderMode=cv2.BORDER_REPLICATE)
    ys, xs = np.mgrid[-half:half + 1, -half:half + 1]
    rho = np.hypot(xs, ys) / R_OUT
    theta = np.degrees(np.arcsin(np.clip(rho, 0, 1)))
    valid = (rho < 1) & (theta <= MAX_DEG)
    return img, valid, theta


def disc(d_px):
    n = max(1, int(round(d_px)))
    if n % 2 == 0:
        n += 1
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (n, n))


def dark_mask(img, valid, ratio):
    """Pixels darker than ratio x the local ball brightness."""
    bright = cv2.morphologyEx(img, cv2.MORPH_CLOSE, disc(12 * PX_PER_MM))
    bright = cv2.GaussianBlur(bright, (0, 0), 3)
    rel = img.astype(np.float32) / np.maximum(bright.astype(np.float32), 1)
    return ((rel < ratio) & valid).astype(np.uint8)


def analyse(img, valid, theta, ratio, stroke_mm):
    dark = dark_mask(img, valid, ratio)
    opened = cv2.morphologyEx(dark, cv2.MORPH_OPEN, disc(stroke_mm * PX_PER_MM))
    n, lab, stats, cent = cv2.connectedComponentsWithStats(dark, connectivity=8)
    comps = []
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        if area < (0.5 * PX_PER_MM) ** 2 * 4:      # specks under ~1 mm^2
            continue
        m = lab == i
        cx, cy = cent[i]
        comps.append({"area_mm2": area / PX_PER_MM ** 2,
                      "kept": float(opened[m].sum()) / area,
                      "theta": float(theta[int(round(cy)), int(round(cx))]),
                      "xy": (int(cx), int(cy))})
    n2, _, st2, _ = cv2.connectedComponentsWithStats(opened, connectivity=8)
    after = sorted((st2[i, cv2.CC_STAT_AREA] / PX_PER_MM ** 2 for i in range(1, n2)), reverse=True)
    return dark, opened, comps, after


def overlay(img, valid, dark, opened):
    out = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    out[~valid] = (out[~valid] * 0.35).astype(np.uint8)
    out[(dark == 1) & (opened == 0)] = (40, 40, 230)
    out[opened == 1] = (60, 200, 60)
    return out


def label(img, text):
    cv2.putText(img, text, (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("images", nargs="+")
    ap.add_argument("--stroke-mm", type=float, default=2.0)
    ap.add_argument("--ratio", type=float, default=0.6)
    ap.add_argument("--rows-per-sheet", type=int, default=8)
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)

    lines = ["thin-print test: opening %.1f mm (%.1f px at %.2f px/mm), dark < %.2f x local brightness"
             % (a.stroke_mm, a.stroke_mm * PX_PER_MM, PX_PER_MM, a.ratio),
             "per component: area mm^2 | kept sphere | kept plane | deg from view centre"
             " (* = beyond %.0f deg, foreshortened)" % EVAL_DEG, ""]
    rows, sheet_no = [], 0

    def flush():
        nonlocal rows, sheet_no
        if rows:
            w = max(r.shape[1] for r in rows)
            rows = [cv2.copyMakeBorder(r, 0, 4, 0, w - r.shape[1], cv2.BORDER_CONSTANT) for r in rows]
            cv2.imwrite(os.path.join(a.outdir, "sheet_%02d.png" % sheet_no), np.vstack(rows))
            sheet_no += 1
            rows = []

    for path in a.images:
        gray = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        name = os.path.basename(path)
        ball = None if gray is None else find_ball(gray)
        if ball is None:
            lines.append("%s: no ball" % name)
            continue
        u, v, r = ball
        sph, sv, sth = unwrap(gray, u, v, r)
        pln, pv, pth = plane_crop(gray, u, v, r)
        d_s, o_s, comps_s, after_s = analyse(sph, sv, sth, a.ratio, a.stroke_mm)
        d_p, o_p, comps_p, _ = analyse(pln, pv, pth, a.ratio, a.stroke_mm)

        # Plane survival per sphere component: map the component centre back.
        def plane_kept(c):
            x, y = c["xy"]
            half = sph.shape[0] // 2
            s = math.hypot(x - half, y - half)
            k = R_OUT * math.sin(s / R_OUT) / s if s > 0 else 1.0
            px, py = half + (x - half) * k, half + (y - half) * k
            best = min(comps_p, key=lambda q: math.hypot(q["xy"][0] - px, q["xy"][1] - py), default=None)
            if best is None or math.hypot(best["xy"][0] - px, best["xy"][1] - py) > 3 * PX_PER_MM:
                return float("nan")
            return best["kept"]

        lines.append("%s  ball (%.0f, %.0f) r %.1f px" % (name, u, v, r))
        for c in sorted(comps_s, key=lambda c: -c["area_mm2"]):
            lines.append("   %6.1f  %4.2f  %4.2f  %3.0f%s" % (
                c["area_mm2"], c["kept"], plane_kept(c), c["theta"],
                "*" if c["theta"] > EVAL_DEG else ""))
        lines.append("   after opening: %d blobs, mm^2 %s" % (
            len(after_s), " ".join("%.0f" % x for x in after_s)))

        row = np.hstack([
            label(cv2.cvtColor(pln, cv2.COLOR_GRAY2BGR), name[:22]),
            label(cv2.cvtColor(sph, cv2.COLOR_GRAY2BGR), "unwrapped"),
            label(overlay(sph, sv, d_s, o_s), "sphere open"),
            label(overlay(pln, pv, d_p, o_p), "plane open")])
        rows.append(row)
        if len(rows) >= a.rows_per_sheet:
            flush()
    flush()
    with open(os.path.join(a.outdir, "results.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
