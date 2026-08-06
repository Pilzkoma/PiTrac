#!/usr/bin/env python3
"""Simultaneous capture from both OV9281 modules, for calibration.

Sequential per-camera series can never yield stereo extrinsics - the two
views must show the board in the same place at the same moment. That makes
paired capture the one irreversible decision in this tool, so it is the
primitive everything else is built on rather than something each caller
arranges for itself.

Capture setup follows sp1_vision/dual_camera_test.py, which established that
MJPG FOURCC must be set before resolution or format negotiation falls back to
YUYV at 10 FPS.
"""

import subprocess
import threading
import time

import cv2

from sp1_vision import camera_paths

FRAME_WIDTH = 1280
FRAME_HEIGHT = 800
FRAME_RATE = 120
FOURCC = cv2.VideoWriter_fourcc("M", "J", "P", "G")
WARMUP_FRAMES = 5


def set_manual_exposure(device, exposure_units):
    """Force manual exposure so a capture series is consistently lit.

    exposure_units are 100 us steps, matching V4L2's exposure_absolute
    (range 1..5000 on these modules). Pass None to restore auto.

    Done through v4l2-ctl rather than cv2.CAP_PROP_AUTO_EXPOSURE because the
    OpenCV property semantics vary across versions on the V4L2 backend.
    """
    if exposure_units is None:
        ctrl = "exposure_auto=3"
    else:
        ctrl = "exposure_auto=1,exposure_absolute={}".format(int(exposure_units))
    subprocess.run(
        ["v4l2-ctl", "--device={}".format(device), "--set-ctrl={}".format(ctrl)],
        check=False, capture_output=True,
    )


class CameraPair:
    """Both cameras, opened together, grabbed together."""

    def __init__(self, exposure_units=None):
        self.exposure_units = exposure_units
        self._caps = {}
        self._devices = {}

    def open(self):
        self._devices = camera_paths.all_devices()
        for n, dev in self._devices.items():
            if self.exposure_units is not None:
                set_manual_exposure(dev, self.exposure_units)
            cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)
            if not cap.isOpened():
                self.release()
                raise RuntimeError(
                    "camera {} at {} would not open; another process may hold "
                    "it (a V4L2 node has a single owner)".format(n, dev)
                )
            cap.set(cv2.CAP_PROP_FOURCC, FOURCC)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
            cap.set(cv2.CAP_PROP_FPS, FRAME_RATE)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            for _ in range(WARMUP_FRAMES):
                cap.read()
            self._caps[n] = cap
        return self

    def grab(self):
        """Return {camera_number: BGR frame}, captured simultaneously."""
        frames, _ = self.grab_with_skew()
        return frames

    def grab_with_skew(self):
        """Return ({camera_number: frame}, skew_seconds).

        Skew is the spread between the two read completions - a health
        measure for how simultaneous the pair really was.
        """
        frames = {}
        stamps = {}
        errors = {}
        barrier = threading.Barrier(len(self._caps))

        def worker(n, cap):
            try:
                barrier.wait()
                ok, frame = cap.read()
                stamps[n] = time.perf_counter()
                if not ok or frame is None:
                    errors[n] = "read failed"
                else:
                    frames[n] = frame
            except Exception as exc:            # noqa: BLE001 - reported below
                errors[n] = repr(exc)

        threads = [
            threading.Thread(target=worker, args=(n, cap))
            for n, cap in self._caps.items()
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        if errors:
            raise RuntimeError("paired grab failed: {}".format(errors))
        return frames, max(stamps.values()) - min(stamps.values())

    def release(self):
        for n, cap in list(self._caps.items()):
            cap.release()
            del self._caps[n]
        if self.exposure_units is not None:
            for dev in self._devices.values():
                set_manual_exposure(dev, None)

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.release()
