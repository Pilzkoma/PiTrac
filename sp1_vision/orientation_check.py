#!/usr/bin/env python3
"""The mark orientation chain on real frames: both cameras, and rolling putts.

    python -m sp1_vision.orientation_check static CAM1.png CAM2.png
    python -m sp1_vision.orientation_check roll DIR1 DIR2 T_FROM T_TO [--sheet OUT.jpg]

static: one frame pair. The ball is found in both cameras
(ball_pair.find_ball_pair), each camera's frame is unwrapped round that
centre and identified on the map (ball_orientation.orient_image), and the
two poses are compared after the extrinsics: agree_deg is the angle of
R1 @ (rig.r.T @ R2).T, which should be 0 (spec acceptance of part 2).

roll: the frames of a triggered recording (file name = arrival time in s)
between T_FROM and T_TO, cam1 paired with the cam2 frame of nearest arrival
within PAIR_MAX_DT_S. Each pair as above; then for consecutive frames with
an Orientation in the same camera, the measured rotation between them
against pure rolling on the floor: angle |v| dt / r about up x v_hat, with
v from fit_motion on the stereo track (locally, over VELOCITY_WINDOW_S) and
up the floor normal in camera 1's frame (attitude pitch +1.60 deg,
CLAUDE.md; the 0.36 deg roll is ignored).

Frame times. File names are arrival times, which come in USB pairs 8 and
12 ms apart while the trigger edges are exactly TRIGGER_PERIOD_S apart and
every edge gives one frame in each camera. Arrival steps are therefore
snapped to whole periods (a raw 8/12 ms dt would put +-20 % into every
rolling comparison); a cam2 frame takes the time of its cam1 partner.

The 2026-11-18 putts are pushed with a slipper that stays next to the
ball, a source of ball-shaped rivals: find_ball_pair mostly (rightly)
refuses as "ambiguous". The roll therefore follows a track seeded by the
marks (orient_frames) and searches each frame near the expected position
(find_ball with near_m: only stereo pairings within NEAR_TOL_M of it).
Where stereo fails (the ball reaching cam2's right edge) one camera's circle
centre is met with the plane the stereo track rolls in (mono_ball); those
positions join the track and the velocity fit. Positions that are not
inliers of the local motion fit are not used for rolling comparisons, nor
are comparisons below MIN_SPEED_MPS (ball at rest).
"""
import copy
import math
import os
import re
import sys
from collections import Counter

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sp1_vision import ball_orientation, ball_pair, frame_analysis, mark_detect, sphere_fit  # noqa: E402
from sp1_vision import mark_map  # noqa: E402
from sp1_vision import stereo_geometry, strobe_event  # noqa: E402
from sp1_vision.ball_orientation import Orientation, Refusal  # noqa: E402
from sp1_vision.mark_map import BALL_RADIUS_MM  # noqa: E402

PITCH_DEG = 1.60
UP_CAM = (0.0, -math.cos(math.radians(PITCH_DEG)), math.sin(math.radians(PITCH_DEG)))
TRIGGER_PERIOD_S = 0.010
PAIR_MAX_DT_S = strobe_event.PAIR_MAX_DT_S
NEAR_TOL_M = 0.025              # near search: pairings this close to near_m only
TRACK_REACH_S = 0.035           # near_m from tracked frames at most this far away
SEED_AGREE_DEG = 3.0            # track seeds: both cameras oriented, agreeing this well
SEED_CANDIDATES = 3             # stereo positions tried as seeds per frame
MONO_RADIUS_TOL = 0.25          # monocular frames: Hough radius within this of the expected
PREDICT_POINTS = 5              # tracked positions in the line that predicts the next
VELOCITY_WINDOW_S = 0.06        # local fit_motion over +- this round a frame pair
MIN_VELOCITY_POINTS = 4
MAX_GAP_S = 0.030               # rolling comparison only across at most this dt
MIN_SPEED_MPS = strobe_event.MIN_SPEED_MPS   # slower: ball at rest, no comparison
# A ball-centre error across the line of sight turns every unwrapped normal
# by about its size / r: measured on real frames (cam1 16.1389, 16.1509 s,
# centre moved by +-0.5..2 mm) 3.7-4.2 deg per mm across, 0.08 deg per mm
# along the ray (10 mm along: 0.8 deg). So the centre is flagged on its
# across-ray residual, at the size that alone costs the static acceptance
# number (3 deg): 3 / 3.75 = 0.8 mm.
POSE_DEG_PER_MM_ACROSS = 3.75
CENTRE_FLAG_MM = 0.8            # across-ray residual from the neighbours' line
# How the ball centre is measured on its outline (CLI --centre):
#   "circle" - frame_analysis.refine_ball, a circle fit in the distorted image;
#   "cone"   - sphere_fit.refine_ball_cone, the cone of rays tangent to the
#              sphere (no projection / distortion bias; 2026-11-21_centre).
CENTRE = "cone"
BORDER_PX = 2.0                 # centre flagged when a used circle comes this near the edge


def _gray(img):
    img = np.asarray(img)
    if img.ndim == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return img


def _pair_refiner(rig, f1, f2):
    """The outline refiner for a frame pair under CENTRE. ball_pair calls one
    refine(frame, u, v, r) for both frames, so the cone refiner picks each
    camera's intrinsics by which frame object it is handed."""
    if CENTRE == "circle":
        return frame_analysis.refine_ball

    def refine(frame, u, v, r):
        if frame is f1:
            K, d = rig.k1, rig.d1
        elif frame is f2:
            K, d = rig.k2, rig.d2
        else:
            raise ValueError("cone refiner handed a frame it was not built for - "
                             "ball_pair must pass find_ball's frame objects")
        return sphere_fit.refine_ball_cone(frame, u, v, r, K, d)
    return refine


def find_ball(rig, g1, g2, near_m=None):
    """(BallPair, None) or (None, reason).

    near_m: the stereo search of find_ball_pair (same candidates, same
    gates, same refinement and outline rescue - the rescue only for circles
    within two ball radii of near_m's projection), but only pairings that
    triangulate within NEAR_TOL_M of near_m are considered. Masking the
    images round the expected position instead was tried and is worse:
    Hough then fits circles to the mask edge and the depth jumps by 30 mm.
    """
    f1, f2 = strobe_event.bgr(g1), strobe_event.bgr(g2)
    refine = _pair_refiner(rig, f1, f2)
    if near_m is None:
        return ball_pair.find_ball_pair(rig, f1, f2, refine=refine,
                                        max_candidates=strobe_event.MAX_CANDIDATES)
    near = np.asarray(near_m, float).reshape(3)
    low, high = ball_pair.radius_bounds_px(rig)
    c1 = frame_analysis.ball_candidates(f1, low, high)
    c2 = frame_analysis.ball_candidates(f2, low, high)
    if not c1 or not c2:
        return None, "no circle at all (%d / %d candidates)" % (len(c1), len(c2))
    if max(len(c1), len(c2)) > strobe_event.MAX_CANDIDATES:
        return None, "%d x %d circles - a noise image, not searched" % (len(c1), len(c2))

    def gated(cand1, cand2):
        surv, on_size, behind, at_all = ball_pair._consistent_pairs(rig, cand1, cand2)
        surv = [s for s in surv if np.linalg.norm(s[1] - near) <= NEAR_TOL_M]
        return surv, ball_pair._verdict(surv, on_size, behind, at_all, len(c1), len(c2))

    survivors, (best, reason) = gated(c1, c2)
    if best is None and not survivors:
        # find_ball_pair's rescue, restricted to the circles round the
        # expected position: re-measured on their outlines, paired again
        local = []
        for cands, K, d, p in ((c1, rig.k1, rig.d1, near),
                               (c2, rig.k2, rig.d2, rig.r @ near + rig.t_m)):
            uv, _ = cv2.projectPoints(p.reshape(1, 1, 3), np.zeros(3), np.zeros(3), K, d)
            uv = uv.reshape(2)
            reach = 2.0 * ball_pair.apparent_radius_px(K[0, 0], float(np.linalg.norm(p)))
            local.append([c for c in cands if math.hypot(c[0] - uv[0], c[1] - uv[1]) <= reach])
        rescue1 = ball_pair._outline_measured(f1, local[0], refine)
        rescue2 = ball_pair._outline_measured(f2, local[1], refine)
        _, (rescued, _) = gated(rescue1, rescue2)
        if rescued is not None:
            return ball_pair._to_ball_pair(rescued), None
    if best is None:
        return None, reason
    refined = ball_pair._refined_pair(rig, f1, f2, best, refine)
    return ball_pair._to_ball_pair(refined if refined is not None else best), None


def cam1_rotation(rig, cam, R):
    """A camera's orientation (map -> that camera) in camera 1's frame."""
    return R if cam == "cam1" else rig.r.T @ R


def _in_camera(rig, cam, R_cam1):
    return R_cam1 if cam == "cam1" else rig.r @ R_cam1


def _check_pose(R, unwrapped, blobs, mmap):
    """Pose R against one camera's blobs, by the identifier's own
    verification: {"matches": n, "conflicts": [...], "off_site": n}, where
    off_site counts the classified blobs further than MATCH_TOL_DEG from
    every site R predicts (on a site but of the wrong shape is a conflict)."""
    ev = ball_orientation._Evidence(blobs, unwrapped)
    matches, conflicts = ball_orientation._verify(R, ev, mmap)
    pred = mmap.normals @ R.T
    tol = math.cos(math.radians(ball_orientation.MATCH_TOL_DEG))
    off = int(np.sum(np.max(ev.normals @ pred.T, axis=1) < tol)) if len(ev.index) else 0
    return {"matches": len(matches), "conflicts": conflicts, "off_site": off}


def missing_ink_audit(o, unwrapped, blobs, mmap):
    """Number of predicted sites that passed the missing-mark check only on
    dark pixels the 2 mm opening removes (open point of Task 4: the check
    reads the raw dark mask, so a stray dark pixel within MATCH_TOL_DEG of
    the site silences it). 0 for a Refusal."""
    if not isinstance(o, Orientation):
        return 0
    ev = ball_orientation._Evidence(blobs, unwrapped)
    _, raw = ball_orientation._verify(o.R, ev, mmap)
    ev_open = copy.copy(ev)
    ev_open.dark = cv2.morphologyEx(
        ev.dark.astype(np.uint8), cv2.MORPH_OPEN,
        mark_detect._disc(mark_detect.OPEN_MM * mark_detect.PX_PER_MM)).astype(bool)
    _, opened = ball_orientation._verify(o.R, ev_open, mmap)
    return sum(1 for c in opened if c.startswith("no ink")) - sum(
        1 for c in raw if c.startswith("no ink"))


def orient_pair(rig, img1, img2, mmap, near_m=None):
    """Ball and orientation in both cameras of one frame pair.

    Returns a dict: ball (BallPair or None), reason (why no ball, or None),
    cam1, cam2 (Orientation | Refusal), agree_deg (angle of
    R1 @ (rig.r.T @ R2).T, None unless both are Orientations), detail
    {cam: (Unwrapped, blobs)}, cross_check {cam: the other camera's pose
    verified against this camera's blobs, or None}, ink_audit {cam: int}.
    """
    g1, g2 = _gray(img1), _gray(img2)
    out = {"ball": None, "reason": None, "agree_deg": None, "detail": {},
           "cross_check": {"cam1": None, "cam2": None},
           "ink_audit": {"cam1": 0, "cam2": 0}}
    ball, reason = find_ball(rig, g1, g2, near_m)
    out["ball"], out["reason"] = ball, reason
    if ball is None:
        out["cam1"] = out["cam2"] = Refusal("no ball: " + reason)
        return out
    return _orient_ball(rig, g1, g2, mmap, ball, out)


def _orient_ball(rig, g1, g2, mmap, ball, out, cams=("cam1", "cam2")):
    """Fill out (orient_pair's dict) for a ball centre (ball.xyz_m, camera 1
    frame); only the cameras in cams are oriented, the other refuses."""
    centres = {"cam1": ball.xyz_m, "cam2": rig.r @ ball.xyz_m + rig.t_m}
    for cam, g, K, d in (("cam1", g1, rig.k1, rig.d1), ("cam2", g2, rig.k2, rig.d2)):
        if cam not in cams:
            out[cam] = Refusal("ball not found in this camera (monocular frame)")
            continue
        o, u, blobs = ball_orientation.orient_image(g, K, d, centres[cam], mmap)
        out[cam] = o
        out["detail"][cam] = (u, blobs)
        out["ink_audit"][cam] = missing_ink_audit(o, u, blobs, mmap)
    o1, o2 = out["cam1"], out["cam2"]
    if isinstance(o1, Orientation) and isinstance(o2, Orientation):
        out["agree_deg"] = ball_orientation.rotation_angle_deg(o1.R, rig.r.T @ o2.R)
    for cam, other in (("cam1", "cam2"), ("cam2", "cam1")):
        if isinstance(out[cam], Orientation) and other in out["detail"]:
            R_other = _in_camera(rig, other, cam1_rotation(rig, cam, out[cam].R))
            u, blobs = out["detail"][other]
            out["cross_check"][other] = _check_pose(R_other, u, blobs, mmap)
    return out


class MonoBall(object):
    """A ball centre from one camera: the ray through its circle's centre
    met with the plane the stereo track's centres roll in."""

    def __init__(self, xyz_m, cam, uv, radius_px):
        self.xyz_m = np.asarray(xyz_m, float)
        self.cam = cam
        self.uv = tuple(float(x) for x in uv)
        self.radius_px = float(radius_px)

    @property
    def depth_mm(self):
        return float(self.xyz_m[2] * 1000.0)


def mono_ball(rig, g, cam, expected_m, up, height_m):
    """MonoBall in camera cam near expected_m (camera 1 frame), or None.

    The Hough circle nearest the expected position's projection, within
    half a ball radius of it and within MONO_RADIUS_TOL of the expected
    radius, its centre refined on the outline (refine_ball: centre good,
    radius biased, so the radius is not used for range). The centre is
    where that pixel's ray meets the plane up . X = height_m (camera 1
    frame) - a rolling ball's centre stays at one height, and at our
    geometry a pixel of centre error moves the result ~2 mm, against
    ~10 mm per pixel of radius for fx r / radius.
    """
    K, d = (rig.k1, rig.d1) if cam == "cam1" else (rig.k2, rig.d2)
    exp_cam = expected_m if cam == "cam1" else rig.r @ expected_m + rig.t_m
    uv0, _ = cv2.projectPoints(exp_cam.reshape(1, 1, 3), np.zeros(3), np.zeros(3), K, d)
    uv0 = uv0.reshape(2)
    r0 = ball_pair.apparent_radius_px(K[0, 0], float(np.linalg.norm(exp_cam)))
    frame = strobe_event.bgr(g)
    low, high = ball_pair.radius_bounds_px(rig)
    cands = [c for c in frame_analysis.ball_candidates(frame, low, high)
             if math.hypot(c[0] - uv0[0], c[1] - uv0[1]) <= 0.5 * r0
             and abs(c[2] / r0 - 1.0) <= MONO_RADIUS_TOL]
    if not cands:
        return None
    u, v, r = min(cands, key=lambda c: math.hypot(c[0] - uv0[0], c[1] - uv0[1]))
    fit = (frame_analysis.refine_ball(frame, u, v, r) if CENTRE == "circle"
           else sphere_fit.refine_ball_cone(frame, u, v, r, K, d))
    if fit is not None and math.hypot(fit[0] - u, fit[1] - v) <= 0.25 * r0:
        u, v = float(fit[0]), float(fit[1])
    p = cv2.undistortPoints(np.array([[[u, v]]], np.float64), K, d).reshape(2)
    ray = np.array([p[0], p[1], 1.0])
    if cam == "cam1":
        origin, ray1 = np.zeros(3), ray
    else:
        origin, ray1 = -rig.r.T @ rig.t_m, rig.r.T @ ray
    denom = float(up @ ray1)
    if abs(denom) < 1e-6:
        return None
    x = origin + (height_m - float(up @ origin)) / denom * ray1
    if np.linalg.norm(x - expected_m) > NEAR_TOL_M:
        return None
    return MonoBall(x, cam, (u, v), r)


def snap_times(ts, period_s=TRIGGER_PERIOD_S):
    """Arrival times -> trigger-grid times: each step rounded to whole
    periods (see module doc). None leaves them as they are."""
    if period_s is None or not len(ts):
        return list(ts)
    out = [float(ts[0])]
    for a, b in zip(ts[:-1], ts[1:]):
        out.append(out[-1] + period_s * max(1, int(round((b - a) / period_s))))
    return out


def stereo_positions(rig, g1, g2, limit=None):
    """Distinct ball-shaped stereo positions in a frame pair, best first:
    find_ball_pair's survivors (same candidates and gates), one per
    AMBIGUITY_SEPARATION_M cluster, at most `limit`."""
    f1, f2 = strobe_event.bgr(g1), strobe_event.bgr(g2)
    low, high = ball_pair.radius_bounds_px(rig)
    c1 = frame_analysis.ball_candidates(f1, low, high)
    c2 = frame_analysis.ball_candidates(f2, low, high)
    if not c1 or not c2 or max(len(c1), len(c2)) > strobe_event.MAX_CANDIDATES:
        return []
    survivors = ball_pair._consistent_pairs(rig, c1, c2)[0]
    survivors.sort(key=lambda sv: sv[0])
    out = []
    for sv in survivors:
        if all(np.linalg.norm(sv[1] - q) > ball_pair.AMBIGUITY_SEPARATION_M for q in out):
            out.append(sv[1])
        if limit is not None and len(out) >= limit:
            break
    return out


def _is_seed(r):
    return (r["ball"] is not None and r["agree_deg"] is not None
            and r["agree_deg"] < SEED_AGREE_DEG)


def orient_frames(frames, rig, mmap, period_s=TRIGGER_PERIOD_S, up_cam=UP_CAM):
    """orient_pair for every (t_s, gray1, gray2) along a ball track.

    The plain stereo search is not trusted on its own in a putt: the foot
    that pushes the ball stays next to it and gives ball-shaped rivals
    (mostly "ambiguous", sometimes a wrong unambiguous answer). The marks
    themselves identify the ball, so the track is seeded where a stereo
    position (one of the SEED_CANDIDATES best of stereo_positions) gives an
    Orientation in both cameras agreeing within SEED_AGREE_DEG. From there
    it grows frame by frame, nearest frame first: a frame next to the track
    is searched near the position expected from the tracked frames
    (_expected_position, find_ball with near_m). Untracked frames are tried
    as seeds in time order. Frames the track never reaches count as
    "no ball". Returns records [{"t": arrival, "tg": grid time, "near":
    bool, "seed": bool, **orient_pair}] in frame order.
    """
    ts = [float(f[0]) for f in frames]
    tg = snap_times(ts, period_s)
    up = np.asarray(up_cam, float) / np.linalg.norm(up_cam)
    recs = [None] * len(frames)
    tried = {}                      # frame -> distance to the track when last tried
    seed_note = {}

    def grow():
        while True:
            # the untracked frame nearest to the track first; a frame is
            # tried again once the track has come nearer than last time
            todo = []
            for i in range(len(frames)):
                if recs[i] is not None:
                    continue
                d = min([abs(r["tg"] - tg[i]) for r in recs if r is not None] or [1e9])
                if d <= TRACK_REACH_S + 1e-9 and d < tried.get(i, 1e9) - 1e-9:
                    todo.append((d, i))
            if not todo:
                return
            d, i = min(todo)
            tried[i] = d
            t, g1, g2 = frames[i]
            expected = _expected_position(recs, tg[i])
            nr = orient_pair(rig, g1, g2, mmap, near_m=expected)
            if nr["ball"] is None:
                nr = _mono_record(rig, g1, g2, mmap, expected, recs, up)
            if nr is not None:
                nr.update({"t": t, "tg": tg[i], "near": True, "seed": False})
                recs[i] = nr

    for i in range(len(frames)):
        if recs[i] is not None:
            continue
        t, g1, g2 = frames[i]
        positions = stereo_positions(rig, g1, g2, SEED_CANDIDATES)
        seed_note[i] = "%d stereo position(s), none identified in both cameras" % len(positions)
        for p in positions:
            r = orient_pair(rig, g1, g2, mmap, near_m=p)
            if _is_seed(r):
                r.update({"t": t, "tg": tg[i], "near": False, "seed": True})
                recs[i] = r
                grow()
                break
    for i, r in enumerate(recs):
        if r is None:
            why = "not on the track (%s)" % seed_note.get(i, "not tried")
            recs[i] = {"t": ts[i], "tg": tg[i], "near": False, "seed": False,
                       "ball": None, "reason": why, "agree_deg": None, "detail": {},
                       "cross_check": {"cam1": None, "cam2": None},
                       "ink_audit": {"cam1": 0, "cam2": 0},
                       "centre_resid_mm": None, "centre_along_mm": None,
                       "centre_across_mm": None, "at_border": [], "centre_flag": None,
                       "cam1": Refusal("no ball: " + why), "cam2": Refusal("no ball: " + why)}
    centre_quality(recs, rig)
    return recs


def centre_quality(recs, rig):
    """Per tracked record: how far its ball centre may be trusted.

    The residual is the centre's offset from a straight line fitted (least
    squares) through the OTHER tracked centres within VELOCITY_WINDOW_S,
    evaluated at its time (None with fewer than three others or less than
    20 ms covered), split along camera 1's ray to the ball and across it:
    centre_resid_mm (length), centre_along_mm, centre_across_mm. Only the
    across part moves the pose (POSE_DEG_PER_MM_ACROSS); stereo depth
    scatter is almost all along. at_border: the cameras whose circle used
    for the centre comes within BORDER_PX of the image edge (a cut circle
    shifts the fitted centre). centre_flag: a plain reason when the across
    residual exceeds CENTRE_FLAG_MM or a circle touches the edge, else None.
    The flag does not stop a frame from being oriented; rolling_check marks
    comparisons that use a flagged frame, and the summary reports both.
    A centre without a residual and not at the border is neither flagged
    nor known to be good (centre_status "unknown").
    """
    w, h = rig.image_size
    tracked = [k for k, r in enumerate(recs) if r["ball"] is not None]
    for k in tracked:
        r = recs[k]
        others = [j for j in tracked if j != k
                  and abs(recs[j]["tg"] - r["tg"]) <= VELOCITY_WINDOW_S + 1e-9]
        resid = along = across = None
        if len(others) >= 3:
            t = np.array([recs[j]["tg"] for j in others]) - r["tg"]
            if t.max() - t.min() >= 0.02:
                x = np.array([recs[j]["ball"].xyz_m for j in others])
                cols = [t, np.ones(len(t))]
                if len(others) >= 5:
                    cols.insert(0, t * t)    # the ball decelerates: a parabola
                coef = np.linalg.lstsq(np.vstack(cols).T, x, rcond=None)[0]
                d = 1000.0 * (r["ball"].xyz_m - coef[-1])
                ray = r["ball"].xyz_m / np.linalg.norm(r["ball"].xyz_m)
                resid = float(np.linalg.norm(d))
                along = float(d @ ray)
                across = float(np.linalg.norm(d - along * ray))
        b = r["ball"]
        if isinstance(b, MonoBall):
            circles = [(b.cam, b.uv, b.radius_px)]
        else:
            circles = [("cam1", b.uv1, b.radius1_px), ("cam2", b.uv2, b.radius2_px)]
        border = [cam for cam, (u, v), rad in circles
                  if u - rad < BORDER_PX or v - rad < BORDER_PX
                  or u + rad > w - 1 - BORDER_PX or v + rad > h - 1 - BORDER_PX]
        why = []
        if across is not None and across > CENTRE_FLAG_MM:
            why.append("%.1f mm across the ray off its neighbours' line (~%.0f deg)" % (
                across, across * POSE_DEG_PER_MM_ACROSS))
        if border:
            why.append("circle at the image edge in %s" % "/".join(border))
        r["centre_resid_mm"] = resid
        r["centre_along_mm"] = along
        r["centre_across_mm"] = across
        r["at_border"] = border
        r["centre_flag"] = "; ".join(why) or None


def centre_status(r):
    """"flagged" (centre_flag set), "unknown" (no residual: too few tracked
    neighbours, or centre_quality not run) or "ok"."""
    if r.get("centre_flag"):
        return "flagged"
    if r.get("centre_across_mm") is None:
        return "unknown"
    return "ok"


def split_by_centre(comps):
    """rolling_check's comparisons as (ok, flagged, unknown) by their
    "centre" field."""
    return tuple([c for c in comps if c["centre"] == k] for k in ("ok", "flagged", "unknown"))


def _mono_record(rig, g1, g2, mmap, expected, recs, up):
    """orient_pair's dict for a frame where only one camera finds the ball
    (MonoBall, camera 1 tried first), or None. The rolling plane's height
    is the median of up . X over the stereo-tracked records."""
    heights = [float(up @ r["ball"].xyz_m) for r in recs
               if r is not None and isinstance(r["ball"], ball_pair.BallPair)]
    if not heights:
        return None
    for cam in ("cam1", "cam2"):
        b = mono_ball(rig, g1 if cam == "cam1" else g2, cam, expected, up,
                      float(np.median(heights)))
        if b is not None:
            out = {"ball": b, "reason": None, "agree_deg": None, "detail": {},
                   "cross_check": {"cam1": None, "cam2": None},
                   "ink_audit": {"cam1": 0, "cam2": 0}}
            return _orient_ball(rig, g1, g2, mmap, b, out, cams=(cam,))
    return None


def _expected_position(recs, tg):
    """Ball position expected at grid time tg from the tracked records (None
    entries are not tracked), or None if none is within TRACK_REACH_S: a
    straight line fitted (least squares) through the PREDICT_POINTS tracked
    positions nearest in time within 3 x TRACK_REACH_S, evaluated at tg;
    the nearest position itself if they span less than 5 ms. A line through
    several points, because single positions scatter by ~10 mm in depth and
    a two-point velocity over 10 ms carries that into the prediction."""
    found = sorted((abs(r["tg"] - tg), k) for k, r in enumerate(recs)
                   if r is not None and r["ball"] is not None)
    if not found or found[0][0] > TRACK_REACH_S + 1e-9:
        return None
    use = [k for d, k in found if d <= 3 * TRACK_REACH_S + 1e-9][:PREDICT_POINTS]
    t = np.array([recs[k]["tg"] for k in use])
    x = np.array([recs[k]["ball"].xyz_m for k in use])
    if t.max() - t.min() < 0.005:
        return x[0]
    A = np.vstack([t - tg, np.ones(len(t))]).T
    coef = np.linalg.lstsq(A, x, rcond=None)[0]
    return coef[1]


def _rotvec(R):
    rv, _ = cv2.Rodrigues(np.asarray(R, np.float64))
    return rv.reshape(3)


def _angle_between_deg(a, b):
    c = float(a @ b) / (np.linalg.norm(a) * np.linalg.norm(b))
    return math.degrees(math.acos(min(1.0, max(-1.0, c))))


def _local_velocity(recs, tmid):
    """(velocity m/s, inlier set of record indices) from fit_motion on the
    found positions within VELOCITY_WINDOW_S of tmid, or (None, set())."""
    idx = [i for i, r in enumerate(recs)
           if r["ball"] is not None and abs(r["tg"] - tmid) <= VELOCITY_WINDOW_S + 1e-9]
    if len(idx) < MIN_VELOCITY_POINTS:
        return None, set()
    inl, vel, _ = strobe_event.fit_motion([(recs[i]["tg"], recs[i]["ball"]) for i in idx])
    if int(inl.sum()) < MIN_VELOCITY_POINTS:
        return None, set()
    return vel, {i for i, k in zip(idx, inl) if k}


def _worst_across(ra, rb):
    """The larger across-ray centre residual of two records, None if either
    is unknown (no centre_quality, or too few neighbours)."""
    xs = [r.get("centre_across_mm") for r in (ra, rb)]
    return None if any(x is None for x in xs) else max(xs)


def _worse_status(ra, rb):
    st = {centre_status(ra), centre_status(rb)}
    return "flagged" if "flagged" in st else ("unknown" if "unknown" in st else "ok")


def rolling_check(frames, rig, mmap, up_cam=UP_CAM, period_s=TRIGGER_PERIOD_S,
                  records=None):
    """Measured rotation between consecutive Orientations of one camera
    against pure rolling (module doc). frames: [(t_s, gray1, gray2)];
    records: orient_frames' output for these frames, if already computed.

    One dict per comparison: cam, t_a, t_b (arrival times of cam1's frames),
    dt, speed, pred_deg, meas_deg, angle_err_pct, axis_err_deg, sign_ok
    (measured axis on the predicted axis' side), lean_up_deg / lean_v_deg
    (measured axis' elevation towards up / towards v), rate_ratio,
    flagged (either frame's centre_flag is set, see centre_quality),
    centre ("flagged" if flagged, else "unknown" if either frame's centre
    status is unknown, else "ok"), across_mm (the larger across-ray centre
    residual of the two, or None).
    """
    recs = (orient_frames(frames, rig, mmap, period_s, up_cam) if records is None
            else records)
    up = np.asarray(up_cam, float)
    up = up / np.linalg.norm(up)
    r_m = BALL_RADIUS_MM / 1000.0
    out = []
    for cam in ("cam1", "cam2"):
        oriented = [i for i, r in enumerate(recs) if isinstance(r[cam], Orientation)]
        for a, b in zip(oriented[:-1], oriented[1:]):
            dt = recs[b]["tg"] - recs[a]["tg"]
            if dt <= 0 or dt > MAX_GAP_S + 1e-9:
                continue
            vel, inliers = _local_velocity(recs, 0.5 * (recs[a]["tg"] + recs[b]["tg"]))
            if vel is None or a not in inliers or b not in inliers:
                continue
            vh = vel - float(vel @ up) * up          # rolling on the floor
            speed = float(np.linalg.norm(vh))
            if speed < MIN_SPEED_MPS:
                continue
            axis_pred = np.cross(up, vh / speed)
            pred = speed * dt / r_m                  # rad
            Ra = cam1_rotation(rig, cam, recs[a][cam].R)
            Rb = cam1_rotation(rig, cam, recs[b][cam].R)
            rv = _rotvec(Rb @ Ra.T)
            meas = float(np.linalg.norm(rv))
            axis_err = _angle_between_deg(rv, axis_pred) if meas > 1e-9 else 180.0
            ax = rv / max(meas, 1e-12)
            # where the measured axis leans: towards up (a spin about the
            # vertical) and towards the direction of travel
            lean_up = math.degrees(math.asin(max(-1.0, min(1.0, float(ax @ up)))))
            lean_v = math.degrees(math.asin(max(-1.0, min(1.0, float(ax @ vh) / speed))))
            out.append({
                "cam": cam, "t_a": recs[a]["t"], "t_b": recs[b]["t"], "dt": dt,
                "speed": speed, "pred_deg": math.degrees(pred),
                "meas_deg": math.degrees(meas),
                "angle_err_pct": 100.0 * (meas - pred) / pred,
                "axis_err_deg": axis_err, "sign_ok": axis_err < 90.0,
                "lean_up_deg": lean_up, "lean_v_deg": lean_v,
                "rate_ratio": meas / pred,
                "flagged": bool(recs[a].get("centre_flag") or recs[b].get("centre_flag")),
                "centre": _worse_status(recs[a], recs[b]),
                "across_mm": _worst_across(recs[a], recs[b])})
    out.sort(key=lambda c: (c["t_a"], c["cam"]))
    return out


def _reason_class(reason):
    """A refusal reason without its numbers, for counting."""
    s = re.sub(r"\(.*?\)", "", reason)
    s = re.sub(r"[-+]?\d+(\.\d+)?", "#", s)
    s = s.split(":")[0] if s.startswith("no ball") else s
    return " ".join(s.split())


def _fmt(o):
    if isinstance(o, Orientation):
        return "ORIENT %d marks %.2f deg" % (len(o.matched), o.rms_deg)
    return "refused: " + o.reason


def load_window(d1, d2, t_from, t_to):
    """[(t1, gray1, gray2)] with cam2 paired by nearest arrival."""
    def listed(d):
        out = []
        for name in sorted(os.listdir(d)):
            m = re.match(r"t(\d+\.\d+)\.jpg$", name)
            if m and t_from <= float(m.group(1)) <= t_to:
                out.append((float(m.group(1)), os.path.join(d, name)))
        return out
    l1, l2 = listed(d1), listed(d2)
    frames = []
    for t1, p1 in l1:
        if not l2:
            break
        t2, p2 = min(l2, key=lambda x: abs(x[0] - t1))
        if abs(t2 - t1) > PAIR_MAX_DT_S:
            continue
        frames.append((t1, cv2.imread(p1, cv2.IMREAD_GRAYSCALE),
                       cv2.imread(p2, cv2.IMREAD_GRAYSCALE), t2))
    return frames


def _sheet(recs, mmap, path, width=160):
    """One row per camera, one column per frame: the unwrapped cap with its
    blobs (matched green, classified but unmatched yellow, clutter grey)."""
    tiles = {"cam1": [], "cam2": []}
    for r in recs:
        for cam in ("cam1", "cam2"):
            if cam not in r["detail"]:
                tile = np.zeros((width, width, 3), np.uint8)
            else:
                u, blobs = r["detail"][cam]
                tile = cv2.cvtColor(u.image, cv2.COLOR_GRAY2BGR)
                matched = {k for k, _ in r[cam].matched} if isinstance(
                    r[cam], Orientation) else set()
                for k, bl in enumerate(blobs):
                    col = (0, 200, 0) if k in matched else (
                        (0, 220, 255) if bl.shape else (150, 150, 150))
                    cv2.circle(tile, (int(bl.xy[0]), int(bl.xy[1])), 14, col, 2)
                    if bl.shape:
                        cv2.putText(tile, bl.shape[0], (int(bl.xy[0]) - 5, int(bl.xy[1]) + 5),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1)
                if isinstance(r[cam], Orientation):
                    for _, s in r[cam].matched:
                        c, w = ball_orientation.site_pixel(u, r[cam].R @ mmap.normals[s])
                        cv2.drawMarker(tile, (int(c), int(w)), (0, 255, 0),
                                       cv2.MARKER_CROSS, 8, 1)
                tile = cv2.resize(tile, (width, width))
            label = "%.4f %s" % (r["t"], "OK" if isinstance(r[cam], Orientation) else "-")
            cv2.putText(tile, label, (3, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.38,
                        (255, 255, 255), 1)
            tiles[cam].append(tile)
    cols = 12
    rows = []
    for start in range(0, len(recs), cols):
        for cam in ("cam1", "cam2"):
            row = tiles[cam][start:start + cols]
            row = row + [np.zeros_like(row[0])] * (cols - len(row))
            rows.append(np.hstack(row))
        rows.append(np.zeros((6, rows[-1].shape[1], 3), np.uint8))
    cv2.imwrite(path, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 80])


def _print_pair(r, mmap):
    b = r["ball"]
    if b is None:
        print("no ball: %s" % r["reason"])
        return
    print("ball X %+.1f Y %+.1f Z %.1f mm, radius %.1f / %.1f px" % (
        b.xyz_m[0] * 1000, b.xyz_m[1] * 1000, b.depth_mm, b.radius1_px, b.radius2_px))
    for cam in ("cam1", "cam2"):
        print("%s: %s" % (cam, _fmt(r[cam])))
        for k, bl in enumerate(r["detail"][cam][1]):
            print("   blob %d %r" % (k, bl))
        if isinstance(r[cam], Orientation):
            print("   matched (blob, site): %s" % ", ".join(
                "(%d, %d %s)" % (k, s, mmap.shapes[s]) for k, s in r[cam].matched))
        if r["cross_check"][cam] is not None:
            cc = r["cross_check"][cam]
            print("   other camera's pose here: %d matches, %d classified blobs off every "
                  "site, conflicts %s" % (cc["matches"], cc["off_site"],
                                          cc["conflicts"] or "none"))
        if r["ink_audit"][cam]:
            print("   missing-ink check silenced only by unopened dark pixels at %d site(s)"
                  % r["ink_audit"][cam])
    if r["agree_deg"] is not None:
        print("cam1 / cam2 agree within %.2f deg" % r["agree_deg"])


def _median(xs):
    return float(np.median(xs)) if len(xs) else float("nan")


def main(argv=None):
    global CENTRE
    argv = sys.argv[1:] if argv is None else argv
    if "--centre" in argv:
        i = argv.index("--centre")
        CENTRE = argv[i + 1]
        if CENTRE not in ("circle", "cone"):
            print("--centre circle|cone")
            return 2
        argv = argv[:i] + argv[i + 2:]
    rig = stereo_geometry.load_rig()
    stereo_geometry.validate_rig(rig)
    mmap = mark_map.load_map()
    if len(argv) == 3 and argv[0] == "static":
        r = orient_pair(rig, cv2.imread(argv[1], cv2.IMREAD_GRAYSCALE),
                        cv2.imread(argv[2], cv2.IMREAD_GRAYSCALE), mmap)
        _print_pair(r, mmap)
        return 0
    if len(argv) in (5, 7) and argv[0] == "roll":
        sheet = argv[6] if len(argv) == 7 and argv[5] == "--sheet" else None
        loaded = load_window(argv[1], argv[2], float(argv[3]), float(argv[4]))
        frames = [(t1, g1, g2) for t1, g1, g2, _ in loaded]
        recs = orient_frames(frames, rig, mmap)
        print("%d frame pairs %.2f-%.2f s" % (len(recs), float(argv[3]), float(argv[4])))
        print("   t cam1   t cam2  grid    ball Z  along across  cam1                          "
              "cam2                          agree  centre flag")
        for r, (_, _, _, t2) in zip(recs, loaded):
            z = ("%6.1f%s" % (r["ball"].depth_mm, "s" if r["seed"] else (
                "m" if isinstance(r["ball"], MonoBall) else " "))
                 if r["ball"] is not None else "   -   ")
            res = ("%+5.1f %6.2f" % (r["centre_along_mm"], r["centre_across_mm"])
                   if r["centre_resid_mm"] is not None else "    -      -")
            print("%8.4f %8.4f %+6.3f %s %s  %-29s %-29s %-5s  %s" % (
                r["t"], t2, r["tg"] - recs[0]["tg"], z, res, _fmt(r["cam1"])[:29],
                _fmt(r["cam2"])[:29],
                "%.2f" % r["agree_deg"] if r["agree_deg"] is not None else "-",
                r["centre_flag"] or ("unknown (too few neighbours)" if r["ball"] is not None
                                     and centre_status(r) == "unknown" else "")))
        comps = rolling_check(frames, rig, mmap, records=recs)
        print("\nrolling comparison (consecutive Orientations, same camera)")
        print("cam   t_a      t_b      dt ms  v m/s  pred deg  meas deg  err %   axis deg"
              "  (lean up / to v)  sign  flagged  across mm")
        for c in comps:
            print("%s %8.4f %8.4f %5.0f  %5.2f  %8.1f  %8.1f  %+5.0f  %8.1f  (%+5.1f / %+5.1f)"
                  "    %-5s %-7s  %s" % (
                      c["cam"], c["t_a"], c["t_b"], c["dt"] * 1000, c["speed"], c["pred_deg"],
                      c["meas_deg"], c["angle_err_pct"], c["axis_err_deg"], c["lean_up_deg"],
                      c["lean_v_deg"], "+" if c["sign_ok"] else "WRONG",
                      {"ok": "", "flagged": "F", "unknown": "?"}[c["centre"]],
                      "%.2f" % c["across_mm"] if c["across_mm"] is not None else "-"))
        print("\nsummary")
        n = len(recs)
        nb = sum(1 for r in recs if r["ball"] is not None)
        print("frame pairs %d, ball on the track in %d (%d seed frame(s), %d monocular)" % (
            n, nb, sum(1 for r in recs if r["seed"]),
            sum(1 for r in recs if isinstance(r["ball"], MonoBall))))
        reasons = Counter()
        for cam in ("cam1", "cam2"):
            k = sum(1 for r in recs if isinstance(r[cam], Orientation))
            print("%s: Orientation in %d of %d frames (%.0f %%), %d of %d with the ball "
                  "found (%.0f %%)" % (cam, k, n, 100.0 * k / max(n, 1), k, nb,
                                      100.0 * k / max(nb, 1)))
            for r in recs:
                if isinstance(r[cam], Refusal):
                    reasons[(cam, _reason_class(r[cam].reason))] += 1
        alongs = [abs(r["centre_along_mm"]) for r in recs if r["centre_resid_mm"] is not None]
        acrosses = [r["centre_across_mm"] for r in recs if r["centre_resid_mm"] is not None]
        if acrosses:
            print("centre residual from the neighbours' line: along the ray median %.1f mm "
                  "(max %.1f), across median %.2f mm (90th percentile %.2f, max %.2f); "
                  "flagged frames %d (across over %.1f mm %d, circle at the edge %d)" % (
                      _median(alongs), max(alongs), _median(acrosses),
                      float(np.percentile(acrosses, 90)), max(acrosses),
                      sum(1 for r in recs if r["centre_flag"]), CENTRE_FLAG_MM,
                      sum(1 for x in acrosses if x > CENTRE_FLAG_MM),
                      sum(1 for r in recs if r["at_border"])))
        unknown = [r for r in recs if r["ball"] is not None and centre_status(r) == "unknown"]
        print("centre quality unknown (too few tracked neighbours, not counted as "
              "unflagged): %d frame(s)%s" % (len(unknown), "".join(
                  " %.4f" % r["t"] for r in unknown)))
        for label, keep in (("", lambda r: True),
                            ("unflagged ", lambda r: centre_status(r) == "ok")):
            agrees = [r["agree_deg"] for r in recs if r["agree_deg"] is not None and keep(r)]
            if agrees:
                print("both cameras oriented in %d %sframes: agree median %.2f deg, max %.2f "
                      "deg, over 3 deg %d" % (len(agrees), label, _median(agrees),
                                              max(agrees), sum(1 for a in agrees if a >= 3.0)))
        lone = [r["cross_check"][cam] for r in recs for cam in ("cam1", "cam2")
                if r["cross_check"][cam] is not None and r["agree_deg"] is None]
        print("a pose in one camera only: %d; carried into the other camera it puts a "
              "classified blob off every site in %d, a wrong shape on a site in %d" % (
                  len(lone), sum(1 for c in lone if c["off_site"]),
                  sum(1 for c in lone if c["conflicts"])))
        print("missing-ink check passed only on unopened dark pixels: %d site(s) in %d frame(s)"
              % (sum(sum(r["ink_audit"].values()) for r in recs),
                 sum(1 for r in recs if any(r["ink_audit"].values()))))
        print("refusals by reason:")
        for (cam, why), k in sorted(reasons.items(), key=lambda x: (x[0][0], -x[1])):
            print("   %s %3d  %s" % (cam, k, why))
        if comps:
            half = comps[len(comps) // 2:]
            print("rolling: %d comparisons, median |angle error| %.0f %%, median axis error "
                  "%.1f deg, signs right %d of %d (later half of the comparisons: "
                  "%d of %d)" % (
                      len(comps), _median([abs(c["angle_err_pct"]) for c in comps]),
                      _median([c["axis_err_deg"] for c in comps]),
                      sum(c["sign_ok"] for c in comps), len(comps),
                      sum(c["sign_ok"] for c in half), len(half)))
            print("         later half of the comparisons (the list split in two, not "
                  "half the roll time): median |angle error| %.0f %%, median axis error "
                  "%.1f deg" % (_median([abs(c["angle_err_pct"]) for c in half]),
                     _median([c["axis_err_deg"] for c in half])))
            clean, _, unknown_c = split_by_centre(comps)
            print("rolling, flagged centres left out: %d of %d comparisons, median |angle "
                  "error| %.0f %%, median axis error %.1f deg, signs right %d of %d "
                  "(%d with an unknown centre left out too)" % (
                      len(clean), len(comps), _median([abs(c["angle_err_pct"]) for c in clean]),
                      _median([c["axis_err_deg"] for c in clean]),
                      sum(c["sign_ok"] for c in clean), len(clean), len(unknown_c)))
            if unknown_c:
                print("rolling, unknown centre only: %d comparisons, median |angle error| "
                      "%.0f %%, median axis error %.1f deg, signs right %d of %d" % (
                          len(unknown_c), _median([abs(c["angle_err_pct"]) for c in unknown_c]),
                          _median([c["axis_err_deg"] for c in unknown_c]),
                          sum(c["sign_ok"] for c in unknown_c), len(unknown_c)))
            chalf = clean[len(clean) // 2:]
            print("         later half of the comparisons (the list split in two, not "
                  "half the roll time): median |angle error| %.0f %%, median axis error "
                  "%.1f deg" % (_median([abs(c["angle_err_pct"]) for c in chalf]),
                     _median([c["axis_err_deg"] for c in chalf])))
        if sheet:
            _sheet(recs, mmap, sheet)
            print("sheet: %s" % sheet)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
