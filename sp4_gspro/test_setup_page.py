#!/usr/bin/env python3
"""Tests for the dashboard's setup page ("Aufbau").

The flash capture is replaced by a fake that returns drawn stereo pairs, so
nothing fires and no camera opens. Needs Flask and OpenCV, so it runs on
the Jetson. Run from sp4_gspro/:
    python3 -m unittest test_setup_page
"""

import os
import time
import unittest

import cv2

import numpy as np

import setup_page
from sp1_vision import flash_pair, setup_check, stereo_geometry
from sp1_vision.tests.test_ball_pair import frames_with

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _rig():
    return stereo_geometry.load_rig(
        os.path.join(_ROOT, stereo_geometry.DEFAULT_EXTRINSICS_PATH),
        os.path.join(_ROOT, stereo_geometry.DEFAULT_CONFIG_PATH))


def _fake_capture(images, rises=None):
    def capture(pulse_us=100, release=None, **_):
        if release is not None:
            release()
        black = {n: np.zeros_like(images[n]) for n in (1, 2)}
        return flash_pair.FlashPair(diff=images, flash=images, ambient=black,
                                    rises=rises or {1: 60.0, 2: 60.0}, pulse_us=pulse_us)
    return capture


class SetupPageTest(unittest.TestCase):
    def setUp(self):
        import dashboard   # registers the blueprint
        self.client = dashboard.app.test_client()
        rig = _rig()
        c2 = stereo_geometry.camera2_centre_in_camera1(rig)
        # Ball on target for a right-hander: 0.50 m in front of camera 2,
        # 90 mm below the axis (resting on the floor).
        self.ball_xyz = np.array([c2[0], 0.09, c2[2] + 0.50])
        f1, f2 = frames_with(rig, balls=[self.ball_xyz])
        self.images = {1: f1, 2: f2}
        self._saved = setup_page._capture
        setup_page._capture = _fake_capture(self.images)
        setup_page._last = None

    def tearDown(self):
        setup_page._capture = self._saved

    def measure(self, hand="RH"):
        return self.client.post("/setup/measure", json={"handedness": hand}).get_json()

    def test_measure_found(self):
        r = self.measure()
        self.assertTrue(r["found"], r.get("reason"))
        self.assertEqual(r["rear_camera"], 2)
        self.assertLess(abs(r["depth_mm"]), setup_check.TOLERANCE_MM)
        self.assertLess(abs(r["along_mm"]), setup_check.TOLERANCE_MM)
        self.assertTrue(r["ok"])
        self.assertTrue(r["margin_ok"])
        self.assertEqual(r["advice"], ["Passt - innerhalb ±10 mm"])
        self.assertEqual(set(r["images"]), {"1", "2"})
        self.assertGreater(len(r["images"]["1"]), 1000)

    def test_no_ball_gives_reason_and_no_numbers(self):
        blank = {n: np.zeros_like(self.images[n]) for n in (1, 2)}
        setup_page._capture = _fake_capture(blank)
        r = self.measure()
        self.assertFalse(r["found"])
        self.assertIn("circle", r["reason"])
        self.assertIsNone(r["along_mm"])
        self.assertIsNone(r["depth_mm"])
        self.assertFalse(r["ok"])
        self.assertEqual(set(r["images"]), {"1", "2"})

    def test_unlit_camera(self):
        setup_page._capture = _fake_capture(self.images, rises={1: 50.0, 2: 1.0})
        r = self.measure()
        self.assertEqual(r["unlit"], [2])
        self.assertFalse(r["found"])
        self.assertIsNone(r["along_mm"])
        self.assertIn("Kamera 2", r["reason"])

    def test_busy(self):
        setup_page._lock.acquire()
        try:
            r = self.measure()
            self.assertEqual(r["error"], "Messung läuft bereits")
        finally:
            setup_page._lock.release()

    def test_recompute_switches_rear_camera(self):
        self.measure("RH")
        r = self.client.post("/setup/recompute", json={"handedness": "LH"}).get_json()
        self.assertEqual(r["rear_camera"], 1)
        self.assertFalse(r["ok"])                    # ~80 mm off for a left-hander
        self.assertGreater(abs(r["along_mm"]), 60)

    def test_recompute_without_measurement(self):
        r = self.client.post("/setup/recompute", json={"handedness": "LH"}).get_json()
        self.assertEqual(r["error"], "noch keine Messung")

    def test_bad_handedness(self):
        r = self.client.post("/setup/measure", json={"handedness": "x"})
        self.assertEqual(r.status_code, 400)

    def test_response_names_its_handedness(self):
        self.assertEqual(self.measure("RH")["handedness"], "RH")
        r = self.client.post("/setup/recompute", json={"handedness": "LH"}).get_json()
        self.assertEqual(r["handedness"], "LH")

    def test_noise_image_is_refused_quickly(self):
        # No ball, the flash lights only the floor: the stretched difference is
        # noise, the case that gave 1768 x 1577 circles and ~280 s on 2026-11-12.
        rng = np.random.RandomState(1)
        noise = {n: cv2.GaussianBlur(rng.randint(0, 255, self.images[n].shape).astype(np.uint8),
                                     (5, 5), 0) for n in (1, 2)}
        setup_page._capture = _fake_capture(noise)
        t0 = time.monotonic()
        r = self.measure()
        # Uncapped: ~420 s. Capped, Hough on noise alone still costs ~11 s per
        # camera on the Jetson, so the bound is minutes-versus-seconds, not tight.
        self.assertLess(time.monotonic() - t0, 60.0)
        self.assertFalse(r["found"])
        self.assertIsNone(r["along_mm"])

    def test_page_and_nav(self):
        html = self.client.get("/setup").get_data(as_text=True)
        self.assertIn("Aufbau", html)
        self.assertIn('href="/setup"', html)
        self.assertIn('href="/setup"', self.client.get("/calibration").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
