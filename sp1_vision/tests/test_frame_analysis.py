"""Pure frame maths - no cameras involved."""

import os
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


class FindBoardTest(unittest.TestCase):
    # A real IMX296 capture of the calibration board, shipped with PiTrac.
    FIXTURE = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "Software", "CalibrateCameraDistortions",
        "checkerboard_test_image_for_undistortion.png",
    )

    def test_finds_board_in_a_real_capture(self):
        img = cv2.imread(self.FIXTURE, cv2.IMREAD_GRAYSCALE)
        self.assertIsNotNone(img, "fixture not readable: " + self.FIXTURE)
        found, corners = frame_analysis.find_board(img)
        self.assertTrue(found)
        expected = frame_analysis.CHESSBOARD_SIZE[0] * frame_analysis.CHESSBOARD_SIZE[1]
        self.assertEqual(corners.shape[0], expected)

    def test_refinement_moves_corners_but_only_slightly(self):
        img = cv2.imread(self.FIXTURE, cv2.IMREAD_GRAYSCALE)
        _, coarse = frame_analysis.find_board(img, refine=False)
        _, fine = frame_analysis.find_board(img, refine=True)
        shift = np.linalg.norm(fine - coarse, axis=2).max()
        self.assertGreater(shift, 0.0, "cornerSubPix result was discarded")
        self.assertLess(shift, 5.0, "refinement moved a corner implausibly far")

    def test_no_board_in_a_flat_image(self):
        flat = np.full((800, 1280), 128, dtype=np.uint8)
        found, corners = frame_analysis.find_board(flat)
        self.assertFalse(found)
        self.assertIsNone(corners)

    def test_finds_board_in_colour_input(self):
        # The capture path yields CV_8UC3 BGR - OpenCV decodes MJPEG to
        # three channels regardless of the sensor being mono.
        gray = cv2.imread(self.FIXTURE, cv2.IMREAD_GRAYSCALE)
        colour = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        found_gray, corners_gray = frame_analysis.find_board(gray)
        found_colour, corners_colour = frame_analysis.find_board(colour)
        self.assertTrue(found_colour)
        expected = frame_analysis.CHESSBOARD_SIZE[0] * frame_analysis.CHESSBOARD_SIZE[1]
        self.assertEqual(corners_colour.shape[0], expected)
        np.testing.assert_allclose(corners_colour, corners_gray, atol=1e-6)


def _frame_with_discs(*discs):
    """A dark frame with bright discs at (cx, cy, r)."""
    frame = np.zeros((800, 1280), dtype=np.uint8)
    for cx, cy, r in discs:
        cv2.circle(frame, (cx, cy), r, 255, -1)
    return cv2.GaussianBlur(frame, (5, 5), 0)


class BallCandidatesTest(unittest.TestCase):
    """Every circle in the frame, not the strongest one.

    Returning a single circle put the whole decision inside one image, where
    nothing distinguishes a golf ball from a loudspeaker cone. It cost a
    24-shot run: in 17 of those the detector returned the same pixel in
    every frame, because a bright object in the background outscored the
    ball and never moved.

    The division of labour is deliberate. This function is permissive - it
    is allowed to hand back a loudspeaker, a lamp and a plant pot - and the
    stereo pair selection is where precision comes from, because that is
    where the geometry lives.
    """

    def test_returns_a_lone_circle_near_its_true_centre(self):
        found = frame_analysis.ball_candidates(_frame_with_discs((700, 520, 38)))
        self.assertGreaterEqual(len(found), 1)
        u, v, r = found[0]
        self.assertAlmostEqual(u, 700, delta=4)
        self.assertAlmostEqual(v, 520, delta=4)
        self.assertAlmostEqual(r, 38, delta=6)

    def test_returns_every_circle_not_only_the_strongest(self):
        # The property the single-circle version could not have. A big
        # bright disc and a smaller one: both must come back, so that
        # something downstream can decide which is the ball.
        found = frame_analysis.ball_candidates(
            _frame_with_discs((300, 250, 62), (900, 600, 30)))
        self.assertGreaterEqual(len(found), 2)
        for want in ((300, 250), (900, 600)):
            self.assertTrue(
                any(abs(u - want[0]) < 12 and abs(v - want[1]) < 12
                    for u, v, _ in found),
                "no candidate near {}, got {}".format(want, found))

    def test_returns_an_empty_list_when_there_is_nothing(self):
        self.assertEqual(
            frame_analysis.ball_candidates(np.zeros((800, 1280), dtype=np.uint8)),
            [])

    def test_accepts_colour_frames_like_find_board(self):
        gray = _frame_with_discs((640, 400, 30))
        colour = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        self.assertGreaterEqual(len(frame_analysis.ball_candidates(colour)), 1)

    def test_radius_bounds_are_honoured(self):
        found = frame_analysis.ball_candidates(
            _frame_with_discs((700, 520, 38)), min_radius=50, max_radius=70)
        self.assertEqual(found, [])

    def test_every_candidate_is_a_plain_tuple_of_floats(self):
        # The pair selector indexes these and puts them into numpy; numpy
        # scalars leaking through print as "np.float32(700.5)" in the
        # operator's failure messages.
        for candidate in frame_analysis.ball_candidates(
                _frame_with_discs((700, 520, 38))):
            self.assertEqual(len(candidate), 3)
            for value in candidate:
                self.assertIsInstance(value, float)


if __name__ == "__main__":
    unittest.main()
