"""Setup check: where the rest ball should be, and how to move the unit."""

import unittest

import numpy as np

from sp1_vision import ball_pair, setup_check, stereo_geometry


def _ball(uv1, uv2, r1=45.0, r2=45.0):
    return ball_pair.BallPair([0.0, 0.09, 0.5], uv1, uv2, r1, r2, 0.5, 0.0)


class Target(unittest.TestCase):
    def setUp(self):
        self.rig = stereo_geometry.load_rig()

    def test_rear_camera_by_handedness(self):
        self.assertEqual(setup_check.rear_camera(self.rig, "RH"), 2)   # cam2 at x = -80 mm
        self.assertEqual(setup_check.rear_camera(self.rig, "LH"), 1)

    def test_target_is_50cm_from_the_rear_camera_board(self):
        # The owner's reference (2026-11-18): tape from the camera board
        # (sensor) to the ball centre = 500 mm. The optical centre the stereo
        # depth is measured from sits one focal length (2.75 mm) in front.
        c2 = stereo_geometry.camera2_centre_in_camera1(self.rig)
        t = setup_check.target_xyz_m(self.rig, "RH", ball_y_m=0.09)
        np.testing.assert_allclose(t, [c2[0], 0.09, c2[2] + 0.50 - 0.00275], atol=1e-9)

    def test_target_for_left_handers_is_in_front_of_camera_1(self):
        t = setup_check.target_xyz_m(self.rig, "LH", ball_y_m=0.09)
        np.testing.assert_allclose(t, [0.0, 0.09, 0.50 - 0.00275], atol=1e-9)

    def test_unknown_handedness(self):
        with self.assertRaises(ValueError):
            setup_check.flight_sign("rechts")


class OffsetsAndAdvice(unittest.TestCase):
    T = np.array([0.0, 0.09, 0.50])

    def test_offset_signs(self):
        off = setup_check.offsets(np.array([0.008, 0.09, 0.512]), self.T, "RH")
        self.assertAlmostEqual(off.along_mm, 8.0)
        self.assertAlmostEqual(off.depth_mm, 12.0)
        self.assertFalse(off.ok)
        lh = setup_check.offsets(np.array([0.008, 0.09, 0.5]), self.T, "LH")
        self.assertAlmostEqual(lh.along_mm, -8.0)

    def test_tolerance_boundary(self):
        self.assertTrue(setup_check.offsets(np.array([0.010, 0.09, 0.490]), self.T, "RH").ok)
        self.assertFalse(setup_check.offsets(np.array([0.0105, 0.09, 0.5]), self.T, "RH").ok)

    def test_advice_moves_the_unit(self):
        off = setup_check.offsets(np.array([-0.0204, 0.09, 0.512]), self.T, "RH")
        self.assertEqual(setup_check.advice(off),
                         ["Einheit 12 mm näher zum Ball schieben",
                          "Einheit 20 mm gegen die Schlagrichtung schieben"])
        off = setup_check.offsets(np.array([0.015, 0.09, 0.485]), self.T, "RH")
        self.assertEqual(setup_check.advice(off),
                         ["Einheit 15 mm vom Ball weg schieben",
                          "Einheit 15 mm in Schlagrichtung schieben"])

    def test_advice_when_within_tolerance(self):
        off = setup_check.offsets(np.array([0.004, 0.09, 0.495]), self.T, "RH")
        self.assertEqual(setup_check.advice(off), ["Passt - innerhalb ±10 mm"])


class Margin(unittest.TestCase):
    def test_ball_near_an_edge(self):
        self.assertFalse(setup_check.margin_ok(_ball((30, 400), (640, 400))))
        self.assertFalse(setup_check.margin_ok(_ball((640, 400), (640, 770))))

    def test_ball_well_inside(self):
        self.assertTrue(setup_check.margin_ok(_ball((640, 400), (600, 420))))


if __name__ == "__main__":
    unittest.main()
