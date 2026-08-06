"""CameraPair against the real hardware.

These tests open the cameras. They only pass on the Jetson with both modules
plugged in and nothing else holding the devices - a V4L2 node has a single
owner, so stop the dashboard first if it is streaming.
"""

import time
import unittest

from sp1_vision import calibration_capture


class CameraPairTest(unittest.TestCase):
    def setUp(self):
        self.pair = calibration_capture.CameraPair()
        self.pair.open()

    def tearDown(self):
        self.pair.release()

    def test_grab_returns_one_frame_per_camera_at_full_resolution(self):
        frames = self.pair.grab()
        self.assertEqual(sorted(frames), [1, 2])
        for n in (1, 2):
            self.assertEqual(frames[n].shape[:2], (800, 1280))

    def test_frames_in_a_pair_are_captured_close_together(self):
        # The barrier should hold the two reads to within a frame period or
        # two. Anything worse and a moving board would be in different places
        # in the two images.
        _, skew_s = self.pair.grab_with_skew()
        self.assertLess(skew_s, 0.030)

    def test_repeated_grabs_return_fresh_frames(self):
        first = self.pair.grab()
        time.sleep(0.1)
        second = self.pair.grab()
        # BUFFERSIZE 1 plus a live scene means consecutive frames should
        # differ somewhere. Identical frames mean a stale buffer.
        self.assertFalse((first[1] == second[1]).all())

    def test_release_is_idempotent(self):
        self.pair.release()
        self.pair.release()


if __name__ == "__main__":
    unittest.main()
