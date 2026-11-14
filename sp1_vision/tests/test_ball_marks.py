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


class Signatures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = bm.dodecahedron_sites()
        cls.nb = bm.neighbours(cls.s)
        cls.marks = bm.assign_marks(seed=0)

    def test_every_v_signature_is_unique(self):
        sigs = [sig for _, _, _, sig in bm.all_v_signatures(self.marks, self.nb)]
        self.assertEqual(len(sigs), 60)
        self.assertEqual(len(set(sigs)), 60)

    def test_shapes_are_balanced_and_bars_point_at_neighbours(self):
        shapes = [m.shape for m in self.marks]
        for kind in ("dot", "bar", "cross"):
            self.assertGreaterEqual(shapes.count(kind), 5)
        for m in self.marks:
            if m.shape == "bar":
                self.assertIn(m.bar_to, self.nb[m.site])
            else:
                self.assertIsNone(m.bar_to)

    def test_relative_symbols_name_the_bar_direction(self):
        bar = next(m for m in self.marks if m.shape == "bar")
        n1, n2, n3 = self.nb[bar.site]
        target = bar.bar_to
        k = self.nb[bar.site].index(target)
        nxt = self.nb[bar.site][(k + 1) % 3]
        prv = self.nb[bar.site][(k + 2) % 3]
        self.assertEqual(bm.relative_symbol(self.marks, self.nb, bar.site, target), "bar0")
        self.assertEqual(bm.relative_symbol(self.marks, self.nb, bar.site, prv), "bar+")
        self.assertEqual(bm.relative_symbol(self.marks, self.nb, bar.site, nxt), "bar-")

    def test_the_search_is_deterministic(self):
        self.assertEqual(bm.assign_marks(seed=0), self.marks)

    def test_a_mirrored_ball_does_not_read_the_same(self):
        # mirror x -> -x: neighbour order flips; at least one V must change
        mirrored = self.s * np.array([-1, 1, 1])
        nb_m = bm.neighbours(mirrored)
        sigs = {sig for _, _, _, sig in bm.all_v_signatures(self.marks, self.nb)}
        sigs_m = {sig for _, _, _, sig in bm.all_v_signatures(self.marks, nb_m)}
        self.assertNotEqual(sigs, sigs_m)


if __name__ == "__main__":
    unittest.main()
