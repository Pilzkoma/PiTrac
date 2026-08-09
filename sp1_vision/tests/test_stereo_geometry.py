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


if __name__ == "__main__":
    unittest.main()
