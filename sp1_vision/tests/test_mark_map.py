import unittest

import numpy as np

from sp1_vision import mark_map, stereo_geometry
from sp1_vision.tests.render_ball import render_ball


def rotation_taking(a, b):
    """Proper rotation taking unit vector a onto unit vector b."""
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    v = np.cross(a, b)
    c = float(a @ b)
    if c < -1 + 1e-9:  # antiparallel: half turn about any perpendicular axis
        axis = np.cross(a, [1.0, 0.0, 0.0])
        if np.linalg.norm(axis) < 1e-6:
            axis = np.cross(a, [0.0, 1.0, 0.0])
        axis /= np.linalg.norm(axis)
        return 2.0 * np.outer(axis, axis) - np.eye(3)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx / (1.0 + c)


class MarkMapTest(unittest.TestCase):
    def test_sites_and_shapes(self):
        m = mark_map.load_map()
        self.assertEqual(m.normals.shape, (20, 3))
        self.assertEqual([m.shapes.count(s) for s in ("dot", "bar", "cross")], [5, 10, 5])
        np.testing.assert_allclose(np.linalg.norm(m.normals, axis=1), 1, atol=1e-9)

    def test_directions_tangent(self):
        m = mark_map.load_map()
        for i, s in enumerate(m.shapes):
            if s != "dot":
                self.assertAlmostEqual(float(m.directions[i] @ m.normals[i]), 0, places=9)
                self.assertAlmostEqual(float(np.linalg.norm(m.directions[i])), 1, places=9)
            else:
                self.assertEqual(float(np.linalg.norm(m.directions[i])), 0.0)

    def test_ink_areas(self):
        a = mark_map.load_map().ink_area_mm2
        self.assertAlmostEqual(a["dot"], 38.0, delta=0.6)     # 32-gon of 7 mm, x 0.995^2
        self.assertAlmostEqual(a["bar"], 38.1, delta=0.3)     # 11 x 3.5
        self.assertAlmostEqual(a["cross"], 57.2, delta=0.3)   # 2 x 10 x 3.5 - 3.5^2

    def test_neighbour_angle(self):
        self.assertAlmostEqual(mark_map.load_map().neighbour_angle_deg, 41.81, delta=0.05)

    def test_renderer_puts_ink_at_the_site(self):
        m = mark_map.load_map()
        rig = stereo_geometry.load_rig()
        k, d = rig.k1, rig.d1
        centre = np.array([0.02, -0.01, 0.45])
        site = 0
        # site normal towards the camera (-Z); other sites sit around it
        r_face = rotation_taking(m.normals[site], np.array([0.0, 0.0, -1.0]))
        img = render_ball(m, k, d, centre, r_face)
        u = int(round(k[0, 2] + k[0, 0] * centre[0] / centre[2]))
        v = int(round(k[1, 2] + k[1, 1] * centre[1] / centre[2]))
        self.assertLess(int(img[v, u]), 90)               # ink at the site
        rpx = k[0, 0] * mark_map.BALL_RADIUS_MM / 1000.0 / centre[2]
        self.assertLess(int(img[5, 5]), 30)               # outside the ball
        # the ink blob has the area the map says, within edge blur
        ink_px = int(np.count_nonzero(img[v - 15:v + 16, u - 15:u + 16] < 120))
        px_per_mm = k[0, 0] / centre[2] / 1000.0
        expect = m.ink_area_mm2[m.shapes[site]] * px_per_mm ** 2
        self.assertAlmostEqual(ink_px / expect, 1.0, delta=0.3)
        self.assertGreater(rpx, 30)

    def test_renderer_options_run(self):
        m = mark_map.load_map()
        rig = stereo_geometry.load_rig()
        centre = np.array([0.0, 0.0, 0.45])
        r = np.eye(3)
        img = render_ball(m, rig.k1, rig.d1, centre, r, gradient=((1, 0), 0.4),
                          glint=(np.array([0.2, 0.0, -1.0]), 1.5),
                          line=(np.array([0, 0.3, -1.0]), np.array([0.5, 0, -1.0]), 1.0, 90))
        self.assertEqual(img.dtype, np.uint8)
        self.assertEqual(img.shape, (800, 1280))
        # ball partly off the frame must not crash
        render_ball(m, rig.k1, rig.d1, np.array([-0.2, 0.0, 0.45]), r)

    # --- orientation and handedness: R is fully determined (facing + a roll) ---

    def _scene(self, site, roll_deg=30.0):
        m = mark_map.load_map()
        rig = stereo_geometry.load_rig()
        k = rig.k1
        centre = np.array([0.01, 0.005, 0.45])
        t = np.radians(roll_deg)
        rz = np.array([[np.cos(t), -np.sin(t), 0], [np.sin(t), np.cos(t), 0], [0, 0, 1.0]])
        r = rz @ rotation_taking(m.normals[site], np.array([0.0, 0.0, -1.0]))
        img = render_ball(m, k, rig.d1, centre, r)
        return m, k, centre, r, img

    @staticmethod
    def _project(k, centre, vec_cam, scale_m=0.0):
        p = centre + scale_m * vec_cam
        return np.array([k[0, 2] + k[0, 0] * p[0] / p[2], k[1, 2] + k[1, 1] * p[1] / p[2]])

    def _ink_xy(self, img, uv, radius):
        ys, xs = np.nonzero(img < 120)
        keep = (xs - uv[0]) ** 2 + (ys - uv[1]) ** 2 < radius ** 2
        return np.stack([xs[keep], ys[keep]], axis=1).astype(float)

    @staticmethod
    def _angle_err(a, b, period):
        d = (a - b) % period
        return min(d, period - d)

    def test_bar_axis_matches_direction(self):
        m, k, centre, r, _ = self._scene(0)
        bars = [i for i, s in enumerate(m.shapes) if s == "bar"]
        for site in bars[:3]:
            m, k, centre, r, img = self._scene(site)
            uv = self._project(k, centre, r @ m.normals[site], mark_map.BALL_RADIUS_MM / 1000.0)
            pts = self._ink_xy(img, uv, 14)
            self.assertGreater(len(pts), 20)
            c = pts - pts.mean(axis=0)
            w, v = np.linalg.eigh(c.T @ c)
            got = np.degrees(np.arctan2(v[1, 1], v[0, 1]))
            d = r @ m.directions[site]
            want = np.degrees(np.arctan2(d[1], d[0]))
            self.assertLess(self._angle_err(got, want, 180.0), 5.0)

    def test_cross_arms_match_east(self):
        m = mark_map.load_map()
        for site in [i for i, s in enumerate(m.shapes) if s == "cross"][:2]:
            m, k, centre, r, img = self._scene(site)
            uv = self._project(k, centre, r @ m.normals[site], mark_map.BALL_RADIUS_MM / 1000.0)
            pts = self._ink_xy(img, uv, 14) - uv
            rad = np.hypot(pts[:, 0], pts[:, 1])
            pts = pts[rad > 3]
            phase = np.angle(np.mean(np.exp(4j * np.arctan2(pts[:, 1], pts[:, 0]))))
            got = np.degrees(phase) / 4.0
            e = r @ m.east[site]
            want = np.degrees(np.arctan2(e[1], e[0]))
            self.assertLess(self._angle_err(got, want, 90.0), 5.0)

    def test_neighbours_land_where_the_pose_predicts(self):
        # handedness: a mirrored or transposed pose puts neighbours on the wrong side
        for site in (0, 5):
            m, k, centre, r, img = self._scene(site)
            for j in m.neighbours[site]:
                n_cam = r @ m.normals[j]
                uv = self._project(k, centre, n_cam, mark_map.BALL_RADIUS_MM / 1000.0)
                pts = self._ink_xy(img, uv, 12)
                self.assertGreater(len(pts), 15)
                self.assertLess(float(np.linalg.norm(pts.mean(axis=0) - uv)), 5.0)


if __name__ == "__main__":
    unittest.main()
