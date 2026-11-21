"""sphere_fit: the ball centre from the cone of sight rays tangent to the sphere."""

import unittest

import cv2
import numpy as np

from sp1_vision import frame_analysis, mark_map, sphere_fit, stereo_geometry
from sp1_vision.mark_map import BALL_RADIUS_MM
from sp1_vision.tests.render_ball import render_ball

R_M = BALL_RADIUS_MM / 1000.0


def _cone_rays(axis, alpha, n=72):
    axis = np.asarray(axis, float) / np.linalg.norm(axis)
    a = np.cross(axis, [0.0, 1.0, 0.0])
    a /= np.linalg.norm(a)
    b = np.cross(axis, a)
    phi = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return (np.cos(alpha) * axis[None, :]
            + np.sin(alpha) * (np.cos(phi)[:, None] * a + np.sin(phi)[:, None] * b))


def _angle(a, b):
    return float(np.arccos(np.clip(np.dot(a, b) / np.linalg.norm(a) / np.linalg.norm(b),
                                   -1.0, 1.0)))


def _direction(deg_off, towards_deg=30.0):
    """Unit vector deg_off from the optical axis, tilted towards image angle towards_deg."""
    t, p = np.radians(deg_off), np.radians(towards_deg)
    return np.array([np.sin(t) * np.cos(p), np.sin(t) * np.sin(p), np.cos(t)])


class FitCone(unittest.TestCase):
    def test_exact_cone(self):
        axis = _direction(25.0)
        alpha = np.radians(2.8)
        got = sphere_fit.fit_cone(_cone_rays(axis, alpha))
        self.assertIsNotNone(got)
        self.assertLess(_angle(got[0], axis), 1e-9)
        self.assertAlmostEqual(got[1], alpha, delta=1e-9)

    def test_outliers_are_trimmed(self):
        axis = _direction(15.0)
        alpha = np.radians(2.8)
        rays = _cone_rays(axis, alpha, 100)
        bad = _cone_rays(axis, alpha + np.radians(0.3), 100)[::5]   # 20 % of the count
        got = sphere_fit.fit_cone(np.vstack([rays, bad]))
        self.assertLess(np.degrees(_angle(got[0], axis)), 1e-3)

    def test_too_few_rays(self):
        self.assertIsNone(sphere_fit.fit_cone(_cone_rays([0, 0, 1], 0.05, 5)))

    def test_degenerate_rays(self):
        rays = np.tile([0.0, 0.0, 1.0], (40, 1))
        self.assertIsNone(sphere_fit.fit_cone(rays))

    def test_centre_from_the_exact_cone(self):
        centre = _direction(20.0) * 0.44
        alpha = np.arcsin(R_M / np.linalg.norm(centre))
        got = sphere_fit.centre_from_cone(centre / np.linalg.norm(centre), alpha)
        self.assertLess(np.linalg.norm(got - centre) * 1000, 0.01)


class Bilinear(unittest.TestCase):
    def test_exact_between_pixels(self):
        # cv2.remap rounds positions to 1/32 px on OpenCV 4.5.4; this must not
        img = np.array([[0.0, 100.0], [0.0, 100.0]], np.float32)
        got = sphere_fit.bilinear(img, np.array([[0.01]]), np.array([[0.5]]))
        self.assertAlmostEqual(float(got[0, 0]), 1.0, places=4)

    def test_border_is_replicated(self):
        img = np.arange(16, dtype=np.float32).reshape(4, 4)
        got = sphere_fit.bilinear(img, np.array([[-3.0, 9.0]]), np.array([[1.0, 2.0]]))
        self.assertEqual(list(got[0]), [4.0, 11.0])


class RefineBallCone(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = mark_map.load_map()
        rig = stereo_geometry.load_rig()
        cls.k, cls.d = rig.k1, rig.d1

    def _truth_px(self, centre):
        p, _ = cv2.projectPoints(centre.reshape(1, 1, 3), np.zeros(3), np.zeros(3),
                                 self.k, self.d)
        return p.reshape(2)

    def _render(self, centre, ink=False, R=None):
        R = np.eye(3) if R is None else R
        return render_ball(self.m, self.k, self.d, centre, R, ball_grey=200,
                           ink_grey=40 if ink else 200, background=15, oversample=4)

    def _seed(self, centre, off=(0.0, 0.0)):
        u, v = self._truth_px(centre) + np.asarray(off)
        return float(u), float(v), float(self.k[0, 0] * R_M / centre[2])

    def _err(self, refine, centre, ink=False, off=(0.0, 0.0), R=None):
        img = self._render(centre, ink, R)
        u, v, r = self._seed(centre, off)
        fit = refine(img, u, v, r)
        self.assertIsNotNone(fit)
        return float(np.hypot(*(np.array(fit[:2]) - self._truth_px(centre))))

    def _cone(self, frame, u, v, r):
        return sphere_fit.refine_ball_cone(frame, u, v, r, self.k, self.d)

    def test_plain_ball_across_the_field(self):
        for deg in (0.0, 10.0, 20.0, 30.0):
            centre = _direction(deg) * 0.44
            with self.subTest(deg=deg):
                self.assertLess(self._err(self._cone, centre), 0.1)

    def test_marked_ball(self):
        rs = np.random.RandomState(4)
        for deg in (0.0, 15.0, 25.0):
            q = rs.normal(size=4)
            q /= np.linalg.norm(q)
            w, x, y, z = q
            R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                          [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                          [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
            centre = _direction(deg, 200.0) * 0.43
            with self.subTest(deg=deg):
                self.assertLess(self._err(self._cone, centre, ink=True, R=R), 0.2)

    def test_marked_ball_with_a_dim_lower_limb(self):
        # the real ball: IR from above, the lower limb at ~30 % brightness, so
        # a dark mark's edge out-crisps the limb (2026-11-21 static pair: the
        # outermost-strong-edge rule took mark edges, centre 3.8 px off)
        rs = np.random.RandomState(9)
        for k in range(6):
            q = rs.normal(size=4)
            q /= np.linalg.norm(q)
            w, x, y, z = q
            R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                          [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                          [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
            centre = _direction(8.0 + 3 * k, 100.0 + 40 * k) * 0.44
            img = render_ball(self.m, self.k, self.d, centre, R, ball_grey=200, ink_grey=40,
                              background=15, oversample=4, gradient=((0.0, 1.0), 0.3))
            u, v, r = self._seed(centre)
            fit = self._cone(img, u, v, r)
            with self.subTest(pose=k):
                self.assertIsNotNone(fit)
                self.assertLess(float(np.hypot(*(np.array(fit[:2]) - self._truth_px(centre)))), 0.3)
                alpha = np.arcsin(R_M / np.linalg.norm(centre))
                self.assertAlmostEqual(fit[2] / (self.k[0, 0] * np.tan(alpha)), 1.0, delta=0.03)

    def test_the_circle_fit_is_biased_off_axis(self):
        # pins the error the cone fit removes: projection + distortion
        centre = _direction(20.0) * 0.44
        self.assertGreaterEqual(self._err(frame_analysis.refine_ball, centre), 0.4)

    def test_seed_off_by_four_pixels(self):
        centre = _direction(12.0) * 0.44
        img = self._render(centre)
        a = self._cone(img, *self._seed(centre))
        b = self._cone(img, *self._seed(centre, (4.0, -3.0)))
        self.assertLess(float(np.hypot(a[0] - b[0], a[1] - b[1])), 0.05)

    def test_ball_cut_by_the_image_edge(self):
        # centre 20 px inside the right edge: about half the outline is off-image
        fx, cx, cy = self.k[0, 0], self.k[0, 2], self.k[1, 2]
        z = 0.44
        und = cv2.undistortPoints(np.array([[[1259.0, cy]]]), self.k, self.d).reshape(2)
        centre = np.array([und[0] * z, und[1] * z, z])
        img = self._render(centre)
        u, v, r = self._seed(centre)
        fit = self._cone(img, u, v, r)
        if fit is not None:
            self.assertLess(float(np.hypot(*(np.array(fit[:2]) - self._truth_px(centre)))), 0.3)

    def test_cone_refiner_has_the_ball_pair_signature(self):
        refine = sphere_fit.cone_refiner(self.k, self.d)
        centre = _direction(5.0) * 0.44
        self.assertLess(self._err(refine, centre), 0.1)

    def test_radius_is_the_cone_radius(self):
        centre = _direction(0.0) * 0.44
        img = self._render(centre)
        fit = self._cone(img, *self._seed(centre))
        alpha = np.arcsin(R_M / 0.44)
        self.assertAlmostEqual(fit[2], self.k[0, 0] * np.tan(alpha), delta=0.3)


if __name__ == "__main__":
    unittest.main()
