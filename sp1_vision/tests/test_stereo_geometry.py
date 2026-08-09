"""The rig is the one place frames, units and signs are converted.

Everything here guards a failure mode that is invisible downstream: a
mismatched intrinsics source, a millimetre read as a metre, a swapped pair.
"""

import json
import os
import shutil
import tempfile
import unittest

import numpy as np

from sp1_vision import stereo_geometry


def write_extrinsics(path, translation_mm=(78.710, -0.279, -2.457), rotation=None):
    if rotation is None:
        rotation = [[0.9998768, 0.0143309, 0.0063980],
                    [-0.0144342, 0.9997613, 0.0163990],
                    [-0.0061615, -0.0164893, 0.9998451]]
    with open(path, "w") as fh:
        json.dump({
            "method": "cv.stereoCalibrate with CALIB_FIX_INTRINSIC",
            "square_mm": 24.0,
            "rms_px": 0.846,
            "baseline_mm": float(np.linalg.norm(translation_mm)),
            "translation_mm": list(translation_mm),
            "rotation_matrix": rotation,
        }, fh)


def write_config(path, fx1=900.375, fx2=899.989):
    def matrix(fx, cx, cy):
        return [[str(fx), "0.0", str(cx)], ["0.0", str(fx), str(cy)],
                ["0.0", "0.0", "1.0"]]
    with open(path, "w") as fh:
        json.dump({"gs_config": {"cameras": {
            "kCamera1CalibrationMatrix": matrix(fx1, 635.097, 420.049),
            "kCamera1DistortionVector": ["0.0086", "-0.0060", "0.0021",
                                         "-0.0024", "-0.0880"],
            "kCamera2CalibrationMatrix": matrix(fx2, 631.043, 421.086),
            "kCamera2DistortionVector": ["0.0090", "-0.0062", "0.0020",
                                         "-0.0025", "-0.0870"],
        }}}, fh)


class LoadRigTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.ext = os.path.join(self.root, "stereo_extrinsics.json")
        self.cfg = os.path.join(self.root, "golf_sim_config.json")
        write_extrinsics(self.ext)
        write_config(self.cfg)

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_translation_is_converted_from_mm_to_m(self):
        rig = stereo_geometry.load_rig(self.ext, self.cfg)
        self.assertAlmostEqual(rig.t_m[0], 0.078710, places=6)
        self.assertAlmostEqual(rig.baseline_m, 0.078749, places=5)

    def test_intrinsics_are_parsed_from_strings_to_floats(self):
        rig = stereo_geometry.load_rig(self.ext, self.cfg)
        self.assertAlmostEqual(rig.k1[0, 0], 900.375, places=3)
        self.assertAlmostEqual(rig.k2[1, 2], 421.086, places=3)
        self.assertEqual(rig.d1.shape, (5,))

    def test_projection_matrices_are_for_normalised_coordinates(self):
        # P1 = [I|0] and P2 = [R|t]. Anything with K baked in would silently
        # double-apply the intrinsics after undistortPoints normalises.
        rig = stereo_geometry.load_rig(self.ext, self.cfg)
        p1, p2 = rig.projection_matrices()
        np.testing.assert_allclose(p1[:, :3], np.eye(3), atol=1e-12)
        np.testing.assert_allclose(p1[:, 3], np.zeros(3), atol=1e-12)
        np.testing.assert_allclose(p2[:, :3], rig.r, atol=1e-12)
        np.testing.assert_allclose(p2[:, 3], rig.t_m, atol=1e-12)


class ValidateRigTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.ext = os.path.join(self.root, "stereo_extrinsics.json")
        self.cfg = os.path.join(self.root, "golf_sim_config.json")
        write_config(self.cfg)

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_accepts_the_real_rig(self):
        write_extrinsics(self.ext)
        stereo_geometry.validate_rig(stereo_geometry.load_rig(self.ext, self.cfg))

    def test_rejects_a_baseline_that_means_the_wrong_square_size(self):
        # A 20 mm board assumed against a 24 mm print gave 66.40 mm once
        # already. That is a wrong answer, not a noisy one.
        write_extrinsics(self.ext, translation_mm=(66.40, 0.0, 0.0))
        with self.assertRaises(stereo_geometry.StereoRigError):
            stereo_geometry.validate_rig(stereo_geometry.load_rig(self.ext, self.cfg))

    def test_rejects_a_rotation_far_from_identity(self):
        theta = np.radians(20.0)
        write_extrinsics(self.ext, rotation=[
            [np.cos(theta), 0.0, np.sin(theta)],
            [0.0, 1.0, 0.0],
            [-np.sin(theta), 0.0, np.cos(theta)]])
        with self.assertRaises(stereo_geometry.StereoRigError):
            stereo_geometry.validate_rig(stereo_geometry.load_rig(self.ext, self.cfg))

    def test_rejects_intrinsics_from_a_different_source(self):
        # Extrinsics solved with CALIB_FIX_INTRINSIC absorb the intrinsics'
        # error into R and T. Pairing them with other intrinsics is the one
        # combination that is definitely wrong and looks fine in the RMS.
        write_extrinsics(self.ext)
        write_config(self.cfg, fx1=1400.0)
        with self.assertRaises(stereo_geometry.StereoRigError):
            stereo_geometry.validate_rig(stereo_geometry.load_rig(self.ext, self.cfg))

    def test_rejects_wrong_image_size(self):
        # The intrinsics were solved at (1280, 800). A different image size
        # means the intrinsics don't match the hardware, so the rig is broken.
        write_extrinsics(self.ext)
        write_config(self.cfg)
        rig = stereo_geometry.load_rig(self.ext, self.cfg)
        # Manually change the image size to the old IMX296 resolution
        rig.image_size = (1456, 1088)
        with self.assertRaises(stereo_geometry.StereoRigError):
            stereo_geometry.validate_rig(rig)

    def test_rejects_baseline_above_maximum(self):
        # A baseline above the maximum indicates a wrong scale or file source.
        # This tests the upper bound, complementing the lower-bound test.
        write_extrinsics(self.ext, translation_mm=(95.0, 0.0, 0.0))
        with self.assertRaises(stereo_geometry.StereoRigError):
            stereo_geometry.validate_rig(stereo_geometry.load_rig(self.ext, self.cfg))


class FrameConversionTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.ext = os.path.join(self.root, "stereo_extrinsics.json")
        self.cfg = os.path.join(self.root, "golf_sim_config.json")
        write_extrinsics(self.ext)
        write_config(self.cfg)
        self.rig = stereo_geometry.load_rig(self.ext, self.cfg)

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_pitrac_frame_negates_y_and_nothing_else(self):
        # gs_camera.cpp:1157 - "Y distance, positive is upward". The
        # extrinsics are Y down. Getting this backwards inverts launch angle.
        np.testing.assert_allclose(
            stereo_geometry.to_pitrac_frame([1.0, 2.0, 3.0]),
            [1.0, -2.0, 3.0], atol=1e-12)

    def test_pitrac_frame_is_its_own_inverse(self):
        there = stereo_geometry.to_pitrac_frame([0.1, -0.2, 0.3])
        np.testing.assert_allclose(
            stereo_geometry.to_pitrac_frame(there), [0.1, -0.2, 0.3], atol=1e-12)

    def test_camera2_sits_left_of_camera1_in_the_cameras_own_frame(self):
        # T_x is +78.7 mm, which is camera 1's origin seen from camera 2. So
        # camera 2 is at NEGATIVE x in camera 1's frame. Reading the positive
        # T_x as "camera 1 is on the right" is the trap; the unit's frame and
        # the player's are mirrored, and camera 1 is the player's left module.
        centre = stereo_geometry.camera2_centre_in_camera1(self.rig)
        self.assertLess(centre[0], 0.0)
        self.assertAlmostEqual(centre[0], -0.078720, places=5)
        # places=7, not 9: the fixture's R is calibration output rounded to
        # 7 decimals, so R.T @ R deviates from I by ~8.6e-8, not float64
        # epsilon. Asking for 9-decimal agreement tests the literal's
        # rounding, not the norm-preservation this check exists to catch.
        self.assertAlmostEqual(np.linalg.norm(centre), self.rig.baseline_m, places=7)

    def test_camera2_offset_matches_the_hand_computed_value(self):
        # -R.T @ t, then Y negated for PiTrac. The rotation matters here: a
        # plain -t gets Y wrong in sign and 3.2x wrong in size, and Z wrong by
        # 1.26x - which is the argument for computing rather than typing it.
        # Asserted below against the naive value, so the claim is checked and
        # not merely stated.
        offset = stereo_geometry.camera2_offset_from_camera1(self.rig)
        np.testing.assert_allclose(
            offset, [-0.078720, 0.000890, 0.001957], atol=2e-6)

        naive = stereo_geometry.to_pitrac_frame(-self.rig.t_m)
        self.assertLess(naive[1] * offset[1], 0.0)          # Y sign flipped
        self.assertAlmostEqual(abs(offset[1] / naive[1]), 3.19, delta=0.05)
        self.assertAlmostEqual(naive[2] / offset[2], 1.256, delta=0.01)
        self.assertAlmostEqual(naive[0], offset[0], places=4)

    def test_offset_replaces_pitracs_vertical_stacking(self):
        # PiTrac ships [0, -0.19, 0] - their cameras sit 19 cm apart
        # vertically. Ours are side by side; the dominant term must be X.
        offset = stereo_geometry.camera2_offset_from_camera1(self.rig)
        self.assertGreater(abs(offset[0]), 20 * abs(offset[1]))


if __name__ == "__main__":
    unittest.main()
