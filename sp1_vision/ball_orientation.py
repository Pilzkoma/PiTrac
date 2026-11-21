"""Identify the detected mark blobs on the mark map and return the ball's
absolute orientation R (map frame -> camera frame, n_cam = R @ n_map), or
refuse.

Spin is computed from the orientations of successive images, so a wrong pose
is far worse than a refusal: every step below can only discard.

1. Hypotheses: every ordered pair of classified blobs (i, j) whose angle is
   within PAIR_TOL_DEG of the map's neighbour angle, times every ordered pair
   of neighbouring sites (a, b) with the same shapes. R is the rotation
   between the triads (n, n x n') of both pairs, so blob i sits exactly on
   site a; a bar or cross at i must also agree in direction (DIR_TOL_DEG,
   mod 180 / mod 90).
2. Verification: a classified blob within MATCH_TOL_DEG of a predicted site
   matches it when shape and direction agree; with a different shape or
   direction it is a conflict. With the Unwrapped image given, a predicted
   site within MISSING_DEG of the view centre whose (valid) position holds no
   dark pixel at all is a conflict too. Any conflict discards the hypothesis.
   Blobs with shape None (clutter, marks cut by the frame edge) are never
   matched and never evidence against a pose, but they do count as ink.
3. Refit with kabsch on all matches and verify again until the match set is
   stable.
4. Best = most matches, then lowest rms. Refuse with fewer than MIN_MATCHED
   matches, rms above MAX_RMS_DEG, or another surviving pose with the same
   match count more than DISTINCT_DEG away.
5. Beyond the four rules (MISREAD_GUARD): refuse when a pose more than
   DISTINCT_DEG away would fit as many marks without conflict if exactly one
   classified blob had been read as another shape. The map has stars and V's
   that are one shape apart under a symmetry of the site set; without this a
   single misclassification returned poses 72 or 120 deg off (test
   test_one_misread_mark_never_gives_another_pose). Cost on random poses:
   about 5 % more refusals.
"""
import copy
import math

import numpy as np

from sp1_vision import ball_unwrap, mark_detect
from sp1_vision.ball_unwrap import R_OUT_PX

PAIR_TOL_DEG = 6.0
MATCH_TOL_DEG = 6.0
DIR_TOL_DEG = 20.0
MIN_MATCHED = 3
MAX_RMS_DEG = 3.0
DISTINCT_DEG = 10.0
MISSING_DEG = 50.0          # missing-mark check only this close to the view centre
# Refuse when one misread blob would make a different pose fit as well (beyond
# the brief's four rules; see _one_misread_rival and the task-4 report).
MISREAD_GUARD = True

_PERIOD_DEG = {"bar": 180.0, "cross": 90.0}
_MAX_REFITS = 4


class Orientation(object):
    def __init__(self, R, matched, rms_deg):
        self.R = R                  # (3,3) proper rotation, map -> camera
        self.matched = matched      # [(blob_index, site_id)]
        self.rms_deg = rms_deg

    def __repr__(self):
        return "Orientation(%d marks, rms %.2f deg)" % (len(self.matched), self.rms_deg)


class Refusal(object):
    def __init__(self, reason):
        self.reason = reason

    def __repr__(self):
        return "Refusal(%s)" % self.reason


def kabsch(map_vectors, cam_vectors):
    """Proper rotation R minimising sum |cam - R map|^2 (no translation).

    The determinant correction makes det(R) = +1 always: a reflection is
    never returned, even for mirrored or coplanar input.
    """
    a = np.asarray(map_vectors, float).reshape(-1, 3)
    b = np.asarray(cam_vectors, float).reshape(-1, 3)
    u, _, vt = np.linalg.svd(a.T @ b)
    d = 1.0 if np.linalg.det(vt.T @ u.T) >= 0 else -1.0
    return vt.T @ np.diag([1.0, 1.0, d]) @ u.T


def rotation_angle_deg(ra, rb):
    """Angle of the rotation ra @ rb.T."""
    c = (float(np.trace(ra @ rb.T)) - 1.0) / 2.0
    return math.degrees(math.acos(min(1.0, max(-1.0, c))))


def site_pixel(u, n_cam):
    """(col, row) in the unwrapped image of the camera-frame normal n_cam."""
    w, e1, e2 = u.basis
    n = np.asarray(n_cam, float)
    n = n / np.linalg.norm(n)
    theta = math.acos(min(1.0, max(-1.0, float(n @ w))))
    phi = math.atan2(float(n @ e2), float(n @ e1))
    c = float(u.centre_px)
    return (c + R_OUT_PX * theta * math.cos(phi), c + R_OUT_PX * theta * math.sin(phi))


def _angle_deg(a, b):
    return math.degrees(math.acos(min(1.0, max(-1.0, float(a @ b)))))


def _dir_err_deg(d_blob, t_pred, n, shape):
    """Angle between the blob's direction and the predicted one, in the
    tangent plane at n, modulo the shape's symmetry."""
    t = t_pred - float(t_pred @ n) * n
    nt = np.linalg.norm(t)
    d = d_blob - float(d_blob @ n) * n
    nd = np.linalg.norm(d)
    if nt < 1e-9 or nd < 1e-9:
        return 90.0
    a = math.degrees(math.acos(min(1.0, abs(float(d @ t)) / (nt * nd))))
    if _PERIOD_DEG[shape] == 90.0:
        a = min(a, 90.0 - a)
    return a


def _triad(p, q):
    t2 = np.cross(p, q)
    t2 /= np.linalg.norm(t2)
    return np.column_stack([p, t2, np.cross(p, t2)])


class _Evidence(object):
    """The classified blobs as arrays, plus the dark mask for the
    missing-mark check."""

    def __init__(self, blobs, unwrapped):
        self.index = [i for i, b in enumerate(blobs) if b.shape is not None]
        self.normals = np.array([b.normal / np.linalg.norm(b.normal)
                                 for b in (blobs[i] for i in self.index)]).reshape(-1, 3)
        self.shapes = [blobs[i].shape for i in self.index]
        self.directions = [blobs[i].direction for i in self.index]
        self.all_normals = np.array([b.normal / np.linalg.norm(b.normal)
                                     for b in blobs]).reshape(-1, 3)
        self.u = unwrapped
        if unwrapped is not None:
            self.dark = mark_detect.dark_mask(unwrapped).astype(bool)
            r = R_OUT_PX * math.radians(MATCH_TOL_DEG)
            ri = int(math.ceil(r))
            dy, dx = np.mgrid[-ri:ri + 1, -ri:ri + 1]
            keep = dx * dx + dy * dy <= r * r
            self.disc = (dx[keep], dy[keep])

    def ink_near(self, col, row):
        h, w = self.dark.shape
        xs = self.disc[0] + int(round(col))
        ys = self.disc[1] + int(round(row))
        ok = (xs >= 0) & (xs < w) & (ys >= 0) & (ys < h)
        return bool(self.dark[ys[ok], xs[ok]].any())

    def site_is_checkable(self, n_pred):
        """(col, row) of n_pred in the unwrapped image if it lies within
        MISSING_DEG of the view centre on a valid pixel, else None."""
        u = self.u
        if _angle_deg(n_pred, u.basis[0]) > MISSING_DEG:
            return None
        col, row = site_pixel(u, n_pred)
        c, r = int(round(col)), int(round(row))
        h, w = u.valid.shape
        if not (0 <= c < w and 0 <= r < h) or not u.valid[r, c]:
            return None
        return col, row


def _verify(R, ev, mmap):
    """Matches [(k, site)] of the classified blobs under R, and the list of
    conflicts (plain-English str), empty if there is none."""
    pred = mmap.normals @ R.T                   # (20,3) camera frame
    matches = []
    conflicts = []
    claimed = {}
    if len(ev.index):
        cosines = ev.normals @ pred.T
        for k in range(len(ev.index)):
            s = int(np.argmax(cosines[k]))
            ang = math.degrees(math.acos(min(1.0, max(-1.0, float(cosines[k, s])))))
            if ang > MATCH_TOL_DEG:
                continue                         # clutter for this pose
            shape, site_shape = ev.shapes[k], mmap.shapes[s]
            if shape != site_shape:
                conflicts.append("a %s where a %s belongs" % (shape, site_shape))
                continue
            if shape in _PERIOD_DEG:
                err = _dir_err_deg(ev.directions[k], R @ mmap.directions[s],
                                   ev.normals[k], shape)
                if err > DIR_TOL_DEG:
                    conflicts.append("a %s turned %.0f deg against its site" % (shape, err))
                    continue
            if s in claimed:
                conflicts.append("two marks at the site of one %s" % site_shape)
                continue
            claimed[s] = k
            matches.append((k, s))
    if ev.u is not None:
        for s in range(len(pred)):
            if s in claimed:
                continue
            spot = ev.site_is_checkable(pred[s])
            if spot is None:
                continue
            if len(ev.all_normals) and np.max(ev.all_normals @ pred[s]) >= math.cos(
                    math.radians(MATCH_TOL_DEG)):
                continue                         # a blob (even clutter) is there
            if not ev.ink_near(spot[0], spot[1]):
                conflicts.append("no ink where a %s belongs (%.0f deg from the view centre)" % (
                    mmap.shapes[s], _angle_deg(pred[s], ev.u.basis[0])))
    return matches, conflicts


def _fit(matches, ev, mmap):
    sites = [s for _, s in matches]
    ks = [k for k, _ in matches]
    R = kabsch(mmap.normals[sites], ev.normals[ks])
    res = ev.normals[ks] - mmap.normals[sites] @ R.T
    # angle from the chord length
    chords = np.linalg.norm(res, axis=1)
    angles = np.degrees(2.0 * np.arcsin(np.clip(chords / 2.0, 0.0, 1.0)))
    return R, float(math.sqrt(float(np.mean(angles ** 2))))


def _hypotheses(ev, mmap):
    out = []
    n = len(ev.index)
    target = mmap.neighbour_angle_deg
    for p in range(n):
        for q in range(n):
            if p == q:
                continue
            if abs(_angle_deg(ev.normals[p], ev.normals[q]) - target) > PAIR_TOL_DEG:
                continue
            cam = _triad(ev.normals[p], ev.normals[q])
            for a in range(len(mmap.shapes)):
                if mmap.shapes[a] != ev.shapes[p]:
                    continue
                for b in mmap.neighbours[a]:
                    if mmap.shapes[b] != ev.shapes[q]:
                        continue
                    R = cam @ _triad(mmap.normals[a], mmap.normals[b]).T
                    if ev.shapes[p] in _PERIOD_DEG:
                        err = _dir_err_deg(ev.directions[p], R @ mmap.directions[a],
                                           ev.normals[p], ev.shapes[p])
                        if err > DIR_TOL_DEG:
                            continue
                    out.append(R)
    return out


def _one_misread_rival(ev, mmap, best_R, n_best):
    """True if a pose more than DISTINCT_DEG from best_R would fit at least
    n_best marks without any conflict once exactly one classified blob's
    shape (and direction) were read differently.

    8 of the 20 stars (a site and its three neighbours) are one shape away
    from another star under one of the 59 non-trivial symmetries of the site
    set, and so are 234 (symmetry, V) combinations of the 60 site+2-neighbour
    V's. A symmetry maps sites onto sites, so the missing-ink check cannot
    tell the two poses apart either. Hypotheses here ignore shapes (every
    blob pair at the neighbour angle x every neighbouring site pair, all
    evaluated at once); a candidate is then re-verified in full with the one
    blob read as the shape that pose expects.
    """
    k = len(ev.index)
    pairs = [(p, q) for p in range(k) for q in range(k) if p != q
             and abs(_angle_deg(ev.normals[p], ev.normals[q])
                     - mmap.neighbour_angle_deg) <= PAIR_TOL_DEG]
    if not pairs:
        return False
    site_pairs = [(a, b) for a in range(len(mmap.shapes)) for b in mmap.neighbours[a]]
    cam = np.array([_triad(ev.normals[p], ev.normals[q]) for p, q in pairs])
    mp = np.array([_triad(mmap.normals[a], mmap.normals[b]) for a, b in site_pairs])
    Rh = np.einsum("pij,skj->psik", cam, mp).reshape(-1, 3, 3)        # cam @ mp.T
    pred = np.einsum("hij,sj->hsi", Rh, mmap.normals)                 # (H,20,3)
    cosines = np.einsum("ki,hsi->hks", ev.normals, pred)              # (H,k,20)
    near = np.argmax(cosines, axis=2)                                 # (H,k)
    within = np.take_along_axis(cosines, near[..., None], 2)[..., 0] >= math.cos(
        math.radians(MATCH_TOL_DEG))
    codes = {"dot": 0, "bar": 1, "cross": 2}
    site_code = np.array([codes[s] for s in mmap.shapes])
    blob_code = np.array([codes[s] for s in ev.shapes])
    ok = site_code[near] == blob_code[None, :]
    for kk in range(k):
        if ev.shapes[kk] not in _PERIOD_DEG:
            continue
        n = ev.normals[kk]
        t = np.einsum("hij,hj->hi", Rh, mmap.directions[near[:, kk]])
        t = t - (t @ n)[:, None] * n
        t /= np.maximum(np.linalg.norm(t, axis=1), 1e-12)[:, None]
        a = np.degrees(np.arccos(np.clip(np.abs(t @ ev.directions[kk]), 0.0, 1.0)))
        if ev.shapes[kk] == "cross":
            a = np.minimum(a, 90.0 - a)
        ok[:, kk] &= a <= DIR_TOL_DEG
    good = within & ok
    bad = within & ~ok
    cand = np.nonzero((bad.sum(1) == 1) & (good.sum(1) + 1 >= n_best))[0]
    for h in cand:
        if rotation_angle_deg(Rh[h], best_R) <= DISTINCT_DEG:
            continue
        kb = int(np.nonzero(bad[h])[0][0])
        s = int(near[h, kb])
        # read blob kb as the mark this pose expects there, then the full check
        alt = copy.copy(ev)
        alt.shapes = list(ev.shapes)
        alt.directions = list(ev.directions)
        alt.shapes[kb] = mmap.shapes[s]
        alt.directions[kb] = Rh[h] @ mmap.directions[s] if mmap.shapes[s] != "dot" else None
        matches, conflicts = _verify(Rh[h], alt, mmap)
        R = Rh[h]
        if not conflicts and len(matches) >= 2:
            R, _ = _fit(matches, alt, mmap)
            alt.directions[kb] = R @ mmap.directions[s] if mmap.shapes[s] != "dot" else None
            matches, conflicts = _verify(R, alt, mmap)
        if (not conflicts and len(matches) >= n_best
                and rotation_angle_deg(R, best_R) > DISTINCT_DEG):
            return True
    return False


def _distinct(poses):
    """Representatives of poses more than DISTINCT_DEG apart."""
    reps = []
    for R in poses:
        if all(rotation_angle_deg(R, q) > DISTINCT_DEG for q in reps):
            reps.append(R)
    return reps


def identify(blobs, mmap, unwrapped=None):
    """Orientation or Refusal for the blobs of one image (see module doc).

    unwrapped: the Unwrapped the blobs came from; enables the missing-mark
    check (blob-only callers may omit it).
    """
    ev = _Evidence(blobs, unwrapped)
    n_cls = len(ev.index)
    if n_cls < MIN_MATCHED:
        return Refusal("only %d classified marks" % n_cls)
    hyps = _hypotheses(ev, mmap)
    if not hyps:
        return Refusal("no two of %d classified marks fit a pair of neighbouring sites"
                       % n_cls)

    survivors = []                  # (n_matches, rms, R, matches)
    discarded = None                # (n_matches, -n_conflicts, reason) of the best discarded
    for R in hyps:
        matches, conflicts = _verify(R, ev, mmap)
        seen = []
        while not conflicts and len(matches) >= 2:
            key = sorted(matches)
            if key in seen or len(seen) >= _MAX_REFITS:
                break
            seen.append(key)
            R, _ = _fit(matches, ev, mmap)
            matches, conflicts = _verify(R, ev, mmap)
        if conflicts:
            score = (len(matches), -len(conflicts))
            if discarded is None or score > discarded[:2]:
                discarded = score + (conflicts[0],)
            continue
        if len(matches) < 2:
            continue
        R, rms = _fit(matches, ev, mmap)
        survivors.append((len(matches), rms, R, matches))

    if not survivors:
        if discarded is not None:
            return Refusal("best pose leaves " + discarded[2])
        return Refusal("no pose fits more than one of %d classified marks" % n_cls)

    survivors.sort(key=lambda t: (-t[0], t[1]))
    n_best, rms, R, matches = survivors[0]
    if n_best < MIN_MATCHED:
        return Refusal("best pose matches only %d of %d classified marks" % (n_best, n_cls))
    if rms > MAX_RMS_DEG:
        return Refusal("best pose fits %d marks at %.1f deg rms" % (n_best, rms))
    rivals = _distinct([t[2] for t in survivors if t[0] == n_best])
    if len(rivals) > 1:
        return Refusal("ambiguous: %d poses fit %d marks" % (len(rivals), n_best))
    if MISREAD_GUARD and _one_misread_rival(ev, mmap, R, n_best):
        return Refusal("ambiguous: one misread mark from another pose (%d marks)" % n_best)
    matched = sorted((ev.index[k], s) for k, s in matches)
    return Orientation(R, matched, rms)


def orient_image(gray, K, dist, centre_cam_m, mmap):
    """Unwrap, detect and identify: (Orientation | Refusal, Unwrapped, blobs)."""
    u = ball_unwrap.unwrap(gray, K, dist, centre_cam_m)
    blobs = mark_detect.detect_marks(u, mmap)
    return identify(blobs, mmap, u), u, blobs
