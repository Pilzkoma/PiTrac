#!/usr/bin/env python3
"""Unit tests for cli_triangulate module."""

import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout

from sp1_vision.cli_triangulate import (
    _find_max_shot_number,
    _load_manifest,
    _resume_start_number,
    _write_manifest,
)


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


if __name__ == "__main__":
    unittest.main()
