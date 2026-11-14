"""The ball's mark map: sites, neighbours, shapes, stencil geometry."""

import os
import tempfile
import unittest

import numpy as np

from sp1_vision import ball_marks as bm


class Sites(unittest.TestCase):
    def test_twenty_unit_vectors_vertex_up(self):
        s = bm.dodecahedron_sites()
        self.assertEqual(s.shape, (20, 3))
        np.testing.assert_allclose(np.linalg.norm(s, axis=1), 1.0, atol=1e-12)
        np.testing.assert_allclose(s[0], [0, 0, 1], atol=1e-12)
        heights = np.round(np.abs(s[:, 2]), 3).tolist()
        self.assertEqual((heights.count(1.0), heights.count(0.745), heights.count(0.333)), (2, 6, 12))
        self.assertEqual(int((s[:, 2] > 0).sum()), 10)
        self.assertAlmostEqual(float(np.min(np.abs(s[:, 2]))), 1 / 3, places=6)

    def test_three_neighbours_at_the_edge_angle(self):
        s = bm.dodecahedron_sites()
        nb = bm.neighbours(s)
        edge = np.degrees(np.arccos(np.sqrt(5) / 3))      # 41.81 deg
        for i, trio in enumerate(nb):
            self.assertEqual(len(set(trio)), 3)
            for j in trio:
                self.assertAlmostEqual(np.degrees(np.arccos(np.clip(s[i] @ s[j], -1, 1))), edge, places=6)
                self.assertIn(i, nb[j])

    def test_neighbours_run_counter_clockwise_from_outside(self):
        s = bm.dodecahedron_sites()
        for i, (a, b, c) in enumerate(bm.neighbours(s)):
            for p, q in ((a, b), (b, c), (c, a)):
                # (p - n) x (q - n) points outward for CCW seen from outside
                self.assertGreater(np.cross(s[p] - s[i], s[q] - s[i]) @ s[i], 0)

    def test_tangent_frame_is_right_handed_and_tangent(self):
        for n in bm.dodecahedron_sites():
            north, east = bm.tangent_frame(n)
            self.assertAlmostEqual(float(north @ n), 0, places=12)
            self.assertAlmostEqual(float(east @ n), 0, places=12)
            np.testing.assert_allclose(np.cross(east, north), n, atol=1e-12)


if __name__ == "__main__":
    unittest.main()
