#!/usr/bin/env python3
"""A marked ball turned by known angles: acceptance 2 of the ball-marks design.

    python -m sp1_vision.turn_series SERIESDIR [--step N] [--skip-s S] [--csv PATH]

SERIESDIR holds one strobe_shot --trigger recording per turntable position,
named pos_DDD by the angle turned so far, CLOCKWISE SEEN FROM ABOVE
(pos_000, pos_015, ... pos_345, and pos_360 back at the start):

    python3 -m sp1_vision.strobe_shot --trigger --seconds 2 --out SERIESDIR/pos_015

Per position the ball is at rest: it is found by stereo in the first
SEED_FRAMES frame pairs (orientation_check.find_ball, cone centre) and its
median position serves every frame of that position. Each frame is oriented
in both cameras (orientation_check._orient_ball), and each camera's poses -
in camera 1's frame - are averaged robustly (mean_rotation): the medoid,
the poses within MEAN_TOL_DEG of it, their chordal mean.

The series per camera (analyse_series): every position's pose against the
first one, R_k R_0^T, as a signed turn about the disc axis - down, the
floor normal from the measured attitude (orientation_check.UP_CAM) - and
against the turn the folder name says; consecutive steps; the axis of each
turn against down, and the common axis (its tilt is the disc's lean, not an
error of the method); closure, pos_360 against pos_000. Clockwise from above
is a rotation about down: a positive turn here. cam1 and cam2 are reported
separately and compared position by position (spec: within 3 deg).

The mark table (marks.csv, mark_rows): every blob of every frame - also of
frames that refused - named by the site the position's pose puts within
MATCH_TOL_DEG of it, with the site's true shape, the shape read, and the
blob's angle from the view centre, area, solidity and elongation. This is
the measurement of what the classification does towards the limb; the
summary prints it by shape and angle band.
"""
import argparse
import csv
import math
import os
import re
import sys
from collections import Counter

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sp1_vision import ball_orientation, ball_pair, mark_map, orientation_check  # noqa: E402
from sp1_vision import stereo_geometry  # noqa: E402
from sp1_vision.ball_orientation import Orientation, rotation_angle_deg  # noqa: E402

MEAN_TOL_DEG = 3.0        # poses this close to the medoid are averaged
MIN_POSES = 2             # fewer agreeing poses: no mean for that camera
SEED_FRAMES = 10          # frame pairs searched for the resting ball's position
AXIS_MIN_DEG = 10.0       # turns smaller than this have no meaningful axis
SIGN_MARGIN_DEG = 5.0     # no sign within this of 0 and 180 deg
THETA_BANDS = (0.0, 20.0, 40.0, 50.0, 55.0, 60.0)
_POS = re.compile(r"pos_(\d+)$")
_FRAME = re.compile(r"t(\d+\.\d+)\.jpg$")


def _wrap(deg):
    """deg into (-180, 180]."""
    w = math.fmod(deg + 180.0, 360.0)
    if w <= 0.0:
        w += 360.0
    return w - 180.0


def _rotvec(R):
    rv, _ = cv2.Rodrigues(np.asarray(R, np.float64))
    return rv.reshape(3)


def _nearest_rotation(M):
    u, _, vt = np.linalg.svd(M)
    d = 1.0 if np.linalg.det(u @ vt) >= 0 else -1.0
    return u @ np.diag([1.0, 1.0, d]) @ vt


def mean_rotation(Rs, tol_deg=MEAN_TOL_DEG, min_n=MIN_POSES):
    """(R, n used, median angle of the used poses to R) or None.

    The medoid (smallest median angle to the others) picks the cluster, so a
    pose off by a symmetry of the site set cannot drag the mean."""
    Rs = [np.asarray(R, float) for R in Rs]
    if len(Rs) < min_n:
        return None
    ang = np.array([[rotation_angle_deg(a, b) for b in Rs] for a in Rs])
    med = int(np.argmin(np.median(ang, axis=1)))
    use = [R for R, a in zip(Rs, ang[med]) if a <= tol_deg]
    if len(use) < min_n:
        return None
    R = _nearest_rotation(np.sum(use, axis=0))
    spread = float(np.median([rotation_angle_deg(R, u) for u in use]))
    return R, len(use), spread


def _signed_turn(R, down):
    """(signed angle deg about down, unit axis signed to match, angle deg)."""
    rv = _rotvec(R)
    theta = float(np.linalg.norm(rv))
    if theta < 1e-12:
        return 0.0, None, 0.0
    n = rv / theta
    s = 1.0 if float(n @ down) >= 0.0 else -1.0
    return s * math.degrees(theta), s * n, math.degrees(theta)


def _sign_ok(measured, expected):
    if abs(expected) < SIGN_MARGIN_DEG or abs(expected) > 180.0 - SIGN_MARGIN_DEG:
        return None
    return (measured > 0.0) == (expected > 0.0)


def analyse_series(entries, up_cam):
    """entries: [(deg turned clockwise from above, R map->cam1)], sorted.

    Returns {"rows": per position {deg, expected_deg, measured_deg, err_deg,
    axis_err_deg, sign_ok}, "steps": consecutive {deg_from, deg_to, step_deg,
    expected_deg, sign_ok}, "axis_tilt_deg": the common axis against down,
    "closure_deg": angle between the poses at the first deg and deg + 360
    (None without such a pair)}."""
    down = -np.asarray(up_cam, float)
    down = down / np.linalg.norm(down)
    deg0, R0 = entries[0]
    rows, axes = [], []
    for deg, R in entries:
        phi, axis, theta = _signed_turn(R @ R0.T, down)
        expected = _wrap(deg - deg0)
        axis_err = None
        if axis is not None and theta >= AXIS_MIN_DEG:
            axis_err = math.degrees(math.acos(min(1.0, max(-1.0, float(axis @ down)))))
            axes.append(axis * math.sin(math.radians(min(theta, 90.0))))
        rows.append({"deg": deg, "expected_deg": expected, "measured_deg": phi,
                     "err_deg": _wrap(phi - expected), "axis_err_deg": axis_err,
                     "sign_ok": _sign_ok(phi, expected)})
    steps = []
    for (da, Ra), (db, Rb) in zip(entries[:-1], entries[1:]):
        phi, _, _ = _signed_turn(Rb @ Ra.T, down)
        expected = _wrap(db - da)
        steps.append({"deg_from": da, "deg_to": db, "step_deg": phi,
                      "expected_deg": expected, "sign_ok": _sign_ok(phi, expected)})
    tilt = None
    if axes:
        a = np.sum(axes, axis=0)
        a = a / np.linalg.norm(a)
        tilt = math.degrees(math.acos(min(1.0, max(-1.0, float(a @ down)))))
    closure = None
    by_deg = dict(entries)
    for deg, R in entries:
        if deg + 360 in by_deg:
            closure = rotation_angle_deg(by_deg[deg + 360], R)
            break
    return {"rows": rows, "steps": steps, "axis_tilt_deg": tilt, "closure_deg": closure}


def mark_rows(blobs, R_cam, mmap, tol_deg=ball_orientation.MATCH_TOL_DEG):
    """The blobs that lie within tol_deg of a site under the pose R_cam
    (map -> this camera), named by that site."""
    pred = mmap.normals @ np.asarray(R_cam, float).T
    cos_tol = math.cos(math.radians(tol_deg))
    rows = []
    for b in blobs:
        c = pred @ np.asarray(b.normal, float)
        j = int(np.argmax(c))
        if c[j] < cos_tol:
            continue
        true = mmap.shapes[j]
        rows.append({"site": j, "true_shape": true, "read_shape": b.shape,
                     "theta_deg": float(b.theta_deg), "area_mm2": float(b.area_mm2),
                     "area_ratio": float(b.area_mm2) / mmap.ink_area_mm2[true],
                     "solidity": float(b.solidity), "elongation": float(b.elongation),
                     "off_deg": math.degrees(math.acos(min(1.0, float(c[j])))),
                     "cut": bool(b.cut)})
    return rows


def positions(series_dir):
    """[(deg, folder)] of the pos_DDD folders, by angle."""
    out = []
    for name in os.listdir(series_dir):
        m = _POS.match(name)
        if m and os.path.isdir(os.path.join(series_dir, name)):
            out.append((int(m.group(1)), os.path.join(series_dir, name)))
    return sorted(out)


def _frame_pairs(pos_dir, skip_s, step):
    """[(t1, path1, path2)]: cam1 frames from skip_s on, each with the cam2
    frame of nearest arrival within PAIR_MAX_DT_S, every step-th pair."""
    def listed(cam):
        d = os.path.join(pos_dir, "raw", cam)
        if not os.path.isdir(d):
            return []
        out = []
        for name in sorted(os.listdir(d)):
            m = _FRAME.match(name)
            if m and float(m.group(1)) >= skip_s:
                out.append((float(m.group(1)), os.path.join(d, name)))
        return out
    l1, l2 = listed("cam1"), listed("cam2")
    pairs = []
    for t1, p1 in l1:
        if not l2:
            break
        t2, p2 = min(l2, key=lambda x: abs(x[0] - t1))
        if abs(t2 - t1) <= orientation_check.PAIR_MAX_DT_S:
            pairs.append((t1, p1, p2))
    return pairs[::max(1, int(step))]


def _read(path):
    return cv2.imread(path, cv2.IMREAD_GRAYSCALE)


def _rest_ball(rig, pairs):
    """BallPair at the median of the stereo positions found in the first
    SEED_FRAMES pairs, or (None, reason)."""
    xyz, reasons = [], Counter()
    for _, p1, p2 in pairs[:SEED_FRAMES]:
        ball, reason = orientation_check.find_ball(rig, _read(p1), _read(p2))
        if ball is None:
            reasons[orientation_check._reason_class(reason)] += 1
        else:
            xyz.append(ball.xyz_m)
    if not xyz:
        return None, "no ball in %d frame pairs (%s)" % (
            min(len(pairs), SEED_FRAMES), ", ".join("%s x%d" % kv for kv in reasons.items()))
    c = np.median(np.array(xyz), axis=0)
    return ball_pair.BallPair(c, (0, 0), (0, 0), 0.0, 0.0, 0.0, 0.0), None


def _position(rig, mmap, deg, pos_dir, step, skip_s):
    pairs = _frame_pairs(pos_dir, skip_s, step)
    rec = {"deg": deg, "frames": len(pairs), "ball": None, "reason": None,
           "cam1": None, "cam2": None, "n": {"cam1": 0, "cam2": 0},
           "refusals": Counter(), "agree_deg": None, "blobs": []}
    if not pairs:
        rec["reason"] = "no frame pairs"
        return rec
    ball, reason = _rest_ball(rig, pairs)
    rec["ball"], rec["reason"] = ball, reason
    if ball is None:
        return rec
    poses = {"cam1": [], "cam2": []}
    for t, p1, p2 in pairs:
        out = {"ball": ball, "reason": None, "agree_deg": None, "detail": {},
               "cross_check": {"cam1": None, "cam2": None},
               "ink_audit": {"cam1": 0, "cam2": 0}}
        orientation_check._orient_ball(rig, _read(p1), _read(p2), mmap, ball, out)
        for cam in ("cam1", "cam2"):
            o = out[cam]
            if isinstance(o, Orientation):
                poses[cam].append(orientation_check.cam1_rotation(rig, cam, o.R))
            else:
                rec["refusals"][(cam, orientation_check._reason_class(o.reason))] += 1
            if cam in out["detail"]:
                rec["blobs"].append((t, cam, isinstance(o, Orientation),
                                     out["detail"][cam][1]))
    for cam in ("cam1", "cam2"):
        rec["n"][cam] = len(poses[cam])
        rec[cam] = mean_rotation(poses[cam])
    if rec["cam1"] is not None and rec["cam2"] is not None:
        rec["agree_deg"] = rotation_angle_deg(rec["cam1"][0], rec["cam2"][0])
    return rec


def _marks(rig, mmap, rec):
    """mark_rows for every frame of a position under that position's pose:
    each camera's own mean, else the other camera's carried over."""
    rows = []
    for t, cam, oriented, blobs in rec["blobs"]:
        other = "cam2" if cam == "cam1" else "cam1"
        src = cam if rec[cam] is not None else (other if rec[other] is not None else None)
        if src is None:
            continue
        R_cam = orientation_check._in_camera(rig, cam, rec[src][0])
        for r in mark_rows(blobs, R_cam, mmap):
            r.update({"pos_deg": rec["deg"], "t": t, "cam": cam, "pose_from": src,
                      "frame_oriented": oriented})
            rows.append(r)
    return rows


def run(series_dir, rig, mmap, step=5, skip_s=0.5, up_cam=orientation_check.UP_CAM):
    """{"positions": per position record, "series": {cam: analyse_series or
    None}, "marks": mark table rows}."""
    recs, marks = [], []
    for deg, pos_dir in positions(series_dir):
        rec = _position(rig, mmap, deg, pos_dir, step, skip_s)
        marks.extend(_marks(rig, mmap, rec))
        recs.append(rec)
    series = {}
    for cam in ("cam1", "cam2"):
        entries = [(r["deg"], r[cam][0]) for r in recs if r[cam] is not None]
        series[cam] = analyse_series(entries, up_cam) if len(entries) >= 2 else None
    return {"positions": recs, "series": series, "marks": marks}


_CSV_FIELDS = ["pos_deg", "t", "cam", "frame_oriented", "pose_from", "site", "true_shape",
               "read_shape", "theta_deg", "area_mm2", "area_ratio", "solidity",
               "elongation", "off_deg", "cut"]


def write_marks(rows, path):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_CSV_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: ("%.4f" % r[k] if isinstance(r[k], float) else r[k])
                        for k in _CSV_FIELDS})


def _f(x, fmt="%6.1f"):
    return fmt % x if x is not None else "     -"


def report(result, out=sys.stdout):
    p = lambda *a: print(*a, file=out)  # noqa: E731
    p("positions")
    p(" deg  frames  cam1 n  spread   cam2 n  spread   agree  note")
    for r in result["positions"]:
        cols = []
        for cam in ("cam1", "cam2"):
            m = r[cam]
            cols.append("%4d/%-3d %s" % (m[1] if m else 0, r["n"][cam],
                                         _f(m[2] if m else None, "%5.2f")))
        p("%4d  %6d  %s  %s  %s  %s" % (r["deg"], r["frames"], cols[0], cols[1],
                                        _f(r["agree_deg"], "%5.2f"), r["reason"] or ""))
    p("  (n = poses averaged / frames oriented; spread = their median angle to the mean, deg)")
    for cam in ("cam1", "cam2"):
        s = result["series"][cam]
        p("\n%s against its first position (turn about down = clockwise from above)" % cam)
        if s is None:
            p("  fewer than two positions with a pose")
            continue
        p(" deg  expected  measured   error  axis err  sign")
        for r in s["rows"]:
            p("%4d  %8.1f  %8.1f  %+6.1f  %s  %s" % (
                r["deg"], r["expected_deg"], r["measured_deg"], r["err_deg"],
                _f(r["axis_err_deg"], "%8.1f"),
                {True: "+", False: "WRONG", None: "."}[r["sign_ok"]]))
        errs = [abs(r["err_deg"]) for r in s["rows"][1:]]
        signs = [r["sign_ok"] for r in s["rows"] if r["sign_ok"] is not None]
        steps = [st["step_deg"] - st["expected_deg"] for st in s["steps"]]
        if errs:
            p("  |error| median %.2f, max %.2f deg; signs right %d of %d" % (
                float(np.median(errs)), max(errs), sum(signs), len(signs)))
        if steps:
            p("  steps: error median %+.2f, max |%.2f| deg; step signs right %d of %d" % (
                float(np.median(steps)), max(abs(x) for x in steps),
                sum(1 for st in s["steps"] if st["sign_ok"]),
                sum(1 for st in s["steps"] if st["sign_ok"] is not None)))
        p("  common axis %s deg from the floor normal (the disc's lean); closure %s deg" % (
            _f(s["axis_tilt_deg"], "%.2f"), _f(s["closure_deg"], "%.2f")))
    agrees = [r["agree_deg"] for r in result["positions"] if r["agree_deg"] is not None]
    if agrees:
        p("\ncam1/cam2 agree: median %.2f, max %.2f deg over %d positions, %d over 3 deg" % (
            float(np.median(agrees)), max(agrees), len(agrees), sum(1 for a in agrees if a > 3.0)))
    reasons = Counter()
    for r in result["positions"]:
        reasons.update(r["refusals"])
    if reasons:
        p("\nrefusals by reason")
        for (cam, why), n in sorted(reasons.items(), key=lambda kv: -kv[1]):
            p("  %s %4d  %s" % (cam, n, why))
    marks = result["marks"]
    if marks:
        p("\nmarks under the position's pose, by true shape and angle from the view centre")
        p(" shape  theta        n  read right  read as dot/bar/cross/none  area/ink  solidity")
        for shape in ("dot", "bar", "cross"):
            for lo, hi in zip(THETA_BANDS[:-1], THETA_BANDS[1:]):
                sel = [m for m in marks if m["true_shape"] == shape and lo <= m["theta_deg"] < hi]
                if not sel:
                    continue
                c = Counter(m["read_shape"] for m in sel)
                p(" %-5s  %2.0f-%-2.0f  %6d  %9.0f%%  %4d/%d/%d/%d  %8.2f  %8.2f" % (
                    shape, lo, hi, len(sel), 100.0 * c[shape] / len(sel), c["dot"], c["bar"],
                    c["cross"], c[None], float(np.median([m["area_ratio"] for m in sel])),
                    float(np.median([m["solidity"] for m in sel]))))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("series_dir")
    ap.add_argument("--step", type=int, default=5, help="every N-th frame pair (default 5)")
    ap.add_argument("--skip-s", type=float, default=0.5,
                    help="frames before this are the strobe settling (default 0.5)")
    ap.add_argument("--csv", default=None, help="mark table (default SERIESDIR/marks.csv)")
    args = ap.parse_args(argv)
    rig = stereo_geometry.load_rig()
    stereo_geometry.validate_rig(rig)
    result = run(args.series_dir, rig, mark_map.load_map(), step=args.step, skip_s=args.skip_s)
    report(result)
    path = args.csv or os.path.join(args.series_dir, "marks.csv")
    write_marks(result["marks"], path)
    print("\nmark table: %s (%d rows)" % (path, len(result["marks"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
