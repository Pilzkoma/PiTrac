"""render_ball's oversampling: an area-weighted edge for subpixel ground truth."""

import unittest

import numpy as np

from sp1_vision import mark_map, stereo_geometry
from sp1_vision.mark_map import BALL_RADIUS_MM
from sp1_vision.tests.render_ball import render_ball

BG, BALL = 15.0, 200.0


class RenderBallOversample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = mark_map.load_map()
        rig = stereo_geometry.load_rig()
        cls.k, cls.d = rig.k1, rig.d1
        cls.R = np.eye(3)

    def _plain(self, centre, dist, oversample):
        # ink drawn in the background grey: a plain ball without marks
        return render_ball(self.m, self.k, dist, centre, self.R, ball_grey=BALL,
                           ink_grey=BALL, background=BG, oversample=oversample)

    def test_default_is_unchanged(self):
        centre = np.array([0.02, -0.01, 0.45])
        a = render_ball(self.m, self.k, self.d, centre, self.R)
        b = render_ball(self.m, self.k, self.d, centre, self.R, oversample=1)
        self.assertTrue(np.array_equal(a, b))

    def test_oversampled_area_matches_the_projected_disc(self):
        z = 0.44
        img = self._plain(np.array([0.0, 0.0, z]), np.zeros(5), 4).astype(float)
        area_px = (img - BG).sum() / (BALL - BG)
        # exact silhouette of a sphere on the axis: a circle of radius
        # f tan(asin(r / z))
        alpha = np.arcsin(BALL_RADIUS_MM / 1000.0 / z)
        fx, fy = self.k[0, 0], self.k[1, 1]
        expected = np.pi * fx * fy * np.tan(alpha) ** 2
        self.assertAlmostEqual(area_px / expected, 1.0, delta=0.01)

    def test_oversampled_centroid_is_the_circle_centre_on_axis(self):
        img = self._plain(np.array([0.0, 0.0, 0.44]), np.zeros(5), 4).astype(float)
        wgt = img - BG
        ys, xs = np.mgrid[0:img.shape[0], 0:img.shape[1]]
        u = (wgt * xs).sum() / wgt.sum()
        v = (wgt * ys).sum() / wgt.sum()
        self.assertAlmostEqual(u, self.k[0, 2], delta=0.02)
        self.assertAlmostEqual(v, self.k[1, 2], delta=0.02)

    def test_oversampling_softens_the_edge(self):
        centre = np.array([0.0, 0.0, 0.44])
        hard = self._plain(centre, np.zeros(5), 1)
        soft = self._plain(centre, np.zeros(5), 4)
        # more distinct grey levels on the rim than the blurred binary edge
        self.assertGreater(len(np.unique(soft)), len(np.unique(hard)))


if __name__ == "__main__":
    unittest.main()
