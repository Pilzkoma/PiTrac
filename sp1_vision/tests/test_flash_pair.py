"""The flash capture's image arithmetic (the hardware part runs on the device)."""

import unittest
from unittest import mock

import numpy as np

from sp1_vision import flash_pair
from sp1_vision import strobe_capture


class DifferenceImage(unittest.TestCase):
    def test_brightest_part_stretched_to_220(self):
        ambient = np.full((100, 100), 30, np.uint8)
        flash = ambient.copy()
        flash[40:60, 40:60] = 90     # +60 on the ball
        d = flash_pair.difference_image(flash, ambient)
        self.assertEqual(int(d[50, 50]), 220)
        self.assertEqual(int(d[0, 0]), 0)

    def test_black_difference_does_not_divide_by_zero(self):
        a = np.full((10, 10), 50, np.uint8)
        self.assertEqual(int(flash_pair.difference_image(a, a).max()), 0)


class Unlit(unittest.TestCase):
    def test_threshold(self):
        t = strobe_capture.LIT_THRESHOLD
        self.assertEqual(flash_pair.unlit_cameras({1: t + 1, 2: t - 1}), [2])
        self.assertEqual(flash_pair.unlit_cameras({1: t, 2: t}), [])


class LitFrame(unittest.TestCase):
    def test_brightest_frame_after_the_fire_against_the_median_before(self):
        dark = np.full((20, 20), 30, np.uint8)
        lit = np.full((20, 20), 90, np.uint8)
        t_fire = 1.0
        frames = [(0, 0.5 + 0.05 * i, dark) for i in range(5)]       # all before t_fire - 0.05
        frames += [(0, 1.01, dark), (0, 1.02, lit)]
        with mock.patch.object(strobe_capture, "decode", lambda b: b):
            flash, ambient, rise = flash_pair.lit_frame(frames, t_fire)
        self.assertEqual(int(flash[0, 0]), 90)
        self.assertEqual(int(ambient[0, 0]), 30)
        self.assertAlmostEqual(rise, 60.0)

    def test_too_few_frames_before_the_flash(self):
        frames = [(0, 0.99, np.zeros((4, 4), np.uint8))]
        with mock.patch.object(strobe_capture, "decode", lambda b: b):
            with self.assertRaises(RuntimeError):
                flash_pair.lit_frame(frames, 1.0)


if __name__ == "__main__":
    unittest.main()
