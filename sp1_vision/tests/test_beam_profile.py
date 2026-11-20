"""IR beam profile from one flash on a flat wall: angles, correction, tilts."""

import unittest

import numpy as np

from sp1_vision import beam_profile, stereo_geometry


def _gauss(theta, peak=0.0, hwhm=9.0):
    """A beam that halves `hwhm` degrees from its peak."""
    return np.exp(-np.log(2) * ((np.asarray(theta, dtype=float) - peak) / hwhm) ** 2)


class Angles(unittest.TestCase):
    def setUp(self):
        rig = stereo_geometry.load_rig()
        self.k, self.d = rig.k1, rig.d1

    def test_principal_point_is_on_the_axis(self):
        v, h, a = beam_profile.ray_angles(self.k, np.zeros(5), (1280, 800))
        cx, cy = int(round(self.k[0, 2])), int(round(self.k[1, 2]))
        self.assertLess(abs(v[cy, cx]), 0.05)
        self.assertLess(abs(h[cy, cx]), 0.05)
        self.assertLess(a[cy, cx], 0.05)

    def test_up_is_positive_and_right_is_positive(self):
        v, h, _ = beam_profile.ray_angles(self.k, self.d, (1280, 800))
        cx, cy = int(round(self.k[0, 2])), int(round(self.k[1, 2]))
        self.assertGreater(v[0, cx], 15.0)          # top row: well above the axis
        self.assertLess(v[799, cx], -15.0)
        self.assertGreater(h[cy, 1279], 25.0)       # right edge
        self.assertLess(h[cy, 0], -25.0)

    def test_pinhole_angle_matches_focal_length(self):
        v, _, _ = beam_profile.ray_angles(self.k, np.zeros(5), (1280, 800))
        cx, cy = int(round(self.k[0, 2])), int(round(self.k[1, 2]))
        expected = np.degrees(np.arctan((cy - 100) / self.k[1, 1]))
        self.assertAlmostEqual(float(v[100, cx]), expected, delta=0.05)


class PlaneCorrection(unittest.TestCase):
    def test_cos_cubed(self):
        np.testing.assert_allclose(beam_profile.plane_factor(np.array([0.0, 60.0])),
                                   [1.0, 0.125], atol=1e-12)


class Profile(unittest.TestCase):
    def test_vertical_profile_of_a_flat_wall_recovers_the_beam(self):
        rig = stereo_geometry.load_rig()
        v, h, a = beam_profile.ray_angles(rig.k1, rig.d1, (1280, 800))
        # What the camera sees on a perpendicular wall: beam x cos^3.
        img = 100.0 * _gauss(v, peak=2.0, hwhm=9.0) * _gauss(h, hwhm=20.0) * beam_profile.plane_factor(a)
        angles, prof = beam_profile.vertical_profile(img, v, h, a)
        lo, hi = beam_profile.half_power_angles(angles, prof)
        self.assertAlmostEqual(hi, 11.0, delta=0.7)
        self.assertAlmostEqual(lo, -7.0, delta=0.7)

    def test_profile_can_be_limited_to_angles_above_a_floor(self):
        # 2026-11-21: a white skirting board below the dark wall - only the
        # wall above it (+1 deg up) is one surface.
        rig = stereo_geometry.load_rig()
        v, h, a = beam_profile.ray_angles(rig.k1, rig.d1, (1280, 800))
        img = 100.0 * _gauss(v, hwhm=9.0) * beam_profile.plane_factor(a)
        img[v < 1.0] = 255.0                      # the bright skirting board
        angles, prof = beam_profile.vertical_profile(img, v, h, a, min_deg=1.0)
        self.assertGreaterEqual(angles.min(), 1.0)
        self.assertAlmostEqual(float(np.interp(9.0, angles, prof) / np.interp(1.5, angles, prof)),
                               float(_gauss(9.0) / _gauss(1.5)), delta=0.03)

    def test_half_power_outside_the_range_is_none(self):
        angles = np.arange(-20.0, 21.0)
        lo, hi = beam_profile.half_power_angles(angles, _gauss(angles, hwhm=40.0))
        self.assertIsNone(lo)
        self.assertIsNone(hi)


class Tilts(unittest.TestCase):
    def test_flat_beam_and_a_high_flight_ask_for_one_array_up(self):
        angles = np.arange(-24.0, 24.0, 0.5)
        prof = _gauss(angles, hwhm=9.0)
        best = beam_profile.best_tilts(angles, prof, need=(-13.0, 22.0))
        up, down = max(best.tilts), min(best.tilts)
        self.assertGreaterEqual(up, 10.0)
        self.assertLessEqual(down, 0.0)
        today = beam_profile.combined(angles, prof, (0.0, 0.0), np.array([22.0]))[0]
        self.assertGreater(best.min_rel, today)        # the worst point gets brighter

    def test_combined_is_the_mean_of_shifted_profiles(self):
        angles = np.arange(-30.0, 31.0)
        prof = _gauss(angles, hwhm=9.0)
        c = beam_profile.combined(angles, prof, (10.0, 0.0), np.array([10.0, 0.0]))
        np.testing.assert_allclose(c, [0.5 * (1 + _gauss(10.0)), 0.5 * (_gauss(-10.0) + 1)], atol=1e-6)


class Extrapolation(unittest.TestCase):
    def test_beyond_both_sides_is_the_dark_end_not_the_peak(self):
        # Measured only from the peak (+1.5) upwards, as on 2026-11-21.
        angles = np.arange(1.5, 23.0, 1.0)
        prof = _gauss(angles, peak=1.5, hwhm=15.0)
        far = beam_profile.combined(angles, prof, (0.0,), np.array([-25.0, 30.0]))
        np.testing.assert_allclose(far, [prof[-1], prof[-1]], atol=1e-9)

    def test_mirror_inside_the_measured_distance(self):
        angles = np.arange(1.5, 23.0, 1.0)
        prof = _gauss(angles, peak=1.5, hwhm=15.0)
        below = beam_profile.combined(angles, prof, (0.0,), np.array([1.5 - 10.0]))[0]
        self.assertAlmostEqual(below, float(_gauss(11.5, peak=1.5, hwhm=15.0)), delta=0.01)


class Chart(unittest.TestCase):
    def test_draws_several_curves(self):
        angles = np.arange(-20.0, 21.0)
        curves = [((angles, _gauss(angles)), (200, 0, 0), "a"),
                  ((angles, _gauss(angles, peak=5.0)), (0, 0, 200), "b")]
        img = beam_profile._chart(curves, need=(-13.0, 20.0))
        self.assertEqual(img.shape, (420, 900, 3))


if __name__ == "__main__":
    unittest.main()
