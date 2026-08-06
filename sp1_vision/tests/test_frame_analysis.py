"""Pure frame maths - no cameras involved."""

import unittest

import cv2
import numpy as np

from sp1_vision import frame_analysis


def _synthetic_checkerboard(square=40, rows=20, cols=32):
    """High-contrast edges, i.e. something a focus metric should score high."""
    img = np.zeros((rows * square, cols * square), dtype=np.uint8)
    for r in range(rows):
        for c in range(cols):
            if (r + c) % 2 == 0:
                img[r * square:(r + 1) * square, c * square:(c + 1) * square] = 255
    return img


class SharpnessScoreTest(unittest.TestCase):
    def test_sharp_image_scores_higher_than_blurred(self):
        sharp = _synthetic_checkerboard()
        blurred = cv2.GaussianBlur(sharp, (31, 31), 0)
        self.assertGreater(
            frame_analysis.sharpness_score(sharp),
            frame_analysis.sharpness_score(blurred) * 10,
        )

    def test_flat_image_scores_near_zero(self):
        flat = np.full((800, 1280), 128, dtype=np.uint8)
        self.assertLess(frame_analysis.sharpness_score(flat), 1.0)

    def test_accepts_colour_input(self):
        # The capture path yields CV_8UC3 BGR; the metric must not care.
        sharp = _synthetic_checkerboard()
        colour = cv2.cvtColor(sharp, cv2.COLOR_GRAY2BGR)
        self.assertAlmostEqual(
            frame_analysis.sharpness_score(colour),
            frame_analysis.sharpness_score(sharp),
            delta=1.0,
        )

    def test_roi_fraction_restricts_to_centre(self):
        # Sharp centre, flat surround: a centre ROI must score far higher
        # than the whole frame.
        img = np.full((800, 1280), 128, dtype=np.uint8)
        patch = _synthetic_checkerboard(square=10, rows=20, cols=20)
        img[300:500, 540:740] = patch
        whole = frame_analysis.sharpness_score(img, roi_fraction=1.0)
        centre = frame_analysis.sharpness_score(img, roi_fraction=0.25)
        self.assertGreater(centre, whole)


if __name__ == "__main__":
    unittest.main()
