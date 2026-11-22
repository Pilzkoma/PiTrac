"""turn_series: a marked ball turned by known angles on the turntable.

The arithmetic (robust mean pose, signed turn about the disc axis, closure)
on exact synthetic rotations, the mark table against a known pose, the
folder layout, and one end-to-end run on the real static fixture pair.
"""
import math
import os
import shutil
import tempfile
import unittest

import cv2
import numpy as np

from sp1_vision import ball_orientation, mark_detect, mark_map, stereo_geometry, turn_series
from sp1_vision.orientation_check import UP_CAM

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "marked_ball")


def rot(axis, deg):
    rv = np.asarray(axis, float)
    rv = rv / np.linalg.norm(rv) * math.radians(deg)
    R, _ = cv2.Rodrigues(rv)
    return R


def wobble(rng, deg):
    return rot(rng.normal(size=3), deg)


R0 = rot([0.3, -0.5, 0.8], 70.0)
DOWN = -np.asarray(UP_CAM, float)


class MeanRotationTest(unittest.TestCase):
    def test_noise_averages_and_a_symmetry_outlier_is_dropped(self):
        rng = np.random.default_rng(1)
        Rs = [wobble(rng, 1.0) @ R0 for _ in range(20)] + [rot([0, 0, 1], 72.0) @ R0]
        m = turn_series.mean_rotation(Rs)
        self.assertIsNotNone(m)
        R, n, spread = m
        self.assertLess(ball_orientation.rotation_angle_deg(R, R0), 0.5)
        self.assertEqual(n, 20)
        self.assertLess(spread, 1.5)
        self.assertAlmostEqual(np.linalg.det(R), 1.0, places=9)

    def test_too_few_agreeing_is_none(self):
        self.assertIsNone(turn_series.mean_rotation([R0]))
        self.assertIsNone(turn_series.mean_rotation(
            [R0, rot([0, 0, 1], 72.0) @ R0, rot([0, 1, 0], 120.0) @ R0]))


class SeriesTest(unittest.TestCase):
    def _series(self, sign=1.0, noise=0.0):
        rng = np.random.default_rng(2)
        out = []
        for deg in list(range(0, 360, 15)) + [360]:
            R = rot(DOWN, sign * deg) @ R0
            if noise:
                R = wobble(rng, noise) @ R
            out.append((deg, R))
        return out

    def test_clockwise_turns_are_recovered_with_the_right_sign(self):
        res = turn_series.analyse_series(self._series(), UP_CAM)
        self.assertEqual(len(res["rows"]), 25)
        for r in res["rows"]:
            self.assertLess(abs(r["err_deg"]), 1e-6, r)
            # no sign at 0, 180 and 360 deg: a half turn has none
            if r["deg"] % 180:
                self.assertIs(r["sign_ok"], True, r)
            else:
                self.assertIsNone(r["sign_ok"], r)
            if r["axis_err_deg"] is not None:
                self.assertLess(r["axis_err_deg"], 1e-4, r)
        for s in res["steps"]:
            self.assertAlmostEqual(s["step_deg"], 15.0, places=6)
            self.assertTrue(s["sign_ok"])
        self.assertLess(res["closure_deg"], 1e-4)   # acos near 1
        self.assertLess(res["axis_tilt_deg"], 1e-4)

    def test_turning_the_other_way_is_a_wrong_sign(self):
        res = turn_series.analyse_series(self._series(sign=-1.0), UP_CAM)
        turned = [r for r in res["rows"] if 0 < r["deg"] % 360 < 180]
        self.assertTrue(turned)
        self.assertFalse(any(r["sign_ok"] for r in turned))
        self.assertFalse(any(s["sign_ok"] for s in res["steps"]))

    def test_a_tilted_disc_shows_as_axis_tilt_not_as_angle_error(self):
        tilt = rot([1, 0, 0], 4.0) @ DOWN
        series = [(deg, rot(tilt, deg) @ R0) for deg in range(0, 361, 15)]
        res = turn_series.analyse_series(series, UP_CAM)
        self.assertAlmostEqual(res["axis_tilt_deg"], 4.0, delta=0.05)
        self.assertLess(max(abs(r["err_deg"]) for r in res["rows"]), 0.2)

    def test_noise_stays_small(self):
        res = turn_series.analyse_series(self._series(noise=1.0), UP_CAM)
        self.assertLess(max(abs(r["err_deg"]) for r in res["rows"]), 3.0)
        self.assertTrue(all(r["sign_ok"] for r in res["rows"]
                            if 10 < r["deg"] < 350 and r["deg"] != 180))


class MarkRowsTest(unittest.TestCase):
    def test_each_blob_is_named_by_the_site_under_the_known_pose(self):
        mmap = mark_map.load_map()
        R = R0
        pred = mmap.normals @ R.T
        site = int(np.argmax(pred[:, 2] * -1.0))       # a site facing the camera (-z)
        n = pred[site]
        blob = mark_detect.MarkBlob(n, "dot", None, 30.0, 12.0, 1.1, 0.9, (0.0, 0.0))
        stray = mark_detect.MarkBlob(rot([1, 0, 0], 25.0) @ n, None, None, 15.0, 30.0,
                                     1.0, 0.7, (0.0, 0.0))
        rows = turn_series.mark_rows([blob, stray], R, mmap)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["site"], site)
        self.assertEqual(rows[0]["true_shape"], mmap.shapes[site])
        self.assertEqual(rows[0]["read_shape"], "dot")
        self.assertAlmostEqual(rows[0]["theta_deg"], 12.0)


class LayoutTest(unittest.TestCase):
    def test_positions_are_read_from_the_folder_names(self):
        d = tempfile.mkdtemp()
        try:
            for name in ("pos_360", "pos_015", "pos_000", "notes", "pos_x"):
                os.makedirs(os.path.join(d, name))
            got = [(deg, os.path.basename(p)) for deg, p in turn_series.positions(d)]
            self.assertEqual(got, [(0, "pos_000"), (15, "pos_015"), (360, "pos_360")])
        finally:
            shutil.rmtree(d)


class EndToEndTest(unittest.TestCase):
    def test_the_static_fixture_as_a_two_position_series(self):
        # The same static pair saved as position 0 and position 15: the
        # chain runs from folders to the table, and an unturned ball reads
        # as no turn (15 deg error at position 15), not as 15 deg.
        rig = stereo_geometry.load_rig()
        mmap = mark_map.load_map()
        d = tempfile.mkdtemp()
        try:
            for pos in ("pos_000", "pos_015"):
                for cam in ("cam1", "cam2"):
                    img = cv2.imread(os.path.join(FIX, "static_%s.png" % cam))
                    out = os.path.join(d, pos, "raw", cam)
                    os.makedirs(out)
                    for t in ("t000.6000.jpg", "t000.6100.jpg"):
                        cv2.imwrite(os.path.join(out, t), img,
                                    [cv2.IMWRITE_JPEG_QUALITY, 100])
            result = turn_series.run(d, rig, mmap, step=1)
        finally:
            shutil.rmtree(d)
        per = result["positions"]
        self.assertEqual([p["deg"] for p in per], [0, 15])
        oriented = [cam for cam in ("cam1", "cam2") if per[0][cam] is not None]
        self.assertTrue(oriented, per[0])
        for cam in oriented:
            rows = result["series"][cam]["rows"]
            self.assertLess(abs(rows[1]["measured_deg"]), 1.0, rows[1])
            self.assertAlmostEqual(abs(rows[1]["err_deg"]), 15.0, delta=1.0)
        self.assertTrue(result["marks"])


if __name__ == "__main__":
    unittest.main()
