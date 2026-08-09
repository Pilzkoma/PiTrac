"""Triangulation against synthetic geometry, where truth is known exactly.

Testing against real images would confound the arithmetic with detection
error. Here a known 3D point is projected into two known cameras and must
come back.
"""

import unittest

import cv2
import numpy as np

from sp1_vision import stereo_geometry, triangulate


def make_rig(camera2_centre_m=(-0.07872, 0.0, 0.0), pitch_deg=0.0,
             distortion=None):
    """A rig with camera 2 placed where we say, in camera 1's frame.

    Placing the CENTRE rather than T keeps the test readable: T = -R @ centre
    is exactly the conversion the production code has to get right, so
    stating it here in the opposite direction is a genuine cross-check.
    """
    k = np.array([[900.0, 0.0, 640.0],
                  [0.0, 900.0, 400.0],
                  [0.0, 0.0, 1.0]])
    d = np.zeros(5) if distortion is None else np.asarray(distortion, float)
    r, _ = cv2.Rodrigues(np.array([np.radians(pitch_deg), 0.0, 0.0]))
    centre = np.asarray(camera2_centre_m, dtype=float)
    t = -r @ centre
    rig = stereo_geometry.StereoRig(k1=k, d1=d, k2=k, d2=d, r=r, t_m=t)
    # Every test below uses rig.t_m and never camera2_centre_m directly, so
    # a globally inverted T would leave the whole file green. Cross-check
    # here, once, against the production conversion this helper deliberately
    # runs backwards (see the docstring above).
    np.testing.assert_allclose(
        stereo_geometry.camera2_centre_in_camera1(rig), centre, atol=1e-12)
    return rig


def project(rig, xyz):
    """Where a camera-1-frame point lands in each image."""
    xyz = np.asarray(xyz, dtype=float).reshape(1, 3)
    zero = np.zeros(3)
    uv1, _ = cv2.projectPoints(xyz, zero, zero, rig.k1, rig.d1)
    rvec, _ = cv2.Rodrigues(rig.r)
    uv2, _ = cv2.projectPoints(xyz, rvec, rig.t_m, rig.k2, rig.d2)
    return uv1.reshape(2), uv2.reshape(2)


class TriangulateTest(unittest.TestCase):
    def test_recovers_a_known_point_exactly(self):
        rig = make_rig()
        truth = np.array([0.05, 0.0937, 0.500])
        xyz = triangulate.triangulate_point(rig, *project(rig, truth))
        np.testing.assert_allclose(xyz, truth, atol=1e-9)

    def test_recovers_a_known_point_through_lens_distortion(self):
        rig = make_rig(distortion=[0.0086, -0.0060, 0.0021, -0.0024, -0.0880])
        truth = np.array([-0.08, 0.05, 0.42])
        xyz = triangulate.triangulate_point(rig, *project(rig, truth))
        np.testing.assert_allclose(xyz, truth, atol=1e-7)

    def test_recovers_a_known_point_with_the_pair_rotated(self):
        rig = make_rig(pitch_deg=-0.94)
        truth = np.array([0.02, 0.09, 0.65])
        xyz = triangulate.triangulate_point(rig, *project(rig, truth))
        np.testing.assert_allclose(xyz, truth, atol=1e-9)

    def test_depth_is_positive_for_a_point_in_front(self):
        # A swapped pair or an inverted T produces mirrored depth with
        # nothing else visibly wrong. Depth sign is the cheapest guard.
        rig = make_rig()
        xyz = triangulate.triangulate_point(rig, *project(rig, [0.0, 0.0, 0.5]))
        self.assertGreater(xyz[2], 0.0)

    def test_swapped_correspondences_show_a_residual_on_a_pitched_rig(self):
        # A rig with R = I and identical K in both cameras is a degenerate
        # choice here: for pure-X translation, swapping which ray is which
        # still satisfies the epipolar constraint exactly (the essential
        # matrix [T]_x is skew-symmetric, so u2^T F u1 = 0 implies
        # u1^T F u2 = 0 too), so the swap lands on a real - just mirrored -
        # intersection with zero reprojection error. The real rig always
        # carries the mount's pitch, so exercise that here. The residual
        # scales roughly as 2*f*theta - see the sibling test below for the
        # R = I case where this guard provides nothing at all.
        rig = make_rig(pitch_deg=-0.94)
        truth = np.array([0.05, 0.0937, 0.500])
        uv1, uv2 = project(rig, truth)
        # Feed the images in the wrong order - a plausible wiring mistake.
        xyz = triangulate.triangulate_point(rig, uv2, uv1)
        e1, e2 = triangulate.reprojection_error(rig, xyz, uv2, uv1)
        self.assertGreater(max(e1, e2), 1.0)

    def test_swapped_correspondences_show_zero_residual_at_r_identity(self):
        # The counter-case to the test above: at R = I the swap is
        # algebraically invisible to reprojection_error (worked by hand in
        # triangulate.py's module docstring: the swapped solution sits at
        # exactly z' = -Z, a real ray intersection, just behind the camera).
        # The residual is not a swap guard here - only the sign of Z is.
        rig = make_rig()
        truth = np.array([0.05, 0.0937, 0.500])
        uv1, uv2 = project(rig, truth)
        xyz = triangulate.triangulate_point(rig, uv2, uv1)
        self.assertLess(xyz[2], 0.0)


class TriangulationErrorTest(unittest.TestCase):
    def test_raises_on_parallel_rays_from_identical_points(self):
        # Feeding the same pixel to both cameras on an R = I rig gives two
        # rays with the same direction, offset only by the baseline - they
        # never meet, which is exactly the degenerate case the function
        # exists to catch rather than silently return nonsense for.
        rig = make_rig()
        uv = np.array([700.0, 450.0])
        with self.assertRaises(triangulate.TriangulationError):
            triangulate.triangulate_point(rig, uv, uv)


class ReprojectionErrorTest(unittest.TestCase):
    def test_a_true_point_reprojects_onto_its_own_measurements(self):
        rig = make_rig()
        truth = np.array([0.05, 0.0937, 0.500])
        uv1, uv2 = project(rig, truth)
        e1, e2 = triangulate.reprojection_error(rig, truth, uv1, uv2)
        self.assertLess(max(e1, e2), 1e-6)

    def test_a_displaced_point_shows_a_residual(self):
        rig = make_rig()
        truth = np.array([0.05, 0.0937, 0.500])
        uv1, uv2 = project(rig, truth)
        e1, e2 = triangulate.reprojection_error(rig, truth + [0.01, 0, 0], uv1, uv2)
        self.assertGreater(max(e1, e2), 1.0)


class DepthSensitivityTest(unittest.TestCase):
    def test_matches_the_hand_computed_figure_for_its_stated_input(self):
        # Z^2 / (b * f) = 0.5087^2 / (0.07872 * 900) = 3.65 mm per pixel.
        #
        # 0.5087 m is NOT our working depth, and this test does not claim it
        # is. It is the straight-line range to a ball centre 500 mm out and
        # 93.7 mm below the axis, and putting a range into a formula that
        # takes a depth is the error the docstring now records. The
        # arithmetic below is correct for the input it states, so it stays
        # as an exact check on the formula; the working-distance figure is
        # 3.53 mm/px at Z = 0.500 m, asserted where the analysis prints it
        # in test_cli_triangulate.
        rig = make_rig()
        self.assertAlmostEqual(
            triangulate.depth_sensitivity_mm_per_px(rig, 0.5087), 3.65, delta=0.05)

    def test_refuses_a_non_positive_depth(self):
        # Z is squared, so a negative depth would come back as a perfectly
        # plausible positive tolerance - the one arithmetic here that can
        # turn a nonsense input into a believable output.
        rig = make_rig()
        for depth in (0.0, -0.5):
            with self.assertRaises(ValueError):
                triangulate.depth_sensitivity_mm_per_px(rig, depth)


# Six positions 70 mm apart, the layout the capture protocol asks for. Used
# by the regression tests below so they all speak about the same series the
# operator actually lays out on the floor.
TAPE_SERIES_M = np.array([0.350, 0.420, 0.490, 0.560, 0.630, 0.700])


class ScaleRegressionTest(unittest.TestCase):
    """Scale from a straight-line fit of triangulated depth against tape.

    This replaces a consecutive-differences estimator, and the reason is not
    stylistic. Least squares through the origin on consecutive differences
    telescopes, for equally spaced positions, to exactly
    (Z_last - Z_first) / (tape_last - tape_first): the four interior
    positions contribute nothing at all. The operator lays out six and six
    should count.

    Fitting with an intercept keeps the property that motivated differences
    in the first place - where camera 1's z = 0 plane sits relative to the
    tape's zero is unknown, and must land in the intercept rather than in
    the scale.
    """

    def test_perfect_agreement_gives_unit_scale_and_no_offset(self):
        fit = triangulate.fit_scale_regression(TAPE_SERIES_M, TAPE_SERIES_M)
        self.assertAlmostEqual(fit.scale, 1.0, places=9)
        self.assertAlmostEqual(fit.offset_m, 0.0, places=9)
        self.assertLess(fit.rms_m, 1e-12)

    def test_recovers_a_known_scale_error(self):
        # 78.28 against 78.749 mm of baseline is 0.6%, and a baseline 0.6%
        # too large makes every triangulated distance 0.6% too large.
        fit = triangulate.fit_scale_regression(TAPE_SERIES_M * 1.006,
                                               TAPE_SERIES_M)
        self.assertAlmostEqual(fit.scale, 1.006, places=9)

    def test_an_unknown_lens_plane_lands_in_the_offset_not_the_scale(self):
        # The tape is read from the unit's front face; Z is measured from
        # camera 1's z = 0 plane, which sits somewhere inside the housing.
        # That constant must not read as a scale error.
        fit = triangulate.fit_scale_regression(TAPE_SERIES_M + 0.137,
                                               TAPE_SERIES_M)
        self.assertAlmostEqual(fit.scale, 1.0, places=9)
        self.assertAlmostEqual(fit.offset_m, 0.137, places=9)

    def test_the_interior_positions_move_the_answer(self):
        # The defect in the consecutive-differences estimator, stated as a
        # property: two series with IDENTICAL endpoints and different
        # interiors must not fit the same scale. The old estimator returned
        # the same number for both, because it only ever saw the endpoints.
        straight = TAPE_SERIES_M.copy()
        bowed = TAPE_SERIES_M.copy()
        bowed[1] += 0.004
        bowed[2] += 0.004          # endpoints untouched, one side bowed

        flat_fit = triangulate.fit_scale_regression(straight, TAPE_SERIES_M)
        bowed_fit = triangulate.fit_scale_regression(bowed, TAPE_SERIES_M)

        self.assertAlmostEqual(flat_fit.scale, 1.0, places=9)
        self.assertGreater(abs(bowed_fit.scale - flat_fit.scale), 0.003)

    def test_a_noiseless_series_claims_no_uncertainty(self):
        fit = triangulate.fit_scale_regression(TAPE_SERIES_M, TAPE_SERIES_M)
        self.assertAlmostEqual(fit.scale_stderr, 0.0, places=12)

    def test_twice_the_scatter_is_twice_the_stated_uncertainty(self):
        wobble = np.array([1.0, -1.0, 1.0, -1.0, 1.0, -1.0]) * 0.001
        tight = triangulate.fit_scale_regression(TAPE_SERIES_M + wobble,
                                                 TAPE_SERIES_M)
        loose = triangulate.fit_scale_regression(TAPE_SERIES_M + 2 * wobble,
                                                 TAPE_SERIES_M)
        self.assertGreater(tight.scale_stderr, 0.0)
        self.assertAlmostEqual(loose.scale_stderr / tight.scale_stderr,
                               2.0, places=6)

    def test_repeats_at_one_position_are_used_and_tighten_the_estimate(self):
        # Three frames at each position, without touching the ball, is two
        # extra keypresses and it is how the operator buys precision on a
        # 0.6% question. A consecutive-differences estimator discarded them
        # outright: repeated positions give a zero tape gap.
        wobble = np.array([1.0, -1.0, 1.0, -1.0, 1.0, -1.0]) * 0.001
        once = triangulate.fit_scale_regression(TAPE_SERIES_M + wobble,
                                                TAPE_SERIES_M)
        thrice = triangulate.fit_scale_regression(
            np.tile(TAPE_SERIES_M + wobble, 3), np.tile(TAPE_SERIES_M, 3))

        self.assertEqual(thrice.n, 18)
        self.assertAlmostEqual(thrice.scale, once.scale, places=9)
        # n 6 -> 18 triples both the scatter sum and the tape spread, while
        # the degrees of freedom go 4 -> 16: the uncertainty halves exactly.
        self.assertAlmostEqual(thrice.scale_stderr / once.scale_stderr,
                               0.5, places=6)

    def test_refuses_fewer_than_three_positions(self):
        # Two points fit any line exactly. A zero residual and a zero
        # uncertainty from that would be a statement about arithmetic.
        with self.assertRaises(ValueError):
            triangulate.fit_scale_regression(np.array([0.35, 0.42]),
                                             np.array([0.35, 0.42]))

    def test_refuses_a_tape_that_never_moved(self):
        with self.assertRaises(ValueError):
            triangulate.fit_scale_regression(np.array([0.35, 0.36, 0.37]),
                                             np.array([0.40, 0.40, 0.40]))

    def test_refuses_mismatched_lengths(self):
        with self.assertRaises(ValueError):
            triangulate.fit_scale_regression(np.array([0.35]),
                                             np.array([0.35, 0.42]))


class RepeatSpreadTest(unittest.TestCase):
    """What repeated shots at one tape reading actually establish.

    The scale's standard error is computed from scatter about the fitted
    line, and it assumes scatter is the only error there is. It is not: a
    detection bias that grows with depth is a scale error by another name,
    it lands entirely in the slope, and no amount of scatter-based
    arithmetic can see it. Reporting the within-position spread separately
    is what keeps a small stderr from being read as a small error.
    """

    def test_identical_repeats_have_no_spread(self):
        spread = triangulate.pooled_repeat_spread_m(
            [0.50, 0.50, 0.50, 0.62, 0.62], [500.0, 500.0, 500.0, 620.0, 620.0])
        self.assertAlmostEqual(spread, 0.0, places=12)

    def test_recovers_a_known_within_group_spread(self):
        # Deviations of +-10 mm and 0 about the group mean: the pooled
        # estimate over 2 degrees of freedom is sqrt(0.0002 / 2) = 10 mm.
        spread = triangulate.pooled_repeat_spread_m(
            [0.500, 0.510, 0.490], [500.0, 500.0, 500.0])
        self.assertAlmostEqual(spread, 0.010, places=9)

    def test_pools_across_groups_rather_than_averaging_them(self):
        # Two groups of two, deviations +-5 mm and +-15 mm about their own
        # means: sum of squares 2*(0.005^2) + 2*(0.015^2) = 5.0e-4 over 2
        # degrees of freedom, so 15.81 mm. Averaging the two groups' spreads
        # would give 14.14 and quietly understate the worse one.
        spread = triangulate.pooled_repeat_spread_m(
            [0.495, 0.505, 0.605, 0.635],
            [500.0, 500.0, 620.0, 620.0])
        self.assertAlmostEqual(spread, 0.0158114, places=6)

    def test_a_position_measured_once_contributes_nothing(self):
        # A singleton group has no deviation from its own mean and no
        # degree of freedom. Counting it would drag the estimate toward zero.
        with_singleton = triangulate.pooled_repeat_spread_m(
            [0.500, 0.510, 0.490, 0.700], [500.0, 500.0, 500.0, 700.0])
        self.assertAlmostEqual(with_singleton, 0.010, places=9)

    def test_returns_none_when_nothing_was_repeated(self):
        # Not zero. Zero is a measurement of perfect repeatability, and a
        # series with no repeats made no such measurement.
        self.assertIsNone(triangulate.pooled_repeat_spread_m(
            [0.35, 0.42, 0.49], [350.0, 420.0, 490.0]))

    def test_refuses_mismatched_lengths(self):
        with self.assertRaises(ValueError):
            triangulate.pooled_repeat_spread_m([0.35, 0.42], [350.0])


class LineFitTest(unittest.TestCase):
    """The depth line's own direction, which the scale fit depends on.

    The scale compares a difference of triangulated Z against a difference
    of tape readings. Those are the same quantity only insofar as the line
    the balls sat on runs along camera 1's optical axis. The angle between
    the two biases the scale by cos of itself - 2 deg is 0.06%, 5 deg is
    0.38%, against a 0.6% question - and nothing in the run measured it.
    The points themselves do.
    """

    def _along(self, direction, start=(0.0, 0.09, 0.35), steps=(0, 1, 2, 3)):
        direction = np.asarray(direction, dtype=float)
        direction = direction / np.linalg.norm(direction)
        return np.array([np.asarray(start, float) + t * 0.07 * direction
                         for t in steps])

    def test_a_line_along_the_optical_axis_has_no_obliquity(self):
        fit = triangulate.fit_line(self._along([0.0, 0.0, 1.0]))
        self.assertAlmostEqual(fit.obliquity_deg, 0.0, places=9)
        self.assertAlmostEqual(fit.horizontal_deg, 0.0, places=9)
        self.assertAlmostEqual(fit.vertical_deg, 0.0, places=9)

    def test_direction_points_away_from_the_camera_whatever_the_point_order(self):
        # SVD returns a direction of arbitrary sign. Left alone, half of all
        # runs would report a 175 deg obliquity for a line laid 5 deg off,
        # and the scale correction would be catastrophically wrong rather
        # than visibly wrong.
        points = self._along([np.sin(np.radians(5.0)), 0.0,
                              np.cos(np.radians(5.0))])
        for ordered in (points, points[::-1]):
            fit = triangulate.fit_line(ordered)
            self.assertGreater(fit.direction[2], 0.0)
            self.assertAlmostEqual(fit.obliquity_deg, 5.0, places=6)

    def test_recovers_a_line_swung_to_the_right(self):
        # Same sense as yaw_from_target_line: positive means the line runs
        # to the camera's right as it goes away.
        fit = triangulate.fit_line(
            self._along([np.sin(np.radians(5.0)), 0.0, np.cos(np.radians(5.0))]))
        self.assertAlmostEqual(fit.horizontal_deg, 5.0, places=6)
        self.assertAlmostEqual(fit.vertical_deg, 0.0, places=9)
        self.assertAlmostEqual(fit.obliquity_deg, 5.0, places=6)

    def test_recovers_a_line_running_downhill_in_the_camera_frame(self):
        # Y is down, so a positive vertical angle means the line descends as
        # it recedes. For a level floor line this equals the camera's own
        # pitch: a nose-down camera reads negative on both.
        fit = triangulate.fit_line(
            self._along([0.0, np.sin(np.radians(-3.0)), np.cos(np.radians(3.0))]))
        self.assertAlmostEqual(fit.vertical_deg, -3.0, places=6)
        self.assertAlmostEqual(fit.horizontal_deg, 0.0, places=9)
        self.assertAlmostEqual(fit.obliquity_deg, 3.0, places=6)

    def test_a_perfect_line_has_no_scatter(self):
        self.assertLess(triangulate.fit_line(self._along([0.0, 0.0, 1.0])).rms_m,
                        1e-12)

    def test_a_line_oblique_to_every_axis_still_has_no_scatter(self):
        # Straightness, not axis-alignment. Taking the scatter from the two
        # smaller singular values rather than by subtracting the along-line
        # part keeps this from reading millimetres of pure rounding.
        self.assertLess(triangulate.fit_line(self._along([0.3, 0.05, 1.0])).rms_m,
                        1e-12)

    def test_a_lateral_wobble_shows_up_in_the_scatter(self):
        # 5 mm of sideways wander is the figure that would have inflated a
        # 3D-norm scale fit by 0.26% - a quarter of the 0.6% being resolved.
        pts = np.array([[0.03, 0.0937, 0.35],
                        [0.03 + 0.005, 0.0937, 0.42],
                        [0.03, 0.0937, 0.49],
                        [0.03 + 0.005, 0.0937, 0.56]])
        rms = triangulate.fit_line(pts).rms_m
        self.assertGreater(rms, 0.001)
        self.assertLess(rms, 0.005)

    def test_refuses_fewer_than_three_points(self):
        # Two points are exactly collinear by definition; a zero scatter
        # from that would be a statement about arithmetic, not the operator.
        with self.assertRaises(ValueError):
            triangulate.fit_line(np.array([[0.0, 0.09, 0.35],
                                           [0.0, 0.09, 0.42]]))


if __name__ == "__main__":
    unittest.main()
