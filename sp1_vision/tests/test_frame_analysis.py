"""Pure frame maths - no cameras involved."""

import os
import unittest
from unittest import mock

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


def _shaded_ball(cx, cy, r, background=128, bright=240, dark=120):
    """A ball lit hard from one side, on a mid-grey surface.

    The real failure, reproduced. One flank is brighter than the surface and
    the other is barely distinguishable from it, so one half of the outline
    carries a strong gradient and the other almost none. HoughCircles votes along the gradient direction, and a
    reversed edge votes away from the true centre - which is why it settles
    on the bright arc rather than the silhouette, and why it did so
    differently in the two cameras, where the shading is seen from different
    angles. That difference showed up as 2.71 px of reprojection error on
    frames where the ball was plainly visible in both.

    The defaults are chosen so the fixture actually bites: at these levels
    Hough lands 1.58 px from the centre. On a crisp disc it manages 0.71 px
    - its accumulator quantisation, not a bias - and a test built on that
    would pass whether or not anything was refined.
    """
    frame = np.full((800, 1280), background, dtype=np.uint8)
    yy, xx = np.mgrid[0:frame.shape[0], 0:frame.shape[1]]
    inside = (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r
    ramp = np.clip((cx + r - xx) / (2.0 * r), 0.0, 1.0)
    frame[inside] = (dark + (bright - dark) * ramp)[inside].astype(np.uint8)
    return cv2.GaussianBlur(frame, (5, 5), 0)


def _raw_hough_seed(frame, near_x, near_y):
    """The UNREFINED Hough candidate nearest a point, or None.

    ball_candidates now returns refined circles, so a test that wants to
    show the refinement earns its place has to reach past it for the raw
    proposal - otherwise it compares the refined answer with itself and
    passes no matter what.
    """
    gray = cv2.medianBlur(frame_analysis._as_gray(frame), 5)
    circles = cv2.HoughCircles(
        gray, cv2.HOUGH_GRADIENT, dp=1.0,
        minDist=frame_analysis.CANDIDATE_MIN_SEPARATION_PX, param1=100,
        param2=frame_analysis.CANDIDATE_ACCUMULATOR_THRESHOLD,
        minRadius=frame_analysis.BALL_MIN_RADIUS_PX,
        maxRadius=frame_analysis.BALL_MAX_RADIUS_PX)
    if circles is None:
        return None
    return min(((float(u), float(v), float(r)) for u, v, r in circles[0]),
               key=lambda c: (c[0] - near_x) ** 2 + (c[1] - near_y) ** 2)


class RefineBallTest(unittest.TestCase):
    """Fit the outline, not the brightest arc.

    Half a pixel of centre error is 1.8 mm of depth at the working distance,
    and that is the entire budget the 0.6% baseline question has. Anything
    that moves the centre with the lighting moves the answer with it, so a
    detector that only works in favourable light is not a calibration
    instrument.
    """

    def test_recovers_an_evenly_lit_centre_to_a_fraction_of_a_pixel(self):
        frame = _frame_with_discs((640, 400, 40))
        refined = frame_analysis.refine_ball(frame, 643.0, 396.0, 38.0)
        self.assertIsNotNone(refined)
        u, v, r = refined
        self.assertAlmostEqual(u, 640.0, delta=0.8)
        self.assertAlmostEqual(v, 400.0, delta=0.8)
        self.assertAlmostEqual(r, 40.0, delta=1.5)

    def test_a_one_sided_light_no_longer_pulls_the_centre(self):
        # The test this whole change exists for. The refinement must land on
        # the true centre, AND it must beat the seed - otherwise the fixture
        # is not exercising the bias and the test proves nothing.
        frame = _shaded_ball(700, 520, 44)
        raw = _raw_hough_seed(frame, 700, 520)
        self.assertIsNotNone(raw, "the shaded ball produced no candidate at all")
        refined = frame_analysis.refine_ball(frame, *raw)
        self.assertIsNotNone(refined)

        raw_error = np.hypot(raw[0] - 700, raw[1] - 520)
        fine_error = np.hypot(refined[0] - 700, refined[1] - 520)
        self.assertLess(fine_error, 0.6,
                        "refined centre off by {:.2f} px".format(fine_error))
        self.assertLess(fine_error, raw_error,
                        "refinement did not improve on Hough ({:.2f} -> {:.2f} px)"
                        .format(raw_error, fine_error))

    def test_converges_from_a_seed_several_pixels_off(self):
        frame = _frame_with_discs((500, 300, 35))
        refined = frame_analysis.refine_ball(frame, 506.0, 294.0, 30.0)
        self.assertIsNotNone(refined)
        self.assertAlmostEqual(refined[0], 500.0, delta=0.8)
        self.assertAlmostEqual(refined[1], 300.0, delta=0.8)

    def test_refuses_when_there_is_no_outline_to_fit(self):
        flat = np.full((800, 1280), 128, dtype=np.uint8)
        self.assertIsNone(frame_analysis.refine_ball(flat, 640.0, 400.0, 40.0))

    def test_refuses_rather_than_wandering_onto_a_neighbour(self):
        # A seed far from anything must not slide across the frame and
        # report some other object's outline as this candidate's.
        frame = _frame_with_discs((200, 200, 40))
        self.assertIsNone(frame_analysis.refine_ball(frame, 900.0, 600.0, 40.0))

    def test_an_edge_candidate_does_not_crash_on_a_clipped_roi(self):
        frame = _frame_with_discs((30, 770, 25))
        frame_analysis.refine_ball(frame, 30.0, 770.0, 25.0)


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

    # A wiring test for refine_ball belongs here and is deliberately absent:
    # refinement is not on the measuring path yet because it regressed real
    # frames. Its own accuracy tests above stand; this is where the test
    # goes when it earns its way in.

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
