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


class CalibrationSessionTest(unittest.TestCase):
    def tearDown(self):
        calibration_capture.SESSION.release()

    def test_latest_pair_becomes_available_after_start(self):
        session = calibration_capture.SESSION
        session.ensure_open()
        deadline = time.time() + 5.0
        while session.latest_pair() is None and time.time() < deadline:
            time.sleep(0.05)
        pair = session.latest_pair()
        self.assertIsNotNone(pair, "grabber produced no pair within 5 s")
        self.assertEqual(sorted(pair), [1, 2])

    def test_ensure_open_is_idempotent(self):
        session = calibration_capture.SESSION
        session.ensure_open()
        session.ensure_open()
        self.assertTrue(session.is_open())

    def test_release_frees_the_devices_for_another_opener(self):
        session = calibration_capture.SESSION
        session.ensure_open()
        session.release()
        self.assertFalse(session.is_open())
        # If the devices were genuinely released, a plain CameraPair opens.
        pair = calibration_capture.CameraPair()
        pair.open()
        pair.release()

    def test_idle_timeout_releases_without_being_asked(self):
        session = calibration_capture.SESSION
        session.idle_timeout_s = 1.0
        try:
            session.ensure_open()
            deadline = time.time() + 6.0
            while session.is_open() and time.time() < deadline:
                time.sleep(0.1)
            self.assertFalse(session.is_open(), "session did not release when idle")
        finally:
            # idle_timeout_s lives on the shared module-level SESSION, so a
            # short value left behind here would leak into later tests. See
            # the note in the task: restore rather than restructure.
            session.idle_timeout_s = calibration_capture.DEFAULT_IDLE_TIMEOUT_S


if __name__ == "__main__":
    unittest.main()
