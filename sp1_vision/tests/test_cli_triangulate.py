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

from sp1_vision import ball_pair, ground_plane, stereo_geometry
from sp1_vision.ball_pair import MAX_REPROJECTION_PX
from sp1_vision.cli_triangulate import (
    _find_max_shot_number,
    _load_manifest,
    _measure_shot,
    _report_completeness,
    _resume_start_number,
    _usable_counts,
    _write_manifest,
    main,
    run_analysis,
)
from sp1_vision.tests.test_ball_pair import ball_discs, frame_with_disc
from sp1_vision.tests.test_triangulate import make_rig, project

# Camera 1 sits this far above the floor on the real unit, per the spec. The
# fixtures below use it so the height the analysis reports back can be checked
# against a number that was decided elsewhere.
MOUNT_HEIGHT_M = 0.115


def floor_seen_by_a_tilted_camera(pitch_deg, height_m=MOUNT_HEIGHT_M,
                                  xs=(-0.15, 0.0, 0.15),
                                  depths=(0.38, 0.52, 0.66)):
    """Resting-ball centres on a LEVEL floor, in a pitched camera's frame.

    Built from the physical description rather than reusing
    test_ground_plane.floor_points, deliberately: the pitch sign inversion
    caught earlier in this block had its root cause inside that fixture, so
    a test of the sign convention that borrows it can agree with it and
    still be wrong. Two independent constructions that agree are evidence;
    one construction checked against itself is not.

    World frame with a level camera at the origin: X right, Y DOWN, Z
    forward. The floor is height_m below, and a resting ball's centre is one
    radius above the floor. Pitching the CAMERA nose-up by theta about +X
    (which takes its forward axis +Z toward negative Y, i.e. upward) leaves
    the world-fixed points where they are and re-expresses them in the
    rotated frame - that is Rx(theta)^T = Rx(-theta) applied to each point.

    xs and depths are kept well inside the 1280x800 frame at both cameras:
    the stereo offset shifts camera 2's view by about 190 px at these
    distances, so the far right column has to leave room for it.
    """
    y = height_m - ground_plane.GOLF_BALL_RADIUS_M
    world = np.array([[x, y, d] for d in depths for x in xs])
    t = np.radians(pitch_deg)
    rx_inverse = np.array([[1.0, 0.0, 0.0],
                           [0.0, np.cos(t), np.sin(t)],
                           [0.0, -np.sin(t), np.cos(t)]])
    return world @ rx_inverse.T


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


class TestManifestValidation(unittest.TestCase):
    """A parseable manifest with a structurally wrong entry.

    Hand-editing run.json is exactly what the resume warning invites, so the
    common damage is not broken JSON but a missing field. Left unchecked
    that surfaces as a bare KeyError partway down the analysis table, a long
    way from the run directory that caused it.
    """

    def _load_expecting_exit(self, shots):
        test_dir = tempfile.mkdtemp()
        try:
            with open(os.path.join(test_dir, "run.json"), "w") as fh:
                json.dump({"shots": shots}, fh)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                with self.assertRaises(SystemExit) as cm:
                    _load_manifest(test_dir)
            self.assertNotEqual(cm.exception.code, 0)
            return stdout.getvalue(), test_dir
        finally:
            shutil.rmtree(test_dir)

    def test_entry_without_tape_mm_is_refused_by_name(self):
        output, test_dir = self._load_expecting_exit([
            {"name": "gs_01.png", "tape_mm": 350.0, "series": "depth"},
            {"name": "gs_02.png", "series": "depth"},
        ])
        self.assertIn(test_dir, output)
        self.assertIn("gs_02.png", output)
        self.assertIn("tape_mm", output)

    def test_entry_with_a_string_tape_reading_is_refused(self):
        # "420" out of a text editor is the natural hand-edit, and it would
        # otherwise reach the arithmetic and fail there instead of here.
        output, _ = self._load_expecting_exit([
            {"name": "gs_01.png", "tape_mm": "420", "series": "depth"},
        ])
        self.assertIn("tape_mm", output)

    def test_a_non_object_entry_is_refused(self):
        output, _ = self._load_expecting_exit(["gs_01.png"])
        self.assertIn("not an object", output)

    def test_shots_that_is_not_a_list_is_refused(self):
        output, _ = self._load_expecting_exit({"gs_01.png": 350.0})
        self.assertIn("corrupt or unreadable", output)

    def test_a_complete_manifest_with_found_flags_loads(self):
        test_dir = tempfile.mkdtemp()
        try:
            shots = [{"name": "gs_01.png", "tape_mm": 350.0,
                      "series": "depth", "found": True}]
            _write_manifest(test_dir, shots)
            self.assertEqual(_load_manifest(test_dir), shots)
        finally:
            shutil.rmtree(test_dir)


class TestCompletenessGate(unittest.TestCase):
    """What the operator is allowed to pack up on.

    The gate this replaces passed a 6-depth / 2-target / 0-spread series -
    depth >= 4, target >= 2, depth + spread >= 3 all satisfied - and that
    series is a LINE. fit_plane refuses it, and pitch, roll and yaw are lost
    together, after the unit has been moved and the floor marks swept up.
    """

    def _shots(self, depth=0, spread=0, target=0, found=True):
        out = []
        for label, n in (("depth", depth), ("spread", spread),
                         ("target", target)):
            for i in range(n):
                out.append({"name": "gs_{}_{}.png".format(label, i),
                            "tape_mm": 350.0 + 70 * i, "series": label,
                            "found": found})
        return out

    def _run(self, shots):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            rc = _report_completeness(shots)
        return rc, stdout.getvalue()

    def test_six_depth_and_two_target_with_no_spread_is_refused(self):
        rc, output = self._run(self._shots(depth=6, target=2))
        self.assertEqual(rc, 1)
        self.assertIn("INCOMPLETE", output)
        self.assertIn("spread", output)
        # The message must say what spread is FOR, since the operator's
        # obvious reading of "not enough" is "take more shots".
        self.assertIn("LATERAL", output)
        self.assertIn("image width", output)
        self.assertIn("collinear by design", output)

    def test_a_complete_series_passes(self):
        rc, output = self._run(self._shots(depth=6, spread=4, target=2))
        self.assertEqual(rc, 0)
        self.assertNotIn("INCOMPLETE", output)

    def test_one_spread_position_is_still_refused(self):
        rc, _ = self._run(self._shots(depth=6, spread=1, target=2))
        self.assertEqual(rc, 1)

    def test_shots_with_no_ball_do_not_count_toward_the_gate(self):
        # The capture loop prints "MOVE THE BALL AND RETAKE" and used to
        # throw that verdict away, so a series of unusable frames counted as
        # complete.
        shots = self._shots(depth=6, spread=4, target=2, found=False)
        rc, output = self._run(shots)
        self.assertEqual(rc, 1)
        self.assertIn("0 usable", output)
        self.assertIn("12 shots on disk", output)

    def test_legacy_entries_without_found_are_counted_as_usable(self):
        shots = self._shots(depth=6, spread=4, target=2)
        for shot in shots:
            del shot["found"]
        self.assertEqual(_usable_counts(shots),
                         {"depth": 6, "spread": 4, "target": 2})

    def test_mixed_found_flags_are_counted_individually(self):
        shots = self._shots(depth=4, spread=2, target=2)
        shots[0]["found"] = False
        shots[4]["found"] = False
        self.assertEqual(_usable_counts(shots),
                         {"depth": 3, "spread": 1, "target": 2})


class TestArgparseHelp(unittest.TestCase):
    def test_every_option_documents_itself(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            with self.assertRaises(SystemExit):
                main(["--help"])
        output = stdout.getvalue()
        for flag in ("--shots", "--out", "--exposure", "--analyse",
                     "--extrinsics", "--config"):
            self.assertIn(flag, output)
        # The two that used to appear bare.
        self.assertIn("stereo_extrinsics.json", output)
        self.assertIn("golf_sim_config.json", output)
        self.assertIn("never writes", output)


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


# One renderer for the whole suite, in test_ball_pair. Drawing a disc twice
# in two files is two chances to round the centre to whole pixels, and that
# rounding put a systematic +1.45 mm into every synthetic depth - a bias
# that reads as a scale error, which is exactly what these tests measure.
_frame_with_disc = frame_with_disc


def ball_frames(rig, xyz):
    """A stereo pair showing the ball at its true position AND true size.

    The size is not decoration. Every fixture here used to draw a 30 px disc
    whatever the distance, which is a ball of a different diameter at every
    depth - and the selector now checks apparent size against the range its
    own disparity implies, exactly so that a background object cannot pass.
    A fixture that lies about size cannot exercise that check, and would
    quietly stop testing it.

    ball_discs comes from test_ball_pair rather than being written again
    here: two copies of the projection-and-size model would be two chances
    to get it wrong, and a fixture bug is invisible in a green suite.
    """
    d1, d2 = ball_discs(rig, xyz)
    return _frame_with_disc(*d1), _frame_with_disc(*d2)


class TestMeasureShot(unittest.TestCase):
    """_measure_shot's accept/reject logic, now that the choice is a PAIR.

    The detection decision moved into ball_pair, where the rig is, because a
    single image cannot tell a golf ball from a loudspeaker cone - it cost a
    whole 24-shot run to establish that. What stays here is what belongs to
    the file layer: reading the two frames, refusing a frame at the wrong
    resolution, and turning whatever ball_pair says into one table row
    rather than a traceback that takes the other rows with it.
    """

    def _write_frames(self, run_dir, name, frame1, frame2,
                      series="depth", tape_mm=500.0):
        for n, frame in ((1, frame1), (2, frame2)):
            cam_dir = os.path.join(run_dir, "cam{}".format(n))
            os.makedirs(cam_dir, exist_ok=True)
            cv2.imwrite(os.path.join(cam_dir, name), frame)
        return {"name": name, "tape_mm": tape_mm, "series": series}

    def _write_ball(self, run_dir, name, rig, xyz, **kw):
        return self._write_frames(run_dir, name, *ball_frames(rig, xyz), **kw)

    def test_accepts_a_consistent_shot(self):
        rig = make_rig(pitch_deg=-0.94)
        truth = np.array([0.02, 0.09, 0.5])
        run_dir = tempfile.mkdtemp()
        try:
            shot = self._write_ball(run_dir, "gs_01.png", rig, truth)
            xyz, info = _measure_shot(rig, run_dir, shot)
            self.assertIsNotNone(xyz, info)
            np.testing.assert_allclose(xyz, truth, atol=0.005)
            self.assertLessEqual(info, MAX_REPROJECTION_PX)
        finally:
            shutil.rmtree(run_dir)

    def test_rejects_a_swap_even_when_the_residual_is_silent(self):
        # R = I rig: a swapped pair reprojects with exactly zero residual, so
        # the residual cannot catch it. The measurement volume is stated in
        # positive metres, which makes the rejection structural rather than a
        # threshold that could be tuned away.
        rig = make_rig(pitch_deg=0.0)
        truth = np.array([0.02, 0.09, 0.5])
        frame1, frame2 = ball_frames(rig, truth)
        run_dir = tempfile.mkdtemp()
        try:
            shot = self._write_frames(run_dir, "gs_swap.png", frame2, frame1)
            xyz, reason = _measure_shot(rig, run_dir, shot)
            self.assertIsNone(xyz, "swapped pair accepted as {}".format(xyz))
            self.assertIsInstance(reason, str)
        finally:
            shutil.rmtree(run_dir)

    def test_rejects_an_unrelated_correspondence(self):
        rig = make_rig(pitch_deg=-0.94)
        # cam1 sees a ball at one place, cam2 a ball somewhere else entirely.
        near, _ = ball_frames(rig, np.array([0.02, 0.09, 0.5]))
        _, far = ball_frames(rig, np.array([-0.20, -0.05, 0.9]))
        run_dir = tempfile.mkdtemp()
        try:
            shot = self._write_frames(run_dir, "gs_bad.png", near, far)
            xyz, reason = _measure_shot(rig, run_dir, shot)
            self.assertIsNone(xyz)
            self.assertIsInstance(reason, str)
        finally:
            shutil.rmtree(run_dir)

    def test_rejects_an_object_of_the_wrong_size_for_its_distance(self):
        # The gate the old per-image detector could not have: a disc pair
        # whose disparity is perfectly consistent and puts it inside the
        # measurement volume, but which is a quarter too large to be a
        # 42.67 mm ball there. Two background objects in the 2026-08-10 run
        # cleared every other check and failed only on this.
        rig = make_rig(pitch_deg=-0.94)
        (u1, v1, r1), (u2, v2, r2) = ball_discs(rig, np.array([0.0, 0.09, 0.5]))
        run_dir = tempfile.mkdtemp()
        try:
            shot = self._write_frames(
                run_dir, "gs_big.png",
                _frame_with_disc(u1, v1, r1 * 1.25),
                _frame_with_disc(u2, v2, r2 * 1.25))
            xyz, reason = _measure_shot(rig, run_dir, shot)
            self.assertIsNone(xyz)
            self.assertIn("size", reason.lower())
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

    def test_degenerate_rays_are_a_reason_not_a_traceback(self):
        # The same disc at the same pixel in both cameras on an R = I rig
        # gives two parallel rays that never meet - which is also what a
        # distant background object looks like. Uncaught, the raise takes
        # the whole table down including the rows already measured; handled,
        # it costs one row.
        rig = make_rig(pitch_deg=0.0)
        run_dir = tempfile.mkdtemp()
        try:
            same = _frame_with_disc(700.0, 450.0, 38.0)
            shot = self._write_frames(run_dir, "gs_par.png", same, same.copy())
            xyz, reason = _measure_shot(rig, run_dir, shot)
            self.assertIsNone(xyz)
            self.assertIsInstance(reason, str)
        finally:
            shutil.rmtree(run_dir)

    def test_a_frame_at_the_wrong_resolution_is_rejected(self):
        # calibration_capture sets the resolution best-effort and warns in
        # its own docstring that negotiation can fall back. If it did, every
        # intrinsic is wrong for these frames, and validate_rig cannot see
        # it: load_rig never sets image_size, so that check compares the
        # default against itself. The frames are what has to be checked.
        rig = make_rig()
        run_dir = tempfile.mkdtemp()
        try:
            small = np.zeros((400, 640), dtype=np.uint8)
            cv2.circle(small, (320, 200), 30, 255, -1)
            for n in (1, 2):
                cam_dir = os.path.join(run_dir, "cam{}".format(n))
                os.makedirs(cam_dir)
                cv2.imwrite(os.path.join(cam_dir, "gs_01.png"), small)
            shot = {"name": "gs_01.png", "tape_mm": 500.0, "series": "depth"}
            xyz, reason = _measure_shot(rig, run_dir, shot)
            self.assertIsNone(xyz)
            self.assertIn("640x400", reason)
            self.assertIn("1280x800", reason)
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

    def _write(self, run_dir, name, disc1, disc2):
        """Write one stereo pair, each disc at its own true apparent size.

        Takes (u, v, r) rather than (u, v): the selector checks apparent
        size against the range the disparity implies, so a fixture that
        draws every ball 30 px wide would stop exercising that check
        without any test going red.
        """
        for n, disc in ((1, disc1), (2, disc2)):
            cam_dir = os.path.join(run_dir, "cam{}".format(n))
            os.makedirs(cam_dir, exist_ok=True)
            cv2.imwrite(os.path.join(cam_dir, name), _frame_with_disc(*disc))

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
                self._write(run_dir, name, *ball_discs(rig, xyz))
                shots.append({"name": name, "tape_mm": tape, "series": "depth"})

            # (a) One accepted spread shot, tagged with a tape_mm that would
            # visibly wreck the scale fit if it ever leaked into the depth
            # bucket: a huge, unrelated "gap". buckets["spread"] must never
            # reach the scale fit for this to stay near 1.0 below.
            spread_xyz = np.array([-0.20, 0.09, 0.40])
            self._write(run_dir, "gs_spread.png", *ball_discs(rig, spread_xyz))
            shots.append({"name": "gs_spread.png", "tape_mm": 9999.0,
                         "series": "spread"})

            # target series: 2 points, needed for the config block's pan.
            target_truth = [
                (np.array([0.0, 0.09, 0.40]), 400.0),
                (np.array([0.0, 0.09, 0.60]), 600.0),
            ]
            for i, (xyz, tape) in enumerate(target_truth, start=1):
                name = "gs_target_{}.png".format(i)
                self._write(run_dir, name, *ball_discs(rig, xyz))
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
            bad_disc1, _ = ball_discs(rig, np.array([0.02, 0.09, 0.5]))
            _, bad_disc2 = ball_discs(rig, np.array([-0.20, -0.05, 0.9]))
            self._write(run_dir, "gs_bad.png", bad_disc1, bad_disc2)
            shots.append({"name": "gs_bad.png", "tape_mm": 1.0, "series": "depth"})

            # (b) Rejection 4: swapped correspondence of a REAL point, on
            # this R = I rig - zero residual, negative depth.
            sdisc1, sdisc2 = ball_discs(rig, np.array([0.02, 0.09, 0.5]))
            self._write(run_dir, "gs_swap.png", sdisc2, sdisc1)  # swapped
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

            # (b) every rejection reason appears, and they stay
            # distinguishable. The wording moved when the decision became a
            # PAIR decision, but the property did not: an operator reading
            # this table has to be able to tell a missing file from an empty
            # frame from a swap, because the three call for entirely
            # different responses.
            self.assertIn("missing", output)
            self.assertIn("no circle at all", output)
            self.assertIn("no ball-consistent pair", output)
            self.assertIn("swap", output)

            # (c) the measurement is reported as a result in its own right,
            # separate from and before any PiTrac mapping.
            self.assertIn("measured attitude of the unit", output)
            self.assertIn("nose-up positive", output)
            self.assertIn("right-side-down positive", output)

            # yaw's sign sense is opposite to pitch's and roll's - it is the
            # target line's bearing, not the camera's rotation - and all
            # three sit under one "attitude" header, so the difference is
            # stated rather than left to be inferred.
            self.assertIn("yaw sign is not the same sense", output)
            self.assertIn("NEGATION of the unit's own yaw", output)

            # The mounting height, measured from the same plane fit. The
            # fixture's ball centres are at Y = 0.09, one radius under
            # 111 mm.
            height_line = next(l for l in output.splitlines()
                               if "above the floor" in l)
            height_mm = float(height_line.split("sits")[1].split("mm")[0])
            self.assertAlmostEqual(height_mm, 111.3, delta=3.0)
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
            # Camera 2's angles differ from camera 1's by the inter-camera
            # rotation, about a degree here. Only camera 1's is printed, so
            # the output has to say that copying it into kCamera2Angles puts
            # that degree straight into HLA and VLA.
            self.assertIn("kCamera2Angles is deliberately NOT printed", output)
            self.assertIn("Block 2 should carry the attitude as a full "
                          "rotation", output)
        finally:
            shutil.rmtree(run_dir)

    def _run_analysis(self, run_dir, rig, shots):
        with open(os.path.join(run_dir, "run.json"), "w") as fh:
            json.dump({"shots": shots}, fh)
        stdout = io.StringIO()
        with mock.patch("sp1_vision.cli_triangulate.stereo_geometry.load_rig",
                        return_value=rig):
            with redirect_stdout(stdout):
                rc = run_analysis(run_dir, "unused", "unused")
        return rc, stdout.getvalue()

    @staticmethod
    def _printed_angle(output, label):
        line = next(l for l in output.splitlines()
                    if l.strip().startswith(label + " "))
        return float(line.split()[1])

    def test_measures_a_known_non_zero_attitude_end_to_end(self):
        """project -> detect -> triangulate -> fit -> print, at 3 deg of pitch.

        Every other attitude test feeds ground_plane.floor_points straight
        into fit_plane, and every other run_analysis test uses a level
        floor - so the full chain had never once run at a known non-zero
        attitude. The pitch sign inversion caught earlier in this block had
        its root cause in floor_points itself, which is exactly the seam a
        test built only on that fixture cannot see. Here the points go
        through real projection and real Hough detection, and the assertion
        is on the number the operator reads.
        """
        rig = make_rig(pitch_deg=-0.94)
        run_dir = tempfile.mkdtemp()
        try:
            # Nine floor positions seen by a camera pitched 3 deg nose-up,
            # laid out so they span the image width - three across at each of
            # three depths - which is what makes the plane determined.
            points = floor_seen_by_a_tilted_camera(3.0)
            shots = []
            for i, xyz in enumerate(points, start=1):
                name = "gs_{:02d}.png".format(i)
                self._write(run_dir, name, *ball_discs(rig, xyz))
                shots.append({"name": name, "tape_mm": 350.0 + 40.0 * i,
                              "series": "depth" if i % 3 == 0 else "spread",
                              "found": True})

            rc, output = self._run_analysis(run_dir, rig, shots)
            self.assertEqual(rc, 0, output)

            pitch = self._printed_angle(output, "pitch")
            # Positive, and near 3 deg. Hough quantises the centres to about
            # a pixel, worth roughly 0.2 deg here - ample margin to catch a
            # sign flip, which would land at -3.
            self.assertGreater(pitch, 0.0, output)
            self.assertAlmostEqual(pitch, 3.0, delta=0.5)
            self.assertAlmostEqual(self._printed_angle(output, "roll"), 0.0,
                                   delta=0.5)

            # The height falls out of the same fit, and the fixture puts the
            # camera at the spec's 115 mm.
            height_line = next(l for l in output.splitlines()
                               if "above the floor" in l)
            height_mm = float(height_line.split("sits")[1].split("mm")[0])
            self.assertAlmostEqual(height_mm, MOUNT_HEIGHT_M * 1000.0, delta=3.0)
        finally:
            shutil.rmtree(run_dir)

    def test_a_nose_up_camera_really_does_see_the_floor_lower(self):
        # Anchors the fixture above to something physical rather than to
        # another fixture: tilting a camera upward pushes the floor DOWN the
        # image. If floor_seen_by_a_tilted_camera had the rotation the wrong
        # way round, the attitude tests would still agree with it - this is
        # what stops that.
        level = floor_seen_by_a_tilted_camera(0.0)
        nose_up = floor_seen_by_a_tilted_camera(3.0)
        rig = make_rig(pitch_deg=0.0)
        for a, b in zip(level, nose_up):
            v_level = project(rig, a)[0][1]
            v_nose_up = project(rig, b)[0][1]
            self.assertGreater(v_nose_up, v_level)

    def test_measures_a_known_negative_pitch_end_to_end(self):
        # The counter-case, so the assertion above is about the sign and not
        # about the magnitude happening to be positive.
        rig = make_rig(pitch_deg=-0.94)
        run_dir = tempfile.mkdtemp()
        try:
            points = floor_seen_by_a_tilted_camera(-3.0)
            shots = []
            for i, xyz in enumerate(points, start=1):
                name = "gs_{:02d}.png".format(i)
                self._write(run_dir, name, *ball_discs(rig, xyz))
                shots.append({"name": name, "tape_mm": 350.0 + 40.0 * i,
                              "series": "depth" if i % 3 == 0 else "spread",
                              "found": True})
            rc, output = self._run_analysis(run_dir, rig, shots)
            self.assertEqual(rc, 0, output)
            self.assertAlmostEqual(self._printed_angle(output, "pitch"), -3.0,
                                   delta=0.5)
        finally:
            shutil.rmtree(run_dir)

    def _wandering_depth_series(self, rig, run_dir, lateral_mm):
        """A depth line with a sideways wobble, laid at the tape's gaps.

        Each position is exactly its tape reading in DEPTH, so the honest
        answer is scale = 1 whatever the lateral wander does. A fit on the
        3D separation instead reads the wander as extra length and returns a
        scale above 1 - which prints a SMALLER implied baseline and pushes
        the 78.28-against-78.749 answer one way only.
        """
        shots = []
        for i, tape in enumerate([350.0, 420.0, 490.0, 560.0, 630.0]):
            x = 0.0 if i % 2 == 0 else lateral_mm / 1000.0
            name = "gs_d{:02d}.png".format(i)
            self._write(run_dir, name, *ball_discs(
                rig, np.array([x, 0.0937, tape / 1000.0])))
            shots.append({"name": name, "tape_mm": tape, "series": "depth",
                          "found": True})
        # Two spread positions, so the plane is determined.
        for i, (x, z) in enumerate(((-0.22, 0.40), (0.22, 0.60))):
            name = "gs_s{}.png".format(i)
            self._write(run_dir, name, *ball_discs(rig, np.array([x, 0.0937, z])))
            shots.append({"name": name, "tape_mm": z * 1000.0,
                          "series": "spread", "found": True})
        return shots

    def test_scale_is_immune_to_lateral_wander_in_the_depth_line(self):
        # 40 mm of side-to-side wander on 70 mm gaps. Measured as a 3D
        # separation each gap reads sqrt(70^2 + 40^2) = 80.6 mm, a scale of
        # 1.15 - and a scale above 1 prints a SMALLER implied baseline, so
        # the error pushes toward 78.28 and away from 78.749 on a question
        # whose whole signal is 0.6%. Measured as a depth difference the
        # wander contributes exactly nothing.
        #
        # 40 mm rather than a realistic 5 mm because the deviation has to
        # clear Hough's own noise: it quantises the centres to about a
        # pixel, which is +-5 mm of depth at the far end of this series and
        # leaves roughly 1% of slack in the fitted scale. A 5 mm wander
        # (+0.26%) would sit inside that and the test would prove nothing.
        rig = make_rig(pitch_deg=-0.94)
        run_dir = tempfile.mkdtemp()
        try:
            shots = self._wandering_depth_series(rig, run_dir, lateral_mm=40.0)
            rc, output = self._run_analysis(run_dir, rig, shots)
            self.assertEqual(rc, 0, output)

            scale_line = next(l for l in output.splitlines()
                              if l.strip().startswith("scale against tape:"))
            scale = float(scale_line.split(":")[1].split()[0])
            self.assertAlmostEqual(scale, 1.0, delta=0.02)

            # ...and the wander is reported rather than hidden, since it
            # means the tape was laid along something other than intended.
            # An alternating 0/40 mm offset sits 19.6 mm rms off its own
            # best-fit line.
            straight_line = next(l for l in output.splitlines()
                                 if "straightness" in l)
            straightness_mm = float(straight_line.split(":")[1].split()[0])
            self.assertGreater(straightness_mm, 10.0)
            self.assertLess(straightness_mm, 30.0)
        finally:
            shutil.rmtree(run_dir)

    def test_a_straight_depth_line_reports_near_zero_straightness(self):
        rig = make_rig(pitch_deg=-0.94)
        run_dir = tempfile.mkdtemp()
        try:
            shots = self._wandering_depth_series(rig, run_dir, lateral_mm=0.0)
            rc, output = self._run_analysis(run_dir, rig, shots)
            self.assertEqual(rc, 0, output)
            straight_line = next(l for l in output.splitlines()
                                 if "straightness" in l)
            self.assertLess(float(straight_line.split(":")[1].split()[0]), 2.0)
        finally:
            shutil.rmtree(run_dir)

    @staticmethod
    def _scale_line_field(output, index):
        line = next(l for l in output.splitlines()
                    if l.strip().startswith("scale against tape:"))
        return line.split(":")[1].split()[index]

    @staticmethod
    def _labelled_number(output, label):
        line = next(l for l in output.splitlines() if label in l)
        return float(line.split(":")[1].split()[0])

    def _spread_pair(self, rig, run_dir, shots):
        """Two lateral positions, so the floor plane is determined."""
        for i, (x, z) in enumerate(((-0.22, 0.40), (0.22, 0.60))):
            name = "gs_s{}.png".format(i)
            self._write(run_dir, name, *ball_discs(rig, np.array([x, 0.0937, z])))
            shots.append({"name": name, "tape_mm": z * 1000.0,
                          "series": "spread", "found": True})

    def test_the_scale_carries_its_own_uncertainty(self):
        # The question the run exists to settle is 0.6% wide. A scale
        # printed bare cannot answer it either way, and the reader has no
        # way to tell 1.004 +- 0.001 from 1.004 +- 0.009 - the first
        # settles it, the second says come back with more shots.
        rig = make_rig(pitch_deg=-0.94)
        run_dir = tempfile.mkdtemp()
        try:
            shots = self._wandering_depth_series(rig, run_dir, lateral_mm=0.0)
            rc, output = self._run_analysis(run_dir, rig, shots)
            self.assertEqual(rc, 0, output)

            self.assertIn("+-", self._scale_line_field(output, 1))
            stderr = float(self._scale_line_field(output, 2))
            self.assertGreater(stderr, 0.0)
            self.assertLess(stderr, 0.05)
            # The implied baseline inherits the same uncertainty; quoting it
            # to three decimals without one invites reading 78.412 as
            # settled against 78.749.
            baseline_line = next(l for l in output.splitlines()
                                 if "implied baseline" in l)
            self.assertIn("+-", baseline_line)
        finally:
            shutil.rmtree(run_dir)

    def test_a_lens_plane_offset_reads_as_an_offset_not_a_scale(self):
        # The tape is read from the unit's front face; Z is measured from
        # camera 1's z = 0 plane, somewhere inside the housing. Here that
        # gap is 50 mm. Fitting differences used to cancel it; fitting with
        # an intercept measures it instead, which is strictly more - it is
        # the only estimate of that distance the project has.
        rig = make_rig(pitch_deg=-0.94)
        run_dir = tempfile.mkdtemp()
        try:
            shots = []
            for i, tape in enumerate([350.0, 420.0, 490.0, 560.0, 630.0]):
                name = "gs_o{:02d}.png".format(i)
                self._write(run_dir, name, *ball_discs(
                    rig, np.array([0.0, 0.0937, tape / 1000.0 + 0.050])))
                shots.append({"name": name, "tape_mm": tape,
                              "series": "depth", "found": True})
            self._spread_pair(rig, run_dir, shots)

            rc, output = self._run_analysis(run_dir, rig, shots)
            self.assertEqual(rc, 0, output)

            self.assertAlmostEqual(float(self._scale_line_field(output, 0)),
                                   1.0, delta=0.02)
            self.assertAlmostEqual(
                self._labelled_number(output, "lens-plane offset"),
                50.0, delta=8.0)
        finally:
            shutil.rmtree(run_dir)

    def test_repeats_at_one_tape_reading_are_used_rather_than_skipped(self):
        # Three frames per position without touching the ball is the
        # cheapest precision available on the floor. The consecutive-
        # differences estimator dropped every repeat, because a repeated
        # position has a zero tape gap, and said so in a line the operator
        # would read as a warning about their own layout.
        rig = make_rig(pitch_deg=-0.94)
        run_dir = tempfile.mkdtemp()
        try:
            shots = []
            for i, tape in enumerate([380.0, 500.0, 620.0]):
                for repeat in (1, 2):
                    name = "gs_r{}{}.png".format(i, repeat)
                    self._write(run_dir, name, *ball_discs(
                        rig, np.array([0.0, 0.0937, tape / 1000.0])))
                    shots.append({"name": name, "tape_mm": tape,
                                  "series": "depth", "found": True})
            self._spread_pair(rig, run_dir, shots)

            rc, output = self._run_analysis(run_dir, rig, shots)
            self.assertEqual(rc, 0, output)

            self.assertNotIn("did not increase", output)
            self.assertIn("over 6 depth positions", output)
            self.assertAlmostEqual(float(self._scale_line_field(output, 0)),
                                   1.0, delta=0.02)
        finally:
            shutil.rmtree(run_dir)

    def test_an_oblique_depth_line_is_measured_and_its_bias_undone(self):
        # The tape ran along the ball line - a rule on the floor, which is
        # what an operator actually lays - but the line sat 12 deg off the
        # optical axis. The raw scale then reads cos(12) = 0.978 low, which
        # is four times the whole 0.6% signal, and nothing else in the run
        # would have shown it.
        psi = np.radians(12.0)
        rig = make_rig(pitch_deg=-0.94)
        run_dir = tempfile.mkdtemp()
        try:
            shots = []
            for i, along_m in enumerate([0.0, 0.07, 0.14, 0.21, 0.28]):
                xyz = np.array([along_m * np.sin(psi), 0.0937,
                                0.360 + along_m * np.cos(psi)])
                name = "gs_q{:02d}.png".format(i)
                self._write(run_dir, name, *ball_discs(rig, xyz))
                shots.append({"name": name, "tape_mm": 360.0 + along_m * 1000.0,
                              "series": "depth", "found": True})
            self._spread_pair(rig, run_dir, shots)

            rc, output = self._run_analysis(run_dir, rig, shots)
            self.assertEqual(rc, 0, output)

            obliquity = self._labelled_number(output, "depth line obliquity")
            self.assertAlmostEqual(obliquity, 12.0, delta=1.5)

            raw = float(self._scale_line_field(output, 0))
            self.assertAlmostEqual(raw, np.cos(psi), delta=0.02)

            corrected = self._labelled_number(
                output, "scale if the tape ran along")
            self.assertAlmostEqual(corrected, 1.0, delta=0.02)
        finally:
            shutil.rmtree(run_dir)

    def test_the_scale_line_separates_shots_from_distinct_positions(self):
        # 18 shots at 6 readings has the leverage of 6, not of 18. A bare
        # "over 18 depth positions" invites the opposite reading.
        rig = make_rig(pitch_deg=-0.94)
        run_dir = tempfile.mkdtemp()
        try:
            shots = []
            for i, tape in enumerate([380.0, 500.0, 620.0]):
                for repeat in (1, 2):
                    name = "gs_c{}{}.png".format(i, repeat)
                    self._write(run_dir, name, *ball_discs(
                        rig, np.array([0.0, 0.0937, tape / 1000.0])))
                    shots.append({"name": name, "tape_mm": tape,
                                  "series": "depth", "found": True})
            self._spread_pair(rig, run_dir, shots)

            rc, output = self._run_analysis(run_dir, rig, shots)
            self.assertEqual(rc, 0, output)
            self.assertIn("over 6 depth positions at 3 distinct tape readings",
                          output)
        finally:
            shutil.rmtree(run_dir)

    def test_the_repeat_spread_bounds_what_the_stderr_cannot(self):
        # The ball put back on its mark three times, landing 10 mm apart.
        # The regression's stderr is computed from scatter about the fitted
        # line and would report this as small; the repeat spread is what
        # says how repeatable one shot actually was.
        rig = make_rig(pitch_deg=-0.94)
        run_dir = tempfile.mkdtemp()
        try:
            shots = []
            for i, (tape, z) in enumerate([(380.0, 0.380),
                                           (500.0, 0.490),
                                           (500.0, 0.500),
                                           (500.0, 0.510),
                                           (620.0, 0.620)]):
                name = "gs_p{:02d}.png".format(i)
                self._write(run_dir, name, *ball_discs(
                    rig, np.array([0.0, 0.0937, z])))
                shots.append({"name": name, "tape_mm": tape,
                              "series": "depth", "found": True})
            self._spread_pair(rig, run_dir, shots)

            rc, output = self._run_analysis(run_dir, rig, shots)
            self.assertEqual(rc, 0, output)
            spread = self._labelled_number(output, "repeat spread")
            self.assertGreater(spread, 5.0)
            self.assertLess(spread, 20.0)
        finally:
            shutil.rmtree(run_dir)

    def test_a_series_with_no_repeats_says_so_rather_than_printing_a_zero(self):
        # Zero would read as perfect repeatability. The series measured no
        # repeatability at all, which is a different statement.
        rig = make_rig(pitch_deg=-0.94)
        run_dir = tempfile.mkdtemp()
        try:
            shots = self._wandering_depth_series(rig, run_dir, lateral_mm=0.0)
            rc, output = self._run_analysis(run_dir, rig, shots)
            self.assertEqual(rc, 0, output)
            line = next(l for l in output.splitlines() if "repeat spread" in l)
            self.assertIn("not measured", line)
        finally:
            shutil.rmtree(run_dir)

    def test_pan_is_named_a_property_of_the_placement_not_of_the_unit(self):
        # Pitch and roll are pinned by the mount and the floor. Yaw is the
        # angle to a line the operator chose, and the unit is free-standing
        # - no mat edge, no marked position - so it describes the session,
        # not the device. Pasting it into a constant would freeze one
        # afternoon's placement into the geometry.
        rig = make_rig(pitch_deg=-0.94)
        run_dir = tempfile.mkdtemp()
        try:
            shots = self._wandering_depth_series(rig, run_dir, lateral_mm=0.0)
            for i, (x, z) in enumerate(((0.0, 0.40), (0.10, 0.68))):
                name = "gs_tl{}.png".format(i)
                self._write(run_dir, name, *ball_discs(rig, np.array([x, 0.0937, z])))
                shots.append({"name": name, "tape_mm": z * 1000.0,
                              "series": "target", "found": True})

            rc, output = self._run_analysis(run_dir, rig, shots)
            self.assertEqual(rc, 0, output)
            self.assertIn("today's placement", output.lower())
        finally:
            shutil.rmtree(run_dir)

    def test_header_states_the_depth_tolerance_the_table_is_read_against(self):
        rig = make_rig()
        run_dir = tempfile.mkdtemp()
        try:
            rc, output = self._run_analysis(run_dir, rig, [])
            self.assertEqual(rc, 1)  # no floor shots
            header = next(l for l in output.splitlines()
                          if "depth tolerance" in l)
            self.assertIn("3.5", header)  # 0.5^2 / (0.07872 * 900) = 3.53 mm
            self.assertIn("per px", header)
        finally:
            shutil.rmtree(run_dir)

    def test_unmeasured_pan_is_a_placeholder_and_never_a_zero(self):
        # Twenty lines further down, roll is called "DROPPED, not zero". Pan
        # gets the same standard: the kCamera1Angles line is shaped to be
        # copied straight into the config, so a fabricated +0.000 there is
        # the one that does damage.
        rig = make_rig(pitch_deg=0.0)
        run_dir = tempfile.mkdtemp()
        try:
            # A floor with no target-line pair, so yaw is unmeasured.
            points = floor_seen_by_a_tilted_camera(1.0, depths=(0.40, 0.60))
            shots = []
            for i, xyz in enumerate(points, start=1):
                name = "gs_{:02d}.png".format(i)
                self._write(run_dir, name, *ball_discs(rig, xyz))
                shots.append({"name": name, "tape_mm": 350.0 + 40.0 * i,
                              "series": "spread", "found": True})
            rc, output = self._run_analysis(run_dir, rig, shots)
            self.assertEqual(rc, 0, output)

            angles_line = next(l for l in output.splitlines()
                               if '"kCamera1Angles"' in l)
            self.assertIn("????", angles_line)
            self.assertIn("NOT MEASURED", angles_line)
            self.assertNotIn("+0.000", angles_line)

            # And the note explaining yaw's sign sense stays away too: under
            # a "not measured" line it would be explaining the sign of a
            # number that is not there.
            self.assertIn("yaw    not measured", output)
            self.assertNotIn("yaw sign is not the same sense", output)
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
                self._write(run_dir, name, *ball_discs(rig, xyz))
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
