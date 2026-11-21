import copy
import time
import unittest
from unittest import mock

import cv2
import numpy as np

from sp1_vision import ball_orientation, ball_unwrap, mark_detect, mark_map, stereo_geometry
from sp1_vision.ball_orientation import Orientation, Refusal
from sp1_vision.mark_detect import MarkBlob
from sp1_vision.tests.render_ball import render_ball
from sp1_vision.tests.test_mark_map import rotation_taking


def _rot_angle_deg(ra, rb):
    """Angle of the rotation ra @ rb.T."""
    c = (np.trace(ra @ rb.T) - 1.0) / 2.0
    return float(np.degrees(np.arccos(np.clip(c, -1.0, 1.0))))


def _quat_to_r(q):
    w, x, y, z = q / np.linalg.norm(q)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _random_rotations(n, seed):
    """Uniform on SO(3): normalised 4D Gaussian quaternions."""
    rs = np.random.RandomState(seed)
    return [_quat_to_r(rs.normal(size=4)) for _ in range(n)]


def _rot_y(deg):
    t = np.radians(deg)
    c, s = np.cos(t), np.sin(t)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


def _synthetic_blob(mmap, r, site, shape=None):
    """A perfect MarkBlob for a site under pose r (normal, shape, direction)."""
    n = r @ mmap.normals[site]
    shape = mmap.shapes[site] if shape is None else shape
    direction = None
    if shape in ("bar", "cross"):
        direction = r @ mmap.directions[site]
    return MarkBlob(n, shape, direction, 40.0, 0.0, 1.0, 1.0, (0.0, 0.0))


class BallOrientationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = mark_map.load_map()
        rig = stereo_geometry.load_rig()
        cls.k, cls.d = rig.k1, rig.d1
        cls.centre = np.array([0.0, 0.0, 0.45])

    def _orient(self, r, **render_opts):
        img = render_ball(self.m, self.k, self.d, self.centre, r, **render_opts)
        return ball_orientation.orient_image(img, self.k, self.d, self.centre, self.m)

    def _face_pose(self, site, roll_deg=0.0):
        """Site `site` straight towards the camera, rolled about the view axis."""
        view = np.array([0.0, 0.0, -1.0])
        base = rotation_taking(self.m.normals[site], view)
        k = view
        t = np.radians(roll_deg)
        kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
        roll = np.eye(3) + np.sin(t) * kx + (1 - np.cos(t)) * kx @ kx
        return roll @ base

    def _rich_pose(self, roll_deg=0.0):
        """A pentagon face centre towards the camera: five marks at 37.4 deg,
        all well visible (a lone star of four marks can be one misread from
        another star, which the identifier refuses)."""
        m = self.m
        # 0 and two consecutive neighbours lie on one face; its centre is
        # equidistant from all three
        a, b, c = m.normals[0], m.normals[m.neighbours[0][0]], m.normals[m.neighbours[0][1]]
        f = np.cross(b - a, c - a)
        f *= np.sign(f @ a) / np.linalg.norm(f)
        view = np.array([0.0, 0.0, -1.0])
        t = np.radians(roll_deg)
        kx = np.array([[0, 1.0, 0], [-1.0, 0, 0], [0, 0, 0]])     # about -Z
        roll = np.eye(3) + np.sin(t) * kx + (1 - np.cos(t)) * kx @ kx
        return roll @ rotation_taking(f, view)

    # ---------------------------------------------------------------- kabsch
    def test_kabsch_recovers_a_rotation(self):
        r_true = _random_rotations(1, 3)[0]
        a = np.random.RandomState(1).normal(size=(5, 3))
        r = ball_orientation.kabsch(a, a @ r_true.T)
        np.testing.assert_allclose(r, r_true, atol=1e-9)

    def test_kabsch_never_mirrors(self):                    # Review Focus 4
        rs = np.random.RandomState(11)
        for trial in range(20):
            a = rs.normal(size=(4, 3))
            b = a.copy()
            b[:, 2] = -b[:, 2]                              # mirror image
            r = ball_orientation.kabsch(a, b)
            self.assertAlmostEqual(float(np.linalg.det(r)), 1.0, places=9)
            np.testing.assert_allclose(r @ r.T, np.eye(3), atol=1e-9)
        # coplanar points: the SVD leaves the sign free - still a rotation
        a = np.array([[1.0, 0, 0], [0, 1.0, 0], [1.0, 1.0, 0]])
        b = a.copy()
        b[:, 0] = -b[:, 0]
        self.assertAlmostEqual(float(np.linalg.det(ball_orientation.kabsch(a, b))), 1.0,
                               places=9)

    # ------------------------------------------------------- site pixel helper
    def test_site_pixel_inverts_normal_at(self):
        r = self._face_pose(0)
        img = render_ball(self.m, self.k, self.d, self.centre, r)
        u = ball_unwrap.unwrap(img, self.k, self.d, self.centre)
        rs = np.random.RandomState(5)
        for _ in range(50):
            x, y = rs.uniform(-110, 110, size=2)
            n = ball_unwrap.normal_at(u, x, y)
            col, row = ball_orientation.site_pixel(u, n)
            self.assertAlmostEqual(col, u.centre_px + x, places=6)
            self.assertAlmostEqual(row, u.centre_px + y, places=6)

    # ------------------------------------------------------- renderer poses
    def test_random_poses_recovered(self):
        t0 = time.time()
        n_ok, wrong, off, refusals = 0, [], [], {}
        for idx, r_true in enumerate(_random_rotations(60, 7)):
            res, _, _ = self._orient(r_true)
            if isinstance(res, Orientation):
                err = _rot_angle_deg(res.R, r_true)
                self.assertAlmostEqual(float(np.linalg.det(res.R)), 1.0, places=6)
                if err > 5.0:
                    wrong.append((idx, err))
                elif err > 1.0:
                    off.append((idx, err))
                else:
                    n_ok += 1
            else:
                self.assertIsInstance(res, Refusal)
                key = res.reason
                refusals[key] = refusals.get(key, 0) + 1
        print("\n  60 poses: %d orientations, %d refusals, %d wrong, %d off 1-5 deg, %.1f s"
              % (n_ok, sum(refusals.values()), len(wrong), len(off), time.time() - t0))
        for reason, count in sorted(refusals.items()):
            print("    refused %d x: %s" % (count, reason))
        self.assertEqual(wrong, [])
        self.assertEqual(off, [])
        self.assertGreaterEqual(n_ok, 50)

    def test_relative_turn_sign(self):
        r1 = self._rich_pose(17.0)
        r2 = _rot_y(20.0) @ r1
        o1, _, _ = self._orient(r1)
        o2, _, _ = self._orient(r2)
        self.assertIsInstance(o1, Orientation, getattr(o1, "reason", ""))
        self.assertIsInstance(o2, Orientation, getattr(o2, "reason", ""))
        rv, _ = cv2.Rodrigues(o2.R @ o1.R.T)
        np.testing.assert_allclose(np.degrees(rv.ravel()), [0.0, 20.0, 0.0], atol=1.0)

    # ------------------------------------------------------- Review Focus 5
    def test_two_marks_refused(self):
        r = self._face_pose(0)
        a = 0
        b = self.m.neighbours[a][0]
        blobs = [_synthetic_blob(self.m, r, a), _synthetic_blob(self.m, r, b)]
        res = ball_orientation.identify(blobs, self.m)
        self.assertIsInstance(res, Refusal)
        self.assertIn("only 2", res.reason)
        # a clutter blob does not make it three
        clutter = copy.copy(blobs[0])
        clutter.shape, clutter.direction = None, None
        res = ball_orientation.identify(blobs + [clutter], self.m)
        self.assertIsInstance(res, Refusal)
        self.assertIn("only 2", res.reason)

    def test_two_fitting_marks_among_three_refused(self):
        # three classified blobs, but only two of them sit on sites
        r = self._face_pose(0)
        a = 0
        b = self.m.neighbours[a][0]
        blobs = [_synthetic_blob(self.m, r, a), _synthetic_blob(self.m, r, b)]
        mid = blobs[0].normal + blobs[1].normal            # half way: no site near
        stray = copy.copy(blobs[0])
        stray.normal = mid / np.linalg.norm(mid)
        res = ball_orientation.identify(blobs + [stray], self.m)
        self.assertIsInstance(res, Refusal)
        self.assertIn("only 2 of 3", res.reason)

    def test_poor_fit_refused(self):
        # five marks pushed 3.5 deg away from the view axis: an expansion no
        # rotation absorbs, every blob still within MATCH_TOL_DEG
        r = self._rich_pose(40.0)
        w = np.array([0.0, 0.0, -1.0])
        blobs = []
        for s in [s for s in range(20) if (r @ self.m.normals[s])[2] < -0.6]:
            b = _synthetic_blob(self.m, r, s)
            ax = np.cross(w, b.normal)
            ax /= np.linalg.norm(ax)
            th = np.radians(3.5)
            n2 = b.normal * np.cos(th) + np.cross(ax, b.normal) * np.sin(th)
            b.normal = n2
            if b.direction is not None:
                d = b.direction - (b.direction @ n2) * n2
                b.direction = d / np.linalg.norm(d)
            blobs.append(b)
        res = ball_orientation.identify(blobs, self.m)
        self.assertIsInstance(res, Refusal)
        self.assertIn("deg rms", res.reason)

    def test_synthetic_blobs_identified(self):
        r = self._rich_pose(40.0)
        sites = [s for s in range(20) if (r @ self.m.normals[s])[2] < -0.6]
        blobs = [_synthetic_blob(self.m, r, s) for s in sites]
        res = ball_orientation.identify(blobs, self.m)
        self.assertIsInstance(res, Orientation, getattr(res, "reason", ""))
        self.assertLess(_rot_angle_deg(res.R, r), 1e-3)
        self.assertEqual(sorted(s for _, s in res.matched), sorted(sites))

    def test_wrong_shape_where_a_mark_belongs_is_refused_or_ignored(self):
        cases = 0
        for r_true in _random_rotations(8, 21):
            res, u, blobs = self._orient(r_true)
            if not isinstance(res, Orientation):
                continue
            cases += 1
            for bi, _site in res.matched:
                for shape in ("dot", "bar", "cross"):
                    if shape == blobs[bi].shape:
                        continue
                    changed = list(blobs)
                    b = copy.copy(blobs[bi])
                    b.shape = shape
                    if shape == "dot":
                        b.direction = None
                    elif b.direction is None:
                        t = np.cross(b.normal, [0.0, 1.0, 0.0])
                        b.direction = t / np.linalg.norm(t)
                    changed[bi] = b
                    with self.subTest(case=cases, blob=bi, shape=shape):
                        out = ball_orientation.identify(changed, self.m, u)
                        if isinstance(out, Orientation):
                            self.assertLess(_rot_angle_deg(out.R, r_true), 1.0)
                        else:
                            self.assertIsInstance(out, Refusal)
        self.assertGreaterEqual(cases, 5)

    def test_wrong_direction_is_a_conflict(self):
        r = self._rich_pose(40.0)
        sites = [s for s in range(20) if (r @ self.m.normals[s])[2] < -0.6]
        blobs = [_synthetic_blob(self.m, r, s) for s in sites]
        bars = [i for i, s in enumerate(sites) if self.m.shapes[s] == "bar"]
        self.assertTrue(bars)
        i = bars[0]
        n = blobs[i].normal
        d = blobs[i].direction
        turned = np.cross(n, d)                              # 90 deg off
        blobs[i] = copy.copy(blobs[i])
        blobs[i].direction = turned / np.linalg.norm(turned)
        res = ball_orientation.identify(blobs, self.m)
        self.assertIsInstance(res, Refusal)          # the true pose has a conflict
        self.assertIn("bar turned 90 deg", res.reason)

    def test_conflicts_discard_and_are_named(self):
        r = self._rich_pose(40.0)
        sites = [s for s in range(20) if (r @ self.m.normals[s])[2] < -0.6]
        clean = [_synthetic_blob(self.m, r, s) for s in sites]
        for i, s in enumerate(sites):
            for shape in ("dot", "bar", "cross"):
                if shape == self.m.shapes[s]:
                    continue
                blobs = list(clean)
                blobs[i] = _synthetic_blob(self.m, r, s, shape)
                if blobs[i].direction is not None:
                    blobs[i].direction = r @ self.m.east[s]    # some tangent
                with self.subTest(site=s, shape=shape):
                    res = ball_orientation.identify(blobs, self.m)
                    self.assertIsInstance(res, Refusal)
                    self.assertEqual(res.reason, "best pose leaves a %s where a %s belongs"
                                     % (shape, self.m.shapes[s]))
        # a mark split in two classified pieces is no mark the map knows
        piece = copy.copy(clean[0])
        res = ball_orientation.identify(clean + [piece], self.m)
        self.assertIsInstance(res, Refusal)
        self.assertIn("two marks at the site", res.reason)

    def test_symmetric_map_is_ambiguous(self):
        # all marks the same shape: the dodecahedron's 60 rotations all fit
        m = copy.copy(self.m)
        m.shapes = ["dot"] * 20
        m.directions = np.zeros((20, 3))
        r = self._rich_pose(40.0)
        sites = [s for s in range(20) if (r @ m.normals[s])[2] < -0.6]
        blobs = [_synthetic_blob(m, r, s) for s in sites]
        res = ball_orientation.identify(blobs, m)
        self.assertIsInstance(res, Refusal)
        self.assertIn("ambiguous", res.reason)

    def test_missing_mark_is_a_conflict(self):
        # erase one well-visible mark from the unwrapped image: the true pose
        # predicts ink there and finds none -> never that pose with the hole
        r = self._rich_pose(25.0)
        img = render_ball(self.m, self.k, self.d, self.centre, r)
        u = ball_unwrap.unwrap(img, self.k, self.d, self.centre)
        blobs = mark_detect.detect_marks(u, self.m)
        full = ball_orientation.identify(blobs, self.m, u)
        self.assertIsInstance(full, Orientation, getattr(full, "reason", ""))
        self.assertGreaterEqual(len(full.matched), 4)
        w = u.basis[0]
        victim = None
        for bi, s in full.matched:
            ang = np.degrees(np.arccos(np.clip(blobs[bi].normal @ w, -1, 1)))
            if 15.0 < ang < 45.0:
                victim = (bi, s)
                break
        self.assertIsNotNone(victim)
        bi, s = victim
        col, row = blobs[bi].xy
        erased = copy.copy(u)
        erased.image = u.image.copy()
        cv2.circle(erased.image, (int(round(col)), int(round(row))), 40, 200, -1)
        erased.image[~u.valid] = 0
        rest = [b for i, b in enumerate(blobs) if i != bi]
        # the four-rule core, without the guard: without the image the
        # remaining marks still give the pose, with it the hole is a conflict
        with mock.patch.object(ball_orientation, "MISREAD_GUARD", False):
            self.assertIsInstance(ball_orientation.identify(rest, self.m), Orientation)
            res = ball_orientation.identify(rest, self.m, erased)
        if isinstance(res, Orientation):
            self.fail("pose reported although a predicted mark is missing: %r (%.1f deg off)"
                      % (res.matched, _rot_angle_deg(res.R, r)))
        self.assertIn("no ink", res.reason)

    def _symmetries(self):
        """The 60 rotations of the site set, as (G, perm): G @ n_s = n_perm[s]."""
        m = self.m
        out = []
        b0 = m.neighbours[0][0]
        for a in range(20):
            for b in m.neighbours[a]:
                g = (ball_orientation._triad(m.normals[a], m.normals[b])
                     @ ball_orientation._triad(m.normals[0], m.normals[b0]).T)
                perm = np.argmax((m.normals @ g.T) @ m.normals.T, axis=1)
                out.append((g, perm))
        return out

    def _same_mark(self, s, t, g):
        m = self.m
        if m.shapes[s] != m.shapes[t]:
            return False
        if m.shapes[s] == "dot":
            return True
        d = g @ m.directions[s]
        return ball_orientation._dir_err_deg(m.directions[t], d, m.normals[t],
                                             m.shapes[s]) <= ball_orientation.DIR_TOL_DEG

    def test_one_misread_mark_never_gives_another_pose(self):
        # Some stars (a site and its three neighbours) differ from another star
        # only in the centre's shape. With that one mark misread, the other
        # star's pose fits all four blobs without a conflict, and the
        # missing-ink check cannot see it (the symmetry maps sites onto sites).
        # Measured without the guard (MISREAD_GUARD False): that wrong pose,
        # 72 or 120 deg off, is returned for all 8 stars, image or not. The
        # price: the clean view of such a star is refused as well.
        m = self.m
        cases = []
        for g, perm in self._symmetries():
            if np.allclose(g, np.eye(3)):
                continue
            for c in range(20):
                star = [c] + m.neighbours[c]
                bad = [s for s in star if not self._same_mark(s, perm[s], g)]
                if bad == [c]:
                    cases.append((c, g, perm))
        self.assertGreater(len(cases), 0)
        for c, g, perm in cases:
            r_true = self._face_pose(c, 30.0)
            r_wrong = r_true @ g.T                  # r_wrong @ n_perm[s] = r_true @ n_s
            img = render_ball(m, self.k, self.d, self.centre, r_true)
            u = ball_unwrap.unwrap(img, self.k, self.d, self.centre)
            blobs = mark_detect.detect_marks(u, m)
            clean = ball_orientation.identify(blobs, m, u)
            self.assertIsInstance(clean, Refusal)              # the price
            self.assertIn("one misread", clean.reason)
            w = u.basis[0]
            bi = int(np.argmax([b.normal @ w for b in blobs]))     # the centre mark
            misread = copy.copy(blobs[bi])
            misread.shape = m.shapes[perm[c]]
            misread.direction = (r_wrong @ m.directions[perm[c]]
                                 if misread.shape != "dot" else None)
            changed = list(blobs)
            changed[bi] = misread
            for unwrapped in (None, u):
                with self.subTest(site=c, image=unwrapped is not None):
                    out = ball_orientation.identify(changed, m, unwrapped)
                    if isinstance(out, Orientation):
                        self.assertLess(_rot_angle_deg(out.R, r_true), 1.0,
                                        "wrong pose, %.0f deg off" % _rot_angle_deg(out.R, r_true))
                    else:
                        self.assertIn("ambiguous", out.reason)

    def test_clutter_blob_at_a_site_is_not_evidence_against(self):
        r = self._rich_pose(40.0)
        sites = [s for s in range(20) if (r @ self.m.normals[s])[2] < -0.6]
        blobs = [_synthetic_blob(self.m, r, s) for s in sites]
        clutter = copy.copy(blobs[0])
        clutter.shape, clutter.direction = None, None
        # a clutter blob on top of a matched mark: not a second mark there
        res = ball_orientation.identify(blobs + [clutter], self.m)
        self.assertIsInstance(res, Orientation, getattr(res, "reason", ""))
        self.assertLess(_rot_angle_deg(res.R, r), 1e-3)
        self.assertEqual(len(res.matched), len(blobs))
        # a clutter blob instead of the mark (cut by the frame edge): no
        # conflict, never matched (the four-rule core, without the guard)
        with mock.patch.object(ball_orientation, "MISREAD_GUARD", False):
            res = ball_orientation.identify(blobs[1:] + [clutter], self.m)
        self.assertIsInstance(res, Orientation, getattr(res, "reason", ""))
        self.assertLess(_rot_angle_deg(res.R, r), 1e-3)
        self.assertNotIn(len(blobs) - 1, [bi for bi, _ in res.matched])

    # ------------------------------------------------------- refit loop exit
    def _noisy_blobs(self, seed, noise_deg=2.5):
        """Perfect blobs of the sites within 60 deg of the view axis under
        random pose `seed`, each normal moved noise_deg (rms) at random."""
        rs = np.random.RandomState(seed)
        r = _random_rotations(1, seed)[0]
        w = np.array([0.0, 0.0, -1.0])
        vis = [s for s in range(20) if (r @ self.m.normals[s]) @ w > np.cos(np.radians(60.0))]
        blobs = [_synthetic_blob(self.m, r, s) for s in vis]
        for b in blobs:
            ax = rs.normal(size=3)
            ax -= (ax @ b.normal) * b.normal
            ax /= np.linalg.norm(ax)
            th = np.radians(rs.normal() * noise_deg)
            b.normal = b.normal * np.cos(th) + ax * np.sin(th)
            if b.direction is not None:
                d = b.direction - (b.direction @ b.normal) * b.normal
                b.direction = d / np.linalg.norm(d)
        return r, blobs

    def _assert_pose_reproduces_its_matches(self, res, blobs):
        if not isinstance(res, Orientation):
            return
        ev = ball_orientation._Evidence(blobs, None)
        matches, conflicts = ball_orientation._verify(res.R, ev, self.m)
        self.assertEqual(conflicts, [])
        self.assertEqual(sorted((ev.index[k], s) for k, s in matches), res.matched)

    def test_refit_cap_never_returns_an_unverified_pose(self):     # final review 4
        # When the refit loop stops at _MAX_REFITS (or on a cycle) the match
        # set has not settled; the pose fitted last must be verified before
        # it is returned. With the cap at 0 every hypothesis takes that exit:
        # on these noisy views the returned pose used to match a different
        # set than the one it reported (seed 235 one blob more, 303 one less).
        for seed in (235, 303, 319, 351):
            with self.subTest(seed=seed):
                _, blobs = self._noisy_blobs(seed)
                with mock.patch.object(ball_orientation, "_MAX_REFITS", 0):
                    res = ball_orientation.identify(blobs, self.m)
                self._assert_pose_reproduces_its_matches(res, blobs)
                # the default cap: same invariant
                self._assert_pose_reproduces_its_matches(
                    ball_orientation.identify(blobs, self.m), blobs)

    def test_final_fit_refuses_a_match_set_its_pose_does_not_reproduce(self):
        r = self._rich_pose(40.0)
        sites = [s for s in range(20) if (r @ self.m.normals[s])[2] < -0.6]
        blobs = [_synthetic_blob(self.m, r, s) for s in sites]
        ev = ball_orientation._Evidence(blobs, None)
        full = [(k, s) for k, s in enumerate(sites)]
        R, rms = ball_orientation._final_fit(full, ev, self.m)
        self.assertLess(_rot_angle_deg(R, r), 1e-3)
        self.assertLess(rms, 1e-3)
        # a subset: its pose matches every blob, so the subset is not its match set
        self.assertIsNone(ball_orientation._final_fit(full[:-1], ev, self.m))


if __name__ == "__main__":
    unittest.main()
