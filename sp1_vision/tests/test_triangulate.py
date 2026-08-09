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
    def test_matches_the_hand_computed_figure_at_the_working_distance(self):
        # Z^2 / (b * f) = 0.5087^2 / (0.07872 * 900) = 3.65 mm per pixel.
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


class StraightnessTest(unittest.TestCase):
    """How far the depth series wandered off the line it was meant to be.

    Reported next to the scale so a badly-laid line is visible. The scale
    itself uses the depth component alone and is immune to this, which is
    the point of measuring it separately rather than letting it hide inside
    the scale residual.
    """

    def test_a_perfect_line_reads_zero(self):
        pts = np.array([[0.03, 0.0937, z] for z in (0.35, 0.42, 0.49, 0.56)])
        self.assertLess(triangulate.straightness_rms_m(pts), 1e-12)

    def test_a_line_oblique_to_every_axis_still_reads_zero(self):
        # Straightness, not axis-alignment: a line laid at an angle to the
        # unit is still a line, and the number must not punish it for that.
        direction = np.array([0.3, 0.05, 1.0])
        pts = np.array([np.array([0.0, 0.09, 0.35]) + t * direction
                        for t in (0.0, 0.07, 0.14, 0.21)])
        self.assertLess(triangulate.straightness_rms_m(pts), 1e-12)

    def test_a_lateral_wobble_shows_up(self):
        # 5 mm of sideways wander is the figure that would have inflated a
        # 3D-norm scale fit by 0.26% - a quarter of the 0.6% being resolved.
        pts = np.array([[0.03, 0.0937, 0.35],
                        [0.03 + 0.005, 0.0937, 0.42],
                        [0.03, 0.0937, 0.49],
                        [0.03 + 0.005, 0.0937, 0.56]])
        rms = triangulate.straightness_rms_m(pts)
        self.assertGreater(rms, 0.001)
        self.assertLess(rms, 0.005)

    def test_refuses_fewer_than_three_points(self):
        # Two points are exactly collinear by definition; a zero from that
        # would be a statement about arithmetic, not about the operator.
        with self.assertRaises(ValueError):
            triangulate.straightness_rms_m(
                np.array([[0.0, 0.09, 0.35], [0.0, 0.09, 0.42]]))


class ScaleFactorTest(unittest.TestCase):
    """Does the triangulated world match the tape's, in size?

    Fitted on DIFFERENCES between positions, never on absolute distances -
    the lens plane's exact location is a guess, and a constant offset in it
    would masquerade as a scale error.
    """

    def test_perfect_agreement_gives_unit_scale(self):
        tape = np.array([0.070, 0.070, 0.070, 0.070, 0.070])
        scale, rms = triangulate.fit_scale_factor(tape, tape)
        self.assertAlmostEqual(scale, 1.0, places=9)
        self.assertLess(rms, 1e-12)

    def test_recovers_a_known_scale_error(self):
        # 78.28 against 78.749 mm of baseline is 0.6%, and a baseline that is
        # 0.6% too large makes every triangulated distance 0.6% too large.
        tape = np.array([0.070, 0.070, 0.070, 0.070, 0.070, 0.070])
        measured = tape * 1.006
        scale, rms = triangulate.fit_scale_factor(measured, tape)
        self.assertAlmostEqual(scale, 1.006, places=6)
        self.assertLess(rms, 1e-9)

    def test_noise_shows_up_in_the_residual_not_the_scale(self):
        tape = np.full(6, 0.070)
        measured = tape + np.array([0.001, -0.001, 0.0008, -0.0009, 0.0, 0.0011])
        scale, rms = triangulate.fit_scale_factor(measured, tape)
        self.assertAlmostEqual(scale, 1.0, delta=0.01)
        self.assertGreater(rms, 1e-5)

    def test_refuses_mismatched_lengths(self):
        with self.assertRaises(ValueError):
            triangulate.fit_scale_factor(np.array([0.07]), np.array([0.07, 0.07]))


if __name__ == "__main__":
    unittest.main()
