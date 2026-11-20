import unittest

import cv2
import numpy as np

from sp1_vision import ball_unwrap, mark_map, stereo_geometry
from sp1_vision.tests.render_ball import render_ball
from sp1_vision.tests.test_mark_map import rotation_taking


def _angle_deg(a, b):
    c = float(a @ b) / (np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.degrees(np.arccos(np.clip(c, -1.0, 1.0))))


def _dir_at(angle_deg, azimuth_deg=0.0):
    a = np.radians(angle_deg)
    z = np.radians(azimuth_deg)
    return np.array([np.sin(a) * np.cos(z), np.sin(a) * np.sin(z), -np.cos(a)])


class BallUnwrapTest(unittest.TestCase):
    def setUp(self):
        self.m = mark_map.load_map()
        self.rig = stereo_geometry.load_rig()
        self.k, self.d = self.rig.k1, self.rig.d1
        self.centre = np.array([0.0, 0.0, 0.45])

    def test_site_lands_where_predicted(self):
        site = 3
        r = rotation_taking(self.m.normals[site], _dir_at(30.0, 40.0))
        img = render_ball(self.m, self.k, self.d, self.centre, r)
        u = ball_unwrap.unwrap(img, self.k, self.d, self.centre)
        dark = ((u.image < 100) & u.valid).astype(np.uint8)
        # keep the blob nearest the predicted place: label and pick by size
        n, lab, stats, cents = cv2.connectedComponentsWithStats(dark)
        best = None
        for i in range(1, n):
            cx, cy = cents[i]
            nrm = ball_unwrap.normal_at(u, cx - u.centre_px,
                                        cy - u.centre_px)
            err = _angle_deg(nrm, r @ self.m.normals[site])
            if stats[i, cv2.CC_STAT_AREA] > 200 and (best is None or err < best):
                best = err
        self.assertIsNotNone(best)
        self.assertLess(best, 0.5)

    def test_roundtrip_normal(self):
        img = np.full((800, 1280), 100, np.uint8)
        u = ball_unwrap.unwrap(img, self.k, self.d, self.centre)
        rng = np.random.RandomState(1)
        h, w = u.image.shape
        for _ in range(20):
            th = rng.uniform(1.0, 60.0)
            ph = rng.uniform(0, 2 * np.pi)
            x = np.radians(th) * ball_unwrap.R_OUT_PX * np.cos(ph)
            y = np.radians(th) * ball_unwrap.R_OUT_PX * np.sin(ph)
            n = ball_unwrap.normal_at(u, x, y)
            self.assertAlmostEqual(np.linalg.norm(n), 1.0, places=9)
            self.assertAlmostEqual(_angle_deg(n, u.basis[0]), th, delta=0.05)

    def test_axes_reach_max_deg(self):
        img = np.full((800, 1280), 100, np.uint8)
        u = ball_unwrap.unwrap(img, self.k, self.d, self.centre)
        c = u.centre_px
        self.assertEqual(u.image.shape, (2 * c + 1, 2 * c + 1))
        for deg in (60, 65, 68):
            off = int(round(ball_unwrap.R_OUT_PX * np.radians(deg)))
            for dx, dy in ((off, 0), (-off, 0), (0, off), (0, -off)):
                self.assertTrue(u.valid[c + dy, c + dx], (deg, dx, dy))
        self.assertAlmostEqual(u.theta_deg[c, c], 0.0)

    def test_mark_at_60_and_68_on_axis(self):
        site = 3
        for deg in (60.0, 68.0):
            # e1 is camera x for a centred ball: azimuth 0 is the +x axis
            r = rotation_taking(self.m.normals[site], _dir_at(deg, 0.0))
            img = render_ball(self.m, self.k, self.d, self.centre, r)
            u = ball_unwrap.unwrap(img, self.k, self.d, self.centre)
            c = u.centre_px
            off = int(round(ball_unwrap.R_OUT_PX * np.radians(deg)))
            patch = u.image[c - 6:c + 7, c + off - 6:c + off + 7]
            self.assertTrue(u.valid[c, c + off])
            self.assertLess(int(patch.min()), 100, deg)   # ink present, not cut off

    def test_tangent_is_tangent(self):
        img = np.full((800, 1280), 100, np.uint8)
        u = ball_unwrap.unwrap(img, self.k, self.d, self.centre)
        n = ball_unwrap.normal_at(u, 30.0, 20.0)
        t = ball_unwrap.tangent_at(u, 30.0, 20.0, 1.0, 0.0)
        self.assertAlmostEqual(float(n @ t), 0.0, places=9)
        self.assertAlmostEqual(float(np.linalg.norm(t)), 1.0, places=9)

    def _bar_width_mm(self, angle):
        site = [i for i, s in enumerate(self.m.shapes) if s == "bar"][0]
        r = rotation_taking(self.m.normals[site], _dir_at(angle, 25.0))
        img = render_ball(self.m, self.k, self.d, self.centre, r)
        u = ball_unwrap.unwrap(img, self.k, self.d, self.centre)
        # the bar's own pixel, from the predicted normal
        nrm = r @ self.m.normals[site]
        dark = ((u.image < 100) & u.valid).astype(np.uint8)
        n, lab, stats, cents = cv2.connectedComponentsWithStats(dark)
        h, w = u.image.shape
        pick = None
        for i in range(1, n):
            cx, cy = cents[i]
            e = _angle_deg(ball_unwrap.normal_at(u, cx - u.centre_px, cy - u.centre_px), nrm)
            if e < 5.0 and stats[i, cv2.CC_STAT_AREA] > 100:
                pick = i
        self.assertIsNotNone(pick)
        pts = np.column_stack(np.nonzero(lab == pick))[:, ::-1].astype(np.float32)
        (_, _), (a, b), _ = cv2.minAreaRect(pts)
        return min(a, b) / ball_unwrap.PX_PER_MM

    def test_widths_equal_at_centre_and_limb(self):
        for angle in (5.0, 55.0):
            self.assertAlmostEqual(self._bar_width_mm(angle), 3.5, delta=0.4,
                                   msg="angle %s" % angle)

    def test_out_of_frame_is_invalid(self):
        k = self.k
        rpx = k[0, 0] * mark_map.BALL_RADIUS_MM / 1000.0 / 0.45
        # centre 20 px inside the right edge
        u_px = 1280 - 20
        x = (u_px - k[0, 2]) * 0.45 / k[0, 0]
        centre = np.array([x, 0.0, 0.45])
        img = render_ball(self.m, k, self.d, centre, np.eye(3))
        u = ball_unwrap.unwrap(img, k, self.d, centre)
        self.assertGreater(rpx, 40)
        h, w = u.image.shape
        # where is the source of each unwrapped pixel? re-project it here
        ys, xs = np.mgrid[0:h, 0:w]
        outside = np.zeros((h, w), bool)
        for yy in range(0, h, 7):
            for xx in range(0, w, 7):
                if not u.valid[yy, xx]:
                    continue
                n = ball_unwrap.normal_at(u, xx - u.centre_px, yy - u.centre_px)
                p = centre + mark_map.BALL_RADIUS_MM / 1000.0 * n
                uv, _ = cv2.projectPoints(p.reshape(1, 1, 3), np.zeros(3), np.zeros(3), k, self.d)
                if uv[0, 0, 0] > 1280 - 3:
                    outside[yy, xx] = True
        self.assertFalse(outside.any())
        # and a real part of the cap is invalid because of the frame
        self.assertGreater(np.count_nonzero(~u.valid & (u.theta_deg <= ball_unwrap.MAX_DEG)), 500)
        self.assertTrue(np.all(u.image[~u.valid] == 0))

    def test_centre_from_circle(self):
        centre = np.array([0.05, 0.08, 0.45])
        k = self.k
        uv = cv2.projectPoints(centre.reshape(1, 1, 3), np.zeros(3), np.zeros(3),
                               k, self.d)[0].reshape(2)
        from sp1_vision import ball_pair
        rpx = ball_pair.apparent_radius_px(k[0, 0], np.linalg.norm(centre))
        est = ball_unwrap.centre_from_circle(k, self.d, uv, rpx)
        self.assertLess(float(np.linalg.norm(est - centre)), 0.003)


if __name__ == "__main__":
    unittest.main()
