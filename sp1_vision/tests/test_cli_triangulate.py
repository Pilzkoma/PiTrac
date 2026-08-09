#!/usr/bin/env python3
"""Unit tests for cli_triangulate module."""

import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

import cv2
import numpy as np

from sp1_vision import ground_plane, stereo_geometry
from sp1_vision.cli_triangulate import (
    MAX_REPROJECTION_PX,
    _find_max_shot_number,
    _load_manifest,
    _measure_shot,
    _resume_start_number,
    _write_manifest,
    run_analysis,
)
from sp1_vision.tests.test_triangulate import make_rig, project


class TestFindMaxShotNumber(unittest.TestCase):
    """Tests for _find_max_shot_number function."""

    def test_empty_directory(self):
        """Empty directory should return 0."""
        test_dir = tempfile.mkdtemp()
        try:
            self.assertEqual(_find_max_shot_number(test_dir), 0)
        finally:
            shutil.rmtree(test_dir)

    def test_nonexistent_directory(self):
        """Nonexistent directory should return 0."""
        self.assertEqual(_find_max_shot_number("/nonexistent/path"), 0)

    def test_finds_maximum_number(self):
        """Should find the maximum gs_NN number."""
        test_dir = tempfile.mkdtemp()
        try:
            # Create files gs_01, gs_03, gs_10
            for num in [1, 3, 10]:
                with open(os.path.join(test_dir, "gs_{:02d}.png".format(num)), "w") as f:
                    f.write("x")
            self.assertEqual(_find_max_shot_number(test_dir), 10)
        finally:
            shutil.rmtree(test_dir)

    def test_ignores_non_matching_files(self):
        """Should ignore files that don't match gs_NN.png pattern."""
        test_dir = tempfile.mkdtemp()
        try:
            # Create matching and non-matching files
            with open(os.path.join(test_dir, "gs_05.png"), "w") as f:
                f.write("x")
            with open(os.path.join(test_dir, "gs_10.jpg"), "w") as f:
                f.write("x")
            with open(os.path.join(test_dir, "other.png"), "w") as f:
                f.write("x")
            # Should find only gs_05.png
            self.assertEqual(_find_max_shot_number(test_dir), 5)
        finally:
            shutil.rmtree(test_dir)


class TestWriteManifest(unittest.TestCase):
    """Tests for the atomic manifest write."""

    def test_no_tmp_file_left_behind_on_success(self):
        test_dir = tempfile.mkdtemp()
        try:
            shots = [{"name": "gs_01.png", "tape_mm": 350.0, "series": "depth"}]
            _write_manifest(test_dir, shots)

            entries = os.listdir(test_dir)
            self.assertIn("run.json", entries)
            leftover_tmp = [e for e in entries if e.endswith(".tmp")]
            self.assertEqual(leftover_tmp, [])
        finally:
            shutil.rmtree(test_dir)

    def test_previous_manifest_intact_when_write_raises(self):
        test_dir = tempfile.mkdtemp()
        try:
            good_shots = [{"name": "gs_01.png", "tape_mm": 350.0, "series": "depth"}]
            _write_manifest(test_dir, good_shots)

            manifest_path = os.path.join(test_dir, "run.json")
            with open(manifest_path) as fh:
                before = fh.read()

            # A set is not JSON-serializable, so json.dump raises partway
            # through the temp-file write, before os.replace ever runs.
            bad_shots = [{"name": "gs_02.png", "tape_mm": set([1, 2]), "series": "depth"}]
            with self.assertRaises(TypeError):
                _write_manifest(test_dir, bad_shots)

            with open(manifest_path) as fh:
                after = fh.read()
            self.assertEqual(before, after)

            leftover_tmp = [e for e in os.listdir(test_dir) if e.endswith(".tmp")]
            self.assertEqual(leftover_tmp, [])
        finally:
            shutil.rmtree(test_dir)


class TestLoadManifest(unittest.TestCase):
    """Tests for reading run.json back, including corruption handling."""

    def test_missing_manifest_returns_empty_list(self):
        test_dir = tempfile.mkdtemp()
        try:
            self.assertEqual(_load_manifest(test_dir), [])
        finally:
            shutil.rmtree(test_dir)

    def test_roundtrip_through_write_manifest(self):
        test_dir = tempfile.mkdtemp()
        try:
            shots = [
                {"name": "gs_01.png", "tape_mm": 350.0, "series": "depth"},
                {"name": "gs_02.png", "tape_mm": 420.0, "series": "spread"},
                {"name": "gs_03.png", "tape_mm": 490.0, "series": "target"},
            ]
            _write_manifest(test_dir, shots)
            self.assertEqual(_load_manifest(test_dir), shots)
        finally:
            shutil.rmtree(test_dir)

    def test_malformed_json_exits_with_operator_message(self):
        test_dir = tempfile.mkdtemp()
        try:
            with open(os.path.join(test_dir, "run.json"), "w") as fh:
                fh.write("{this is not valid json")

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                with self.assertRaises(SystemExit) as cm:
                    _load_manifest(test_dir)

            self.assertNotEqual(cm.exception.code, 0)
            output = stdout.getvalue()
            self.assertIn(test_dir, output)
            self.assertIn("corrupt or unreadable", output)
        finally:
            shutil.rmtree(test_dir)

    def test_missing_shots_key_exits_with_operator_message(self):
        test_dir = tempfile.mkdtemp()
        try:
            with open(os.path.join(test_dir, "run.json"), "w") as fh:
                json.dump({"not_shots": []}, fh)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                with self.assertRaises(SystemExit) as cm:
                    _load_manifest(test_dir)

            self.assertNotEqual(cm.exception.code, 0)
            output = stdout.getvalue()
            self.assertIn(test_dir, output)
            self.assertIn("corrupt or unreadable", output)
        finally:
            shutil.rmtree(test_dir)


class TestResumeStartNumber(unittest.TestCase):
    """Tests for the max-of-disk-and-manifest resume decision."""

    def _make_cam1(self, test_dir, shot_numbers):
        cam1_dir = os.path.join(test_dir, "cam1")
        os.makedirs(cam1_dir)
        for num in shot_numbers:
            open(os.path.join(cam1_dir, "gs_{:02d}.png".format(num)), "w").close()
        return {1: cam1_dir, 2: os.path.join(test_dir, "cam2")}

    def test_agreement_no_warning(self):
        test_dir = tempfile.mkdtemp()
        try:
            dirs = self._make_cam1(test_dir, [1, 2])
            shots = [{"name": "gs_01.png"}, {"name": "gs_02.png"}]

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                start = _resume_start_number(dirs, shots)

            self.assertEqual(start, 3)
            self.assertNotIn("WARNING", stdout.getvalue())
        finally:
            shutil.rmtree(test_dir)

    def test_disk_ahead_of_manifest_warns_naming_both(self):
        test_dir = tempfile.mkdtemp()
        try:
            dirs = self._make_cam1(test_dir, [1, 2, 3])
            shots = [{"name": "gs_01.png"}, {"name": "gs_02.png"}]  # manifest lost one entry

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                start = _resume_start_number(dirs, shots)

            self.assertEqual(start, 4)
            output = stdout.getvalue()
            self.assertIn("WARNING", output)
            self.assertIn("manifest has 2 shots", output)
            self.assertIn("gs_03", output)
        finally:
            shutil.rmtree(test_dir)

    def test_manifest_ahead_of_disk_warns_naming_both(self):
        test_dir = tempfile.mkdtemp()
        try:
            dirs = self._make_cam1(test_dir, [1])
            shots = [{"name": "gs_01.png"}, {"name": "gs_02.png"}, {"name": "gs_03.png"}]

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                start = _resume_start_number(dirs, shots)

            self.assertEqual(start, 4)
            output = stdout.getvalue()
            self.assertIn("WARNING", output)
            self.assertIn("manifest has 3 shots", output)
            self.assertIn("gs_01", output)
        finally:
            shutil.rmtree(test_dir)


def _frame_with_ball(uv, r=30):
    frame = np.zeros((800, 1280), dtype=np.uint8)
    cv2.circle(frame, (int(round(uv[0])), int(round(uv[1]))), r, 255, -1)
    return cv2.GaussianBlur(frame, (5, 5), 0)


class TestMeasureShot(unittest.TestCase):
    """_measure_shot's accept/reject logic - the depth-sign guard especially.

    The reprojection residual alone does not reliably catch a left/right
    camera swap: on a rig with R = I it is exactly zero for a swapped pair
    (worked through in triangulate.py's module docstring), so _measure_shot
    must also reject on the sign of the triangulated depth, independently
    of the residual check.
    """

    def _write_shot(self, run_dir, name, uv1, uv2, series="depth", tape_mm=500.0):
        for n, uv in ((1, uv1), (2, uv2)):
            cam_dir = os.path.join(run_dir, "cam{}".format(n))
            os.makedirs(cam_dir, exist_ok=True)
            cv2.imwrite(os.path.join(cam_dir, name), _frame_with_ball(uv))
        return {"name": name, "tape_mm": tape_mm, "series": series}

    def test_accepts_a_consistent_shot(self):
        rig = make_rig(pitch_deg=-0.94)
        truth = np.array([0.02, 0.09, 0.5])
        uv1, uv2 = project(rig, truth)
        run_dir = tempfile.mkdtemp()
        try:
            shot = self._write_shot(run_dir, "gs_01.png", uv1, uv2)
            xyz, info = _measure_shot(rig, run_dir, shot)
            self.assertIsNotNone(xyz)
            np.testing.assert_allclose(xyz, truth, atol=0.005)
            self.assertLessEqual(info, MAX_REPROJECTION_PX)
        finally:
            shutil.rmtree(run_dir)

    def test_rejects_a_swap_via_depth_sign_when_residual_is_silent(self):
        # R = I rig: a swapped pair reprojects with exactly zero residual,
        # so only the depth-sign check can catch it here.
        rig = make_rig(pitch_deg=0.0)
        truth = np.array([0.02, 0.09, 0.5])
        uv1, uv2 = project(rig, truth)
        run_dir = tempfile.mkdtemp()
        try:
            shot = self._write_shot(run_dir, "gs_swap.png", uv2, uv1)  # swapped
            xyz, reason = _measure_shot(rig, run_dir, shot)
            self.assertIsNone(xyz)
            self.assertIn("behind camera 1", reason)
        finally:
            shutil.rmtree(run_dir)

    def test_rejects_a_high_residual_shot(self):
        rig = make_rig(pitch_deg=-0.94)
        # cam1 sees one point, cam2 sees an unrelated one - a wrong
        # correspondence, not merely a slightly-off detection.
        uv1, _ = project(rig, np.array([0.02, 0.09, 0.5]))
        _, uv2 = project(rig, np.array([-0.20, -0.05, 1.5]))
        run_dir = tempfile.mkdtemp()
        try:
            shot = self._write_shot(run_dir, "gs_bad.png", uv1, uv2)
            xyz, reason = _measure_shot(rig, run_dir, shot)
            self.assertIsNone(xyz)
            self.assertIn("reproj", reason)
        finally:
            shutil.rmtree(run_dir)

    def test_missing_image_reports_the_path(self):
        rig = make_rig()
        run_dir = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(run_dir, "cam1"))
            os.makedirs(os.path.join(run_dir, "cam2"))
            shot = {"name": "nope.png", "tape_mm": 1.0, "series": "depth"}
            xyz, reason = _measure_shot(rig, run_dir, shot)
            self.assertIsNone(xyz)
            self.assertIn("missing", reason)
            self.assertIn("nope.png", reason)
        finally:
            shutil.rmtree(run_dir)

    def test_no_ball_detected_names_the_camera(self):
        rig = make_rig()
        run_dir = tempfile.mkdtemp()
        try:
            blank = np.zeros((800, 1280), dtype=np.uint8)
            os.makedirs(os.path.join(run_dir, "cam1"))
            os.makedirs(os.path.join(run_dir, "cam2"))
            cv2.imwrite(os.path.join(run_dir, "cam1", "gs_01.png"), blank)
            cv2.imwrite(os.path.join(run_dir, "cam2", "gs_01.png"), blank)
            shot = {"name": "gs_01.png", "tape_mm": 1.0, "series": "depth"}
            xyz, reason = _measure_shot(rig, run_dir, shot)
            self.assertIsNone(xyz)
            self.assertIn("cam1", reason)
        finally:
            shutil.rmtree(run_dir)


class RunAnalysisTest(unittest.TestCase):
    """run_analysis end to end: the properties this task exists for.

    stereo_geometry.load_rig is resolved as a module attribute of
    cli_triangulate at call time, so it can be patched there without any
    production change - no dependency injection needed. Everything else
    (image files, run.json, the printed output) is exercised for real.
    """

    def _write(self, run_dir, name, uv1, uv2):
        for n, uv in ((1, uv1), (2, uv2)):
            cam_dir = os.path.join(run_dir, "cam{}".format(n))
            os.makedirs(cam_dir, exist_ok=True)
            cv2.imwrite(os.path.join(cam_dir, name), _frame_with_ball(uv))

    def test_routing_all_four_rejections_and_config_block(self):
        # R = I: the swap shot below is residual-silent here, so its
        # rejection can only come from the depth-sign check - the property
        # this task's addendum is about.
        rig = make_rig(pitch_deg=0.0)
        run_dir = tempfile.mkdtemp()
        try:
            shots = []

            # depth series: 4 collinear points (X, Y fixed; only Z moves),
            # so the true 3D displacement between consecutive points equals
            # the tape gap exactly, and the fitted scale should land near 1.
            depth_truth = [
                (np.array([0.03, 0.09, 0.35]), 350.0),
                (np.array([0.03, 0.09, 0.42]), 420.0),
                (np.array([0.03, 0.09, 0.49]), 490.0),
                (np.array([0.03, 0.09, 0.56]), 560.0),
            ]
            for i, (xyz, tape) in enumerate(depth_truth, start=1):
                name = "gs_depth_{:02d}.png".format(i)
                self._write(run_dir, name, *project(rig, xyz))
                shots.append({"name": name, "tape_mm": tape, "series": "depth"})

            # (a) One accepted spread shot, tagged with a tape_mm that would
            # visibly wreck the scale fit if it ever leaked into the depth
            # bucket: a huge, unrelated "gap". buckets["spread"] must never
            # reach the scale fit for this to stay near 1.0 below.
            spread_xyz = np.array([-0.20, 0.09, 0.40])
            self._write(run_dir, "gs_spread.png", *project(rig, spread_xyz))
            shots.append({"name": "gs_spread.png", "tape_mm": 9999.0,
                         "series": "spread"})

            # target series: 2 points, needed for the config block's pan.
            target_truth = [
                (np.array([0.0, 0.09, 0.40]), 400.0),
                (np.array([0.0, 0.09, 0.60]), 600.0),
            ]
            for i, (xyz, tape) in enumerate(target_truth, start=1):
                name = "gs_target_{}.png".format(i)
                self._write(run_dir, name, *project(rig, xyz))
                shots.append({"name": name, "tape_mm": tape, "series": "target"})

            # (b) Rejection 1: missing file - no image ever written for this name.
            shots.append({"name": "gs_missing.png", "tape_mm": 1.0,
                         "series": "depth"})

            # (b) Rejection 2: no ball - both frames blank.
            blank = np.zeros((800, 1280), dtype=np.uint8)
            for n in (1, 2):
                cam_dir = os.path.join(run_dir, "cam{}".format(n))
                os.makedirs(cam_dir, exist_ok=True)
                cv2.imwrite(os.path.join(cam_dir, "gs_blank.png"), blank)
            shots.append({"name": "gs_blank.png", "tape_mm": 1.0,
                         "series": "depth"})

            # (b) Rejection 3: high residual - an unrelated correspondence,
            # not a swap of a real point.
            bad_uv1, _ = project(rig, np.array([0.02, 0.09, 0.5]))
            _, bad_uv2 = project(rig, np.array([-0.20, -0.05, 1.5]))
            self._write(run_dir, "gs_bad.png", bad_uv1, bad_uv2)
            shots.append({"name": "gs_bad.png", "tape_mm": 1.0, "series": "depth"})

            # (b) Rejection 4: swapped correspondence of a REAL point, on
            # this R = I rig - zero residual, negative depth.
            suv1, suv2 = project(rig, np.array([0.02, 0.09, 0.5]))
            self._write(run_dir, "gs_swap.png", suv2, suv1)  # swapped
            shots.append({"name": "gs_swap.png", "tape_mm": 1.0, "series": "depth"})

            with open(os.path.join(run_dir, "run.json"), "w") as fh:
                json.dump({"shots": shots}, fh)

            stdout = io.StringIO()
            with mock.patch("sp1_vision.cli_triangulate.stereo_geometry.load_rig",
                            return_value=rig):
                with redirect_stdout(stdout):
                    rc = run_analysis(run_dir, "unused", "unused")
            output = stdout.getvalue()

            self.assertEqual(rc, 0, output)

            # (a) routing: the spread shot's absurd tape value did not
            # reach the scale fit - if it had, scale would be nowhere near
            # 1.0. buckets["spread"] is written to in exactly one place in
            # cli_triangulate.py, and depth_ordered is built from
            # buckets["depth"] alone.
            scale_line = next(
                l for l in output.splitlines()
                if l.strip().startswith("scale against tape:"))
            scale_value = float(scale_line.split(":")[1].split()[0])
            self.assertAlmostEqual(scale_value, 1.0, delta=0.05)

            # (b) all four rejection reasons appear, distinguishably.
            self.assertIn("missing", output)
            self.assertIn("no ball in cam", output)
            self.assertIn("reproj", output)
            self.assertIn("behind camera 1", output)

            # (c) the measurement is reported as a result in its own right,
            # separate from and before any PiTrac mapping.
            self.assertIn("measured attitude of the unit", output)
            self.assertIn("nose-up positive", output)
            self.assertIn("right-side-down positive", output)
            attitude_pos = output.index("measured attitude of the unit")
            mapping_pos = output.index("writing this into PiTrac's kCameraNAngles")
            self.assertLess(attitude_pos, mapping_pos)

            # (d) the PiTrac mapping section prints, explicitly labelled as
            # an inheritance and explicitly lossy, with the pan/tilt/roll
            # notes and the Block 2 forward-pointer.
            self.assertIn('"kCamera2OffsetFromCamera1OriginMeters"', output)
            self.assertIn('"kCamera1Angles"', output)
            self.assertIn("SIGN UNVERIFIED", output)
            self.assertIn("DROPPED", output)
            self.assertIn("Block 2 should carry the attitude as a full "
                          "rotation", output)
        finally:
            shutil.rmtree(run_dir)

    def test_reports_a_stereo_rig_error_without_a_traceback(self):
        # If this were not caught inside run_analysis, StereoRigError would
        # propagate out of run_analysis and this test itself would fail
        # with an unhandled exception rather than reach the assertions
        # below - that failure mode is exactly what the catch prevents.
        run_dir = tempfile.mkdtemp()
        try:
            stdout = io.StringIO()
            with mock.patch(
                    "sp1_vision.cli_triangulate.stereo_geometry.load_rig",
                    side_effect=stereo_geometry.StereoRigError("bad baseline")):
                with redirect_stdout(stdout):
                    rc = run_analysis(run_dir, "unused", "unused")
            self.assertEqual(rc, 1)
            self.assertIn("bad baseline", stdout.getvalue())
        finally:
            shutil.rmtree(run_dir)

    def test_reports_a_plane_fit_error_without_a_traceback(self):
        # Same shape of guard, for the plane fit. fit_plane is mocked
        # directly rather than engineered via near-collinear geometry, to
        # keep this test about the catch, not about conditioning.
        rig = make_rig(pitch_deg=0.0)
        run_dir = tempfile.mkdtemp()
        try:
            floor_truth = [
                np.array([0.03, 0.09, 0.35]),
                np.array([-0.20, 0.09, 0.40]),
                np.array([0.20, 0.09, 0.45]),
            ]
            shots = []
            for i, xyz in enumerate(floor_truth, start=1):
                name = "gs_{:02d}.png".format(i)
                self._write(run_dir, name, *project(rig, xyz))
                shots.append({"name": name, "tape_mm": 400.0 + i,
                             "series": "depth" if i == 1 else "spread"})
            with open(os.path.join(run_dir, "run.json"), "w") as fh:
                json.dump({"shots": shots}, fh)

            stdout = io.StringIO()
            with mock.patch(
                    "sp1_vision.cli_triangulate.stereo_geometry.load_rig",
                    return_value=rig):
                with mock.patch(
                        "sp1_vision.cli_triangulate.ground_plane.fit_plane",
                        side_effect=ground_plane.PlaneFitError("near-collinear")):
                    with redirect_stdout(stdout):
                        rc = run_analysis(run_dir, "unused", "unused")
            self.assertEqual(rc, 1)
            self.assertIn("near-collinear", stdout.getvalue())
        finally:
            shutil.rmtree(run_dir)


if __name__ == "__main__":
    unittest.main()
