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
        # LAPACK's vt[2] sign is deterministic per input, not random, but
        # which sign it picks depends on the data in a way that is not
        # under our control - and for both these inputs it comes out
        # downward without the flip in fit_plane. Verified by temporarily
        # deleting that flip and re-running this test: it fails with
        # normal[1] == +0.999..., not close to zero, so this genuinely
        # exercises the guard rather than passing regardless of it.
        for pitch in (-2.0, 2.0):
            plane = ground_plane.fit_plane(floor_points(pitch_deg=pitch))
            self.assertLess(plane.normal[1], 0.0)

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
        # function's docstring), so this holds to the same tolerance as
        # its single-angle neighbours rather than needing a looser one.
        pitch, roll = ground_plane.attitude_from_plane(
            ground_plane.fit_plane(floor_points(pitch_deg=-0.9, roll_deg=0.8)))
        self.assertAlmostEqual(pitch, -0.9, places=3)
        self.assertAlmostEqual(roll, 0.8, places=3)


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
