"""The floor, fitted - and the two things it can and cannot tell us.

A plane gives pitch and roll. It cannot give yaw: a plane is rotationally
symmetric about its normal, so yaw needs the target-line pair.
"""

import unittest

import numpy as np

from sp1_vision import ground_plane


def floor_points(pitch_deg=0.0, roll_deg=0.0, n_x=4, n_z=3):
    """Ball centres on a floor, as seen by a camera at the given attitude.

    Camera frame: X right, Y down, Z forward. A level camera sees the floor
    below it, so the plane's normal is -Y. Positive pitch is nose-up;
    positive roll is right-side-down.

    `rz @ rx` is the camera's own rotation (pitch about X, then roll about
    Z, relative to level). The points below are fixed in the world, so what
    the camera sees is the INVERSE of that rotation applied to them -
    world-fixed points expressed in a rotated camera's frame transform by
    R^-1 = R^T, not by R itself. `pts @ M` applies `M.T` to each row, so
    `pts @ (rz @ rx)` is what does that (dropping the .T here is not a typo:
    it is what turns "rotate the points by R" into "view the points from a
    camera rotated by R").
    """
    xs = np.linspace(-0.25, 0.25, n_x)
    zs = np.linspace(0.35, 0.70, n_z)
    pts = np.array([[x, 0.0937, z] for z in zs for x in xs])

    p = np.radians(pitch_deg)
    rx = np.array([[1, 0, 0],
                   [0, np.cos(p), -np.sin(p)],
                   [0, np.sin(p), np.cos(p)]])
    q = np.radians(roll_deg)
    rz = np.array([[np.cos(q), -np.sin(q), 0],
                   [np.sin(q), np.cos(q), 0],
                   [0, 0, 1]])
    return pts @ (rz @ rx)


class FitPlaneTest(unittest.TestCase):
    def test_level_floor_has_an_upward_normal(self):
        plane = ground_plane.fit_plane(floor_points())
        np.testing.assert_allclose(plane.normal, [0.0, -1.0, 0.0], atol=1e-9)
        self.assertLess(plane.rms_m, 1e-9)

    def test_normal_is_always_oriented_upward(self):
        # This asserts the POSTCONDITION, on a point set and on its
        # Y-mirrored twin. Negating the Y column of the input negates the Y
        # component of every right singular vector, so if LAPACK's sign
        # choice were left to decide the answer, the two would come out
        # opposite and one of these assertions would fail. Which of the two
        # needs the flip is a property of the LAPACK build, so the test must
        # not depend on knowing it - an earlier version asserted only the
        # first case and would have gone quietly vacuous on another build,
        # taking fit_plane's docstring with it.
        for pitch in (-2.0, 2.0):
            pts = floor_points(pitch_deg=pitch)
            mirrored = pts * np.array([1.0, -1.0, 1.0])
            for name, candidate in (("as-is", pts), ("Y-mirrored", mirrored)):
                plane = ground_plane.fit_plane(candidate)
                self.assertLess(plane.normal[1], 0.0,
                                "{} at pitch {}".format(name, pitch))

    def test_the_flip_is_exercised_by_one_of_the_two_orientations(self):
        # Companion to the test above: it proves the pair of inputs really
        # does straddle LAPACK's sign choice, so that test is doing work.
        # If a future numpy made both raw normals point the same way, this
        # fails and says so rather than letting the guard go untested.
        raw_signs = []
        for factor in (1.0, -1.0):
            pts = floor_points(pitch_deg=2.0) * np.array([1.0, factor, 1.0])
            centred = pts - pts.mean(axis=0)
            _, _, vt = np.linalg.svd(centred, full_matrices=False)
            raw_signs.append(np.sign(vt[2][1]))
        self.assertEqual(sorted(raw_signs), [-1.0, 1.0])

    def test_reports_residuals_for_a_noisy_floor(self):
        pts = floor_points()
        pts[3, 1] += 0.004
        plane = ground_plane.fit_plane(pts)
        self.assertGreater(plane.rms_m, 1e-4)

    def test_refuses_a_near_collinear_set(self):
        # Points along one line fit a plane beautifully and determine
        # nothing. The residual will not show it; conditioning does. This is
        # the same failure that left cy unconstrained at an RMS of 0.90.
        collinear = np.array([[0.0, 0.0937, z] for z in np.linspace(0.35, 0.7, 6)])
        with self.assertRaises(ground_plane.PlaneFitError):
            ground_plane.fit_plane(collinear)

    def test_refuses_fewer_than_three_points(self):
        with self.assertRaises(ground_plane.PlaneFitError):
            ground_plane.fit_plane(np.array([[0.0, 0.09, 0.4], [0.1, 0.09, 0.5]]))


class AttitudeTest(unittest.TestCase):
    def test_level_device_reads_zero(self):
        pitch, roll = ground_plane.attitude_from_plane(
            ground_plane.fit_plane(floor_points()))
        self.assertAlmostEqual(pitch, 0.0, places=6)
        self.assertAlmostEqual(roll, 0.0, places=6)

    def test_recovers_pitch(self):
        pitch, roll = ground_plane.attitude_from_plane(
            ground_plane.fit_plane(floor_points(pitch_deg=1.7)))
        self.assertAlmostEqual(pitch, 1.7, places=3)
        self.assertAlmostEqual(roll, 0.0, places=3)

    def test_recovers_roll(self):
        pitch, roll = ground_plane.attitude_from_plane(
            ground_plane.fit_plane(floor_points(roll_deg=-1.1)))
        self.assertAlmostEqual(pitch, 0.0, places=3)
        self.assertAlmostEqual(roll, -1.1, places=3)

    def test_recovers_both_together(self):
        # Both formulas in attitude_from_plane are exact for this fixture's
        # rotation order (not small-angle approximations - see that
        # function's docstring), so this holds far tighter than its
        # single-angle neighbours.
        #
        # places=5, not 3: the abandoned inexact pair - arcsin(n[2]) for
        # pitch, arctan2(n[0], -n[1]) for roll - is wrong here by only
        # 8.8e-5 deg and sails through places=3, so that tolerance does not
        # discriminate between the two versions at all. Exactness cost two
        # rounds of fixes to establish; this is the assertion that keeps it.
        pitch, roll = ground_plane.attitude_from_plane(
            ground_plane.fit_plane(floor_points(pitch_deg=-0.9, roll_deg=0.8)))
        self.assertAlmostEqual(pitch, -0.9, places=5)
        self.assertAlmostEqual(roll, 0.8, places=5)

    def test_stays_exact_at_a_large_attitude(self):
        # The same claim where the inexact pair is not merely detectable but
        # obvious: at 30/20 deg it errs by degrees, not by 1e-4 of one.
        pitch, roll = ground_plane.attitude_from_plane(
            ground_plane.fit_plane(floor_points(pitch_deg=30.0, roll_deg=20.0)))
        self.assertAlmostEqual(pitch, 30.0, places=5)
        self.assertAlmostEqual(roll, 20.0, places=5)


class CameraHeightTest(unittest.TestCase):
    """The 115 mm mounting height, measured rather than assumed.

    The fixture's ball centres sit at Y = +0.0937 m, one ball radius below
    the 0.115 m the spec states - so a correct implementation returns 115 mm
    and the sign error of subtracting the radius instead of adding it
    returns 72 mm, which is not a subtle difference.
    """

    def test_level_floor_gives_the_spec_height(self):
        plane = ground_plane.fit_plane(floor_points())
        height = ground_plane.camera_height_above_floor_m(plane)
        self.assertAlmostEqual(height, 0.0937 + ground_plane.GOLF_BALL_RADIUS_M,
                               places=9)
        self.assertAlmostEqual(height * 1000.0, 115.0, delta=0.1)

    def test_the_radius_is_added_not_subtracted(self):
        # The floor is FURTHER from the camera than the ball centres are,
        # so the height must exceed the perpendicular distance to the fitted
        # plane by exactly one radius.
        plane = ground_plane.fit_plane(floor_points())
        to_plane = float(np.dot(plane.centroid, -plane.normal))
        self.assertGreater(
            ground_plane.camera_height_above_floor_m(plane), to_plane)

    def test_is_unchanged_by_the_attitude_it_is_measured_at(self):
        # Tilting the unit rotates the plane but does not move the camera,
        # so the perpendicular height is the same number at any attitude.
        level = ground_plane.camera_height_above_floor_m(
            ground_plane.fit_plane(floor_points()))
        tilted = ground_plane.camera_height_above_floor_m(
            ground_plane.fit_plane(floor_points(pitch_deg=3.0, roll_deg=-2.0)))
        self.assertAlmostEqual(level, tilted, places=9)


class YawTest(unittest.TestCase):
    def test_target_line_straight_ahead_reads_zero(self):
        plane = ground_plane.fit_plane(floor_points())
        yaw = ground_plane.yaw_from_target_line(
            plane, [0.0, 0.0937, 0.40], [0.0, 0.0937, 0.70])
        self.assertAlmostEqual(yaw, 0.0, places=6)

    def test_target_line_swung_right_reads_positive(self):
        plane = ground_plane.fit_plane(floor_points())
        yaw = ground_plane.yaw_from_target_line(
            plane, [0.0, 0.0937, 0.40], [0.10, 0.0937, 0.70])
        self.assertAlmostEqual(yaw, np.degrees(np.arctan2(0.10, 0.30)), places=4)

    def test_two_coincident_points_are_refused(self):
        plane = ground_plane.fit_plane(floor_points())
        with self.assertRaises(ground_plane.PlaneFitError):
            ground_plane.yaw_from_target_line(
                plane, [0.0, 0.0937, 0.40], [0.0, 0.0937, 0.40])


if __name__ == "__main__":
    unittest.main()
