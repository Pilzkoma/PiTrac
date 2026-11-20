import unittest

import cv2
import numpy as np

from sp1_vision import ball_unwrap, mark_detect, mark_map, stereo_geometry
from sp1_vision.tests.render_ball import _ink_mask, render_ball
from sp1_vision.tests.test_mark_map import rotation_taking


def _angle_deg(a, b):
    c = float(a @ b) / (np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.degrees(np.arccos(np.clip(c, -1.0, 1.0))))


def _dir_at(angle_deg, azimuth_deg=0.0):
    """Unit vector angle_deg from the view axis (-Z) of a centred ball."""
    a = np.radians(angle_deg)
    z = np.radians(azimuth_deg)
    return np.array([np.sin(a) * np.cos(z), np.sin(a) * np.sin(z), -np.cos(a)])


def _roll_about(axis, deg):
    k = np.asarray(axis, float) / np.linalg.norm(axis)
    t = np.radians(deg)
    kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(t) * kx + (1 - np.cos(t)) * kx @ kx


def _tangent_err_deg(d_got, t_want, n, period):
    """Angle between two tangents at n, modulo period (180 or 90)."""
    t = t_want - float(t_want @ n) * n
    t /= np.linalg.norm(t)
    a = float(np.degrees(np.arccos(np.clip(abs(float(d_got @ t)), 0.0, 1.0))))
    return a if period == 180.0 else min(a, 90.0 - a)


class MarkDetectTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = mark_map.load_map()
        rig = stereo_geometry.load_rig()
        cls.k, cls.d = rig.k1, rig.d1
        cls.centre = np.array([0.0, 0.0, 0.45])

    def _pose(self, site, deg, az, roll):
        v = _dir_at(deg, az)
        return _roll_about(v, roll) @ rotation_taking(self.m.normals[site], v)

    def _detect(self, r, **render_opts):
        img = render_ball(self.m, self.k, self.d, self.centre, r, **render_opts)
        u = ball_unwrap.unwrap(img, self.k, self.d, self.centre)
        return u, mark_detect.detect_marks(u, self.m)

    def _nearest(self, blobs, n_cam):
        self.assertTrue(blobs, "no blobs at all")
        errs = [_angle_deg(b.normal, n_cam) for b in blobs]
        i = int(np.argmin(errs))
        return blobs[i], errs[i]

    def _sites(self, shape):
        return [i for i, s in enumerate(self.m.shapes) if s == shape]

    def test_each_shape_classified_up_to_55deg(self):
        for shape in ("dot", "bar", "cross"):
            for site in self._sites(shape)[:2]:
                for deg in (0.0, 30.0, 55.0):
                    for az, roll in ((35.0, 20.0), (160.0, 75.0), (250.0, -40.0)):
                        with self.subTest(shape=shape, site=site, deg=deg, az=az, roll=roll):
                            r = self._pose(site, deg, az, roll)
                            _, blobs = self._detect(r)
                            n_cam = r @ self.m.normals[site]
                            b, err = self._nearest(blobs, n_cam)
                            self.assertLess(err, 3.0)
                            self.assertEqual(b.shape, shape,
                                             "area %.1f elong %.2f solid %.2f"
                                             % (b.area_mm2, b.elongation, b.solidity))
                            self.assertAlmostEqual(
                                b.area_mm2 / self.m.ink_area_mm2[shape], 1.0, delta=0.25)
                            if shape == "dot":
                                self.assertIsNone(b.direction)
                                continue
                            self.assertAlmostEqual(float(b.direction @ b.normal), 0.0, places=6)
                            period = 180.0 if shape == "bar" else 90.0
                            e = _tangent_err_deg(b.direction, r @ self.m.directions[site],
                                                 b.normal, period)
                            self.assertLess(e, 10.0)

    def test_thin_line_through_a_cross_is_ignored(self):
        site = self._sites("cross")[0]
        for j in self.m.neighbours[site]:
            with self.subTest(neighbour=j):
                r = self._pose(site, 10.0, 200.0, 15.0)
                na, nb = r @ self.m.normals[site], r @ self.m.normals[j]
                _, blobs = self._detect(r, line=(na, nb, 1.0, 40))
                near = [b for b in blobs if _angle_deg(b.normal, na) < 12.0]
                self.assertEqual(len(near), 1, [(b.shape, round(b.area_mm2, 1)) for b in near])
                self.assertEqual(near[0].shape, "cross")
                # the line also must not join the cross to the neighbour's mark
                self.assertLess(near[0].area_mm2, 1.5 * self.m.ink_area_mm2["cross"])

    def test_thick_print_is_clutter(self):
        site = self._sites("bar")[0]
        r = self._pose(site, 35.0, 90.0, 10.0)
        img = render_ball(self.m, self.k, self.d, self.centre, r)
        u = ball_unwrap.unwrap(img, self.k, self.d, self.centre)
        sites_cam = self.m.normals @ r.T
        c = u.centre_px
        rad = ball_unwrap.R_OUT_PX * np.radians(20.0)
        best = None
        for phi in np.radians(np.arange(0.0, 360.0, 5.0)):
            x, y = rad * np.cos(phi), rad * np.sin(phi)
            n = ball_unwrap.normal_at(u, x, y)
            clear = min(_angle_deg(n, s) for s in sites_cam)
            if best is None or clear > best[0]:
                best = (clear, x, y)
        clear, x, y = best
        self.assertGreater(clear, 24.0)      # >= ~9 mm from every site centre
        half = int(round(4.0 * ball_unwrap.PX_PER_MM)) // 2
        xi, yi = int(round(c + x)), int(round(c + y))
        u.image[yi - half:yi + half + 1, xi - half:xi + half + 1] = 40
        blobs = mark_detect.detect_marks(u, self.m)
        b, err = self._nearest(blobs, ball_unwrap.normal_at(u, x, y))
        self.assertLess(err, 2.0)
        self.assertGreater(b.area_mm2, mark_detect.MIN_AREA_MM2)
        self.assertLess(b.area_mm2, 20.0)
        self.assertIsNone(b.shape)
        self.assertIsNone(b.direction)

    def test_ring_is_clutter(self):
        # a ring (hole larger than a glint) is round and solid by its outline,
        # with a dot's area - it must not be guessed to be a dot
        site = self._sites("bar")[0]
        r = rotation_taking(self.m.normals[site], np.array([0.0, 0.0, -1.0]))
        img = render_ball(self.m, self.k, self.d, self.centre, r)
        sites_cam = self.m.normals @ r.T
        best = None
        u = ball_unwrap.unwrap(img, self.k, self.d, self.centre)
        for rad_deg in (15.0, 25.0, 35.0):
            rad = ball_unwrap.R_OUT_PX * np.radians(rad_deg)
            for phi in np.radians(np.arange(0.0, 360.0, 5.0)):
                x, y = rad * np.cos(phi), rad * np.sin(phi)
                n = ball_unwrap.normal_at(u, x, y)
                clear = min(_angle_deg(n, s) for s in sites_cam)
                if best is None or clear > best[0]:
                    best = (clear, x, y)
        clear, x, y = best
        self.assertGreater(clear, 26.0)      # ring + nearest mark do not touch
        for outer, inner in ((8.0, 4.0), (8.0, 3.0), (9.0, 5.0)):
            with self.subTest(outer=outer, inner=inner):
                u = ball_unwrap.unwrap(img, self.k, self.d, self.centre)
                c = u.centre_px
                yy, xx = np.mgrid[0:u.image.shape[0], 0:u.image.shape[1]]
                rr = np.hypot(xx - (c + x), yy - (c + y)) / ball_unwrap.PX_PER_MM
                u.image[(rr < outer / 2.0) & (rr >= inner / 2.0)] = 40
                blobs = mark_detect.detect_marks(u, self.m)
                b, err = self._nearest(blobs, ball_unwrap.normal_at(u, x, y))
                self.assertLess(err, 2.0)
                self.assertGreater(b.area_mm2, 0.6 * self.m.ink_area_mm2["dot"])
                self.assertIsNone(b.shape, repr(b))

    def test_glint_on_cross(self):                           # Review Focus 3
        # a 1 mm glint at the mark centre; bars too (3.5 mm wide, the hole
        # leaves thin walls the opening would cut)
        sites = self._sites("cross")[:3] + self._sites("bar")[:2]
        for site in sites:
            for deg in (0.0, 30.0, 50.0):
                with self.subTest(site=site, deg=deg):
                    r = self._pose(site, deg, 120.0, 30.0)
                    n_cam = r @ self.m.normals[site]
                    u, blobs = self._detect(r, glint=(n_cam, 1.0))
                    b, err = self._nearest(blobs, n_cam)
                    self.assertLess(err, 3.0)
                    self.assertEqual(b.shape, self.m.shapes[site],
                                     "area %.1f elong %.2f solid %.2f"
                                     % (b.area_mm2, b.elongation, b.solidity))
                    # the glint hole itself is filled in the dark mask
                    x, y = int(round(b.xy[0])), int(round(b.xy[1]))
                    self.assertEqual(int(mark_detect.dark_mask(u)[y, x]), 1)

    def test_gradient_does_not_create_ink(self):
        # dim towards the bottom of the image (lower limb) and towards one side
        for grad in (((0.0, 1.0), 0.35), ((1.0, 0.4), 0.35)):
            for site, deg, az in ((0, 20.0, 90.0), (7, 40.0, 270.0), (13, 5.0, 0.0)):
                with self.subTest(grad=grad, site=site):
                    r = self._pose(site, deg, az, 0.0)
                    u, blobs = self._detect(r, gradient=grad)
                    sites_cam = self.m.normals @ r.T
                    false_dark = ((mark_detect.dark_mask(u) > 0)
                                  & ~self._grow(self._true_ink(u, r), 2))
                    self.assertLess(int(np.count_nonzero(false_dark)), 20)
                    for b in blobs:
                        self.assertFalse(b.shape is None and b.area_mm2 >= 20.0,
                                         "clutter %.1f mm^2 at %.0f deg"
                                         % (b.area_mm2, b.theta_deg))
                    # and the rendered marks well inside the cap are still found
                    for s, n in enumerate(sites_cam):
                        if _angle_deg(n, u.basis[0]) <= 45.0:
                            b, err = self._nearest(blobs, n)
                            self.assertLess(err, 3.0)
                            self.assertEqual(b.shape, self.m.shapes[s])

    def _true_ink(self, u, r):
        """Ground-truth ink (bool) in the unwrapped image."""
        h, w = u.image.shape
        ys, xs = np.mgrid[0:h, 0:w].astype(float)
        n, _ = ball_unwrap._normals(u.basis, xs - u.centre_px, ys - u.centre_px)
        return _ink_mask(self.m, n.reshape(-1, 3) @ r).reshape(h, w)

    @staticmethod
    def _grow(mask, px):
        ker = np.ones((2 * px + 1, 2 * px + 1), np.uint8)
        return cv2.dilate(mask.astype(np.uint8), ker).astype(bool)

    @staticmethod
    def _shrink(mask, px):
        ker = np.ones((2 * px + 1, 2 * px + 1), np.uint8)
        return cv2.erode(mask.astype(np.uint8), ker).astype(bool)

    def test_frame_edge_does_not_create_or_eat_ink(self):     # Review Focus 1
        # ball partly outside the frame: the cut must neither read as ink nor
        # swallow the ink of a mark it cuts through (the identifier treats a
        # predicted site in `valid` without dark pixels as a conflict)
        k = self.k
        x = (1280 - 40 - k[0, 2]) * 0.45 / k[0, 0]
        centre = np.array([x, 0.0, 0.45])
        for site in (0, 9):
            with self.subTest(site=site):
                r = rotation_taking(self.m.normals[site], np.array([0.0, 0.0, -1.0]))
                img = render_ball(self.m, k, self.d, centre, r)
                u = ball_unwrap.unwrap(img, k, self.d, centre)
                self.assertGreater(np.count_nonzero(~u.valid & (u.theta_deg <= 60.0)), 500)
                mask = mark_detect.dark_mask(u)
                self.assertEqual(mask.dtype, np.uint8)
                self.assertFalse(np.any(mask[~u.valid]))
                ink = self._true_ink(u, r)
                false_dark = (mask > 0) & ~self._grow(ink, 2)
                self.assertLess(int(np.count_nonzero(false_dark)), 20)
                dist = cv2.distanceTransform(u.valid.astype(np.uint8), cv2.DIST_L2, 5)
                near_cut = (self._shrink(ink, 2) & self._shrink(u.valid, 1)
                            & (dist < 3.0 * ball_unwrap.PX_PER_MM) & (u.theta_deg <= 60.0))
                self.assertGreater(int(np.count_nonzero(near_cut)), 100)
                self.assertGreater(float(mask[near_cut].mean()), 0.95)

    def test_frame_edge_on_the_dim_side(self):               # Review Focus 1 + 2
        # flight frame: ball at the image edge and leaving the beam, dimmed to
        # 0.35 towards the cut - the valid strip by the cut must not read as ink
        k = self.k
        x = (1280 - 40 - k[0, 2]) * 0.45 / k[0, 0]
        centre = np.array([x, 0.0, 0.45])
        for site in (0, 9, 4):
            with self.subTest(site=site):
                r = rotation_taking(self.m.normals[site], np.array([0.0, 0.0, -1.0]))
                img = render_ball(self.m, k, self.d, centre, r, gradient=((1.0, 0.0), 0.35))
                u = ball_unwrap.unwrap(img, k, self.d, centre)
                mask = mark_detect.dark_mask(u)
                false_dark = (mask > 0) & ~self._grow(self._true_ink(u, r), 2)
                self.assertLess(int(np.count_nonzero(false_dark)), 20)
                for b in mark_detect.detect_marks(u, self.m):
                    self.assertFalse(b.shape is None and b.area_mm2 >= 20.0
                                     and b.theta_deg > 45.0, repr(b))

if __name__ == "__main__":
    unittest.main()
