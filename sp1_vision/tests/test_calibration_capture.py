"""CameraPair against the real hardware.

These tests open the cameras. They only pass on the Jetson with both modules
plugged in and nothing else holding the devices - a V4L2 node has a single
owner, so stop the dashboard first if it is streaming.
"""

import threading
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
        calibration_capture.SESSION.idle_timeout_s = (
            calibration_capture.DEFAULT_IDLE_TIMEOUT_S)
        calibration_capture.SESSION.release()

    def test_grab_returns_a_pair_once_open(self):
        session = calibration_capture.SESSION
        session.ensure_open()
        frames, skew = session.grab()
        self.assertIsNotNone(frames)
        self.assertEqual(sorted(frames), [1, 2])
        self.assertLess(skew, 0.030)

    def test_grab_before_open_returns_nothing_rather_than_raising(self):
        session = calibration_capture.SESSION
        session.release()
        frames, skew = session.grab()
        self.assertIsNone(frames)
        self.assertIsNone(skew)

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

    def test_release_is_idempotent(self):
        session = calibration_capture.SESSION
        session.ensure_open()
        session.release()
        session.release()
        self.assertFalse(session.is_open())

    def test_idle_timeout_releases_without_being_asked(self):
        session = calibration_capture.SESSION
        session.idle_timeout_s = 1.0
        session.ensure_open()
        deadline = time.time() + 10.0
        while session.is_open() and time.time() < deadline:
            time.sleep(0.1)
        self.assertFalse(session.is_open(), "session did not release when idle")

    def test_reopen_immediately_after_idle_release(self):
        # The release-then-reopen sequence is what the pitrac_lm handoff
        # depends on, and it is where every lifecycle defect showed up.
        session = calibration_capture.SESSION
        session.idle_timeout_s = 1.0
        session.ensure_open()
        deadline = time.time() + 10.0
        while session.is_open() and time.time() < deadline:
            time.sleep(0.1)
        self.assertFalse(session.is_open(), "session did not release when idle")

        session.ensure_open()
        frames, _ = session.grab()
        self.assertIsNotNone(frames, "no pair served after reopening")

    def test_concurrent_release_and_ensure_open_do_not_orphan_a_pair(self):
        # The fourth defect was a release racing an open: it could tear down
        # the freshly opened pair and leave a grabber thread spinning on dead
        # handles while is_open() reported free.
        #
        # The single-lock design has no such window, and there is no longer a
        # persistent grabber to orphan - so this cannot fail the way the
        # original bug failed. What it does check is that the churn neither
        # deadlocks nor raises, and that no threads accumulate, which is the
        # symptom that would return if a background thread were ever
        # reintroduced with the same shape.
        session = calibration_capture.SESSION
        errors = []

        # Open once first, so the watchdog thread is already running and does
        # not count as a leak against the baseline.
        session.ensure_open()
        baseline_threads = threading.active_count()

        def opener():
            for _ in range(5):
                try:
                    session.ensure_open()
                    session.grab()
                except Exception as exc:            # noqa: BLE001
                    errors.append(("open", repr(exc)))

        def releaser():
            for _ in range(5):
                try:
                    session.release()
                    time.sleep(0.05)
                except Exception as exc:            # noqa: BLE001
                    errors.append(("release", repr(exc)))

        threads = [threading.Thread(target=opener),
                   threading.Thread(target=releaser)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=90)
        for t in threads:
            self.assertFalse(t.is_alive(), "a worker never finished - deadlock?")
        self.assertEqual(errors, [])

        # Grab threads are short-lived, but "short" is not a number we get to
        # assume - waiting a fixed second and asserting turns a timing guess
        # into a flaky test. Poll instead: the requirement is that the count
        # comes back, not that it comes back within any particular moment.
        deadline = time.time() + 15.0
        while threading.active_count() > baseline_threads and time.time() < deadline:
            time.sleep(0.1)
        leaked = threading.active_count() - baseline_threads
        self.assertLessEqual(
            leaked, 0,
            "{} threads outlived the churn - something is not being "
            "joined".format(leaked))


if __name__ == "__main__":
    unittest.main()
