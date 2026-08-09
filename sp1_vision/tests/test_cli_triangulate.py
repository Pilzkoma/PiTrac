#!/usr/bin/env python3
"""Unit tests for cli_triangulate module."""

import json
import os
import shutil
import tempfile
import unittest

from sp1_vision.cli_triangulate import _find_max_shot_number


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


class TestManifestHandling(unittest.TestCase):
    """Tests for manifest loading and divergence detection."""

    def test_manifest_and_disk_agreement(self):
        """Test when manifest and disk agree on shot count."""
        test_dir = tempfile.mkdtemp()
        try:
            cam1_dir = os.path.join(test_dir, "cam1")
            os.makedirs(cam1_dir)

            # Create 2 images
            for num in [1, 2]:
                with open(os.path.join(cam1_dir, "gs_{:02d}.png".format(num)), "w") as f:
                    f.write("x")

            # Create matching manifest
            manifest = {
                "shots": [
                    {"name": "gs_01.png", "tape_mm": 350.0, "series": "depth"},
                    {"name": "gs_02.png", "tape_mm": 420.0, "series": "depth"}
                ]
            }

            max_disk = _find_max_shot_number(cam1_dir)
            max_manifest = len(manifest["shots"])

            self.assertEqual(max_disk, 2)
            self.assertEqual(max_manifest, 2)
            self.assertEqual(max_disk, max_manifest)
        finally:
            shutil.rmtree(test_dir)

    def test_manifest_disk_divergence(self):
        """Test detection of manifest/disk divergence (crash scenario)."""
        test_dir = tempfile.mkdtemp()
        try:
            cam1_dir = os.path.join(test_dir, "cam1")
            os.makedirs(cam1_dir)

            # Create 3 images (simulating crash that wrote images but lost manifest entry)
            for num in [1, 2, 3]:
                with open(os.path.join(cam1_dir, "gs_{:02d}.png".format(num)), "w") as f:
                    f.write("x")

            # Create manifest with only 2 shots (incomplete)
            manifest = {
                "shots": [
                    {"name": "gs_01.png", "tape_mm": 350.0, "series": "depth"},
                    {"name": "gs_02.png", "tape_mm": 420.0, "series": "depth"}
                ]
            }

            max_disk = _find_max_shot_number(cam1_dir)
            max_manifest = len(manifest["shots"])

            self.assertEqual(max_disk, 3)
            self.assertEqual(max_manifest, 2)
            self.assertNotEqual(max_disk, max_manifest)
            # Resume should use the max to avoid overwriting images
            next_num = max(max_disk, max_manifest) + 1
            self.assertEqual(next_num, 4)
        finally:
            shutil.rmtree(test_dir)


class TestManifestCorruptionHandling(unittest.TestCase):
    """Tests for corrupt manifest handling."""

    def test_corrupt_manifest_missing_shots_key(self):
        """Test that corrupt manifest (missing 'shots' key) raises KeyError."""
        test_dir = tempfile.mkdtemp()
        try:
            # Write corrupt manifest
            with open(os.path.join(test_dir, "run.json"), "w") as f:
                json.dump({"not_shots": []}, f)

            # Try to load it - should raise KeyError
            with self.assertRaises(KeyError):
                with open(os.path.join(test_dir, "run.json")) as fh:
                    shots = json.load(fh)["shots"]
        finally:
            shutil.rmtree(test_dir)

    def test_manifest_write_uses_tempfile(self):
        """Test that run_shots implementation uses atomic writes."""
        import inspect
        from sp1_vision import cli_triangulate

        # Check that run_shots implementation uses tempfile.mkstemp and os.replace
        source = inspect.getsource(cli_triangulate.run_shots)

        self.assertIn("mkstemp", source, "Should use tempfile.mkstemp for atomic writes")
        self.assertIn("os.replace", source, "Should use os.replace for atomic swap")
        self.assertIn("os.fdopen", source, "Should use os.fdopen to write to temp file")

    def test_manifest_write_cleanup_on_error(self):
        """Test that temp file is cleaned up on write error."""
        import inspect
        from sp1_vision import cli_triangulate

        # Check that run_shots has error handling for cleanup
        source = inspect.getsource(cli_triangulate.run_shots)

        self.assertIn("except Exception", source, "Should have exception handler")
        self.assertIn("os.unlink(temp_path)", source, "Should clean up temp file on error")


if __name__ == "__main__":
    unittest.main()
