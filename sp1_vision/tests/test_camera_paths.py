"""Camera binding must be stable across reboots and must fail loudly."""

import os
import shutil
import tempfile
import unittest

from sp1_vision import camera_paths


class DeviceForCameraTest(unittest.TestCase):
    def setUp(self):
        # A stand-in for /dev/v4l/by-path containing symlinks that point at
        # real files, so os.path.realpath has something to resolve.
        self.root = tempfile.mkdtemp()
        self.dev = os.path.join(self.root, "dev")
        self.by_path = os.path.join(self.root, "by-path")
        os.makedirs(self.dev)
        os.makedirs(self.by_path)

    def tearDown(self):
        shutil.rmtree(self.root)

    def _link(self, camera_number, target_name):
        target = os.path.join(self.dev, target_name)
        open(target, "w").close()
        os.symlink(
            target,
            os.path.join(self.by_path, camera_paths.CAMERA_PORT_PATHS[camera_number]),
        )
        return target

    def test_resolves_symlink_to_real_device_node(self):
        target = self._link(1, "video0")
        self.assertEqual(
            camera_paths.device_for_camera(1, by_path_dir=self.by_path), target
        )

    def test_binding_follows_the_port_not_the_device_number(self):
        # The same port path now points at a different /dev/videoN, exactly
        # what happens when enumeration order changes across a reboot.
        target = self._link(2, "video7")
        self.assertEqual(
            camera_paths.device_for_camera(2, by_path_dir=self.by_path), target
        )

    def test_missing_port_raises_rather_than_falling_back(self):
        # A silent fallback to /dev/video0 would mirror the stereo baseline
        # with nothing visibly wrong in the images.
        with self.assertRaises(camera_paths.CameraBindingError):
            camera_paths.device_for_camera(1, by_path_dir=self.by_path)

    def test_unknown_camera_number_raises(self):
        with self.assertRaises(camera_paths.CameraBindingError):
            camera_paths.device_for_camera(3, by_path_dir=self.by_path)

    def test_both_cameras_are_mapped_to_distinct_ports(self):
        self.assertEqual(sorted(camera_paths.CAMERA_PORT_PATHS), [1, 2])
        self.assertEqual(len(set(camera_paths.CAMERA_PORT_PATHS.values())), 2)


if __name__ == "__main__":
    unittest.main()
