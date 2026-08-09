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

from sp1_vision import camera_paths, stereo_geometry

# One number, named once. The intrinsics in golf_sim_config.json were solved
# at this resolution and stereo_geometry rejects frames of any other, so the
# size we ASK the driver for and the size the maths ASSUMES must not be two
# separate literals that can drift apart.
FRAME_WIDTH, FRAME_HEIGHT = stereo_geometry.EXPECTED_IMAGE_SIZE
FOURCC = cv2.VideoWriter_fourcc("M", "J", "P", "G")
WARMUP_FRAMES = 5

# The module offers exactly two rates at 1280x800: 120 and 100 fps. Nothing
# else. Asking for 30 or 60 silently lands on 100 - measured 2026-08-06,
# driver reporting 100.0 and delivering 101.9 for both requests - so trying to
# run the sensor slower to cut the heat from its MJPEG encoder buys 17% and
# costs pair simultaneity, since the skew between two free-running cameras is
# bounded by the frame period.
#
# The heat is dealt with where it actually comes from: the cameras being open
# at all. The page stops polling and streaming when its tab is hidden, which
# lets the session's idle timeout fire and hand them back.
FRAME_RATE = 120

# v4l2-ctl talks to the UVC driver, and a wedged driver would otherwise block
# forever. This runs while CalibrationSession's lock is held, so a hang here
# would take down every stream, the capture button, the release button and the
# idle watchdog at once - and pitrac_lm could then never reclaim the devices,
# which is the exact failure the idle release exists to prevent.
EXPOSURE_CTL_TIMEOUT_S = 5.0

# How long a camera may keep the other waiting at the paired-grab barrier. A
# party that never arrives - a read wedged in the driver, or a thread that
# failed to start - would otherwise hang the grab, and with it the lock.
BARRIER_TIMEOUT_S = 5.0


def set_manual_exposure(device, exposure_units):
    """Force manual exposure so a capture series is consistently lit.

    exposure_units are 100 us steps, matching V4L2's exposure_absolute
    (range 1..5000 on these modules). Pass None to restore auto.

    Done through v4l2-ctl rather than cv2.CAP_PROP_AUTO_EXPOSURE because the
    OpenCV property semantics vary across versions on the V4L2 backend.

    Best-effort: a failure here means the exposure is not what was asked for,
    which is a worse capture series, not a broken one. Hanging the caller
    would be far worse than that, so it is bounded.
    """
    if exposure_units is None:
        ctrl = "exposure_auto=3"
    else:
        ctrl = "exposure_auto=1,exposure_absolute={}".format(int(exposure_units))
    try:
        subprocess.run(
            ["v4l2-ctl", "--device={}".format(device), "--set-ctrl={}".format(ctrl)],
            check=False, capture_output=True, timeout=EXPOSURE_CTL_TIMEOUT_S,
        )
    except (subprocess.TimeoutExpired, OSError):
        pass


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

        The calling thread is one of the barrier parties, so only one thread
        is spawned per grab rather than two. The dashboard grabs this around
        35 times a second while holding the session lock, and thread creation
        in that critical section is latency every other caller waits behind -
        besides which Thread.start() can fail outright under churn on a small
        board.

        The barrier is bounded. A party that never arrives - a read wedged in
        the driver, or a thread that failed to start at all - would otherwise
        block the grab forever, and the session lock with it.
        """
        frames = {}
        stamps = {}
        errors = {}
        items = list(self._caps.items())
        barrier = threading.Barrier(len(items), timeout=BARRIER_TIMEOUT_S)

        def read_one(n, cap):
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
                # Release anyone still waiting rather than leaving them to
                # time out one by one.
                barrier.abort()

        threads = [threading.Thread(target=read_one, args=(n, cap))
                   for n, cap in items[1:]]
        for t in threads:
            t.start()
        read_one(*items[0])
        for t in threads:
            t.join(timeout=BARRIER_TIMEOUT_S + 5.0)

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


# Seconds without a request before the cameras are handed back. A V4L2 node
# has a single owner, so a dashboard that never lets go would block pitrac_lm
# from ever starting. Keep this well above the cold-open cost, measured at
# 1.8-2.0 s on these OV9281 modules.
DEFAULT_IDLE_TIMEOUT_S = 120.0

# How often the watchdog checks for idleness. One lock acquisition a second.
IDLE_CHECK_INTERVAL_S = 1.0


class CalibrationSession:
    """The cameras, opened on demand and handed back when idle.

    Every operation takes one lock and holds it for the whole operation,
    including the slow open and the close. No reference to the CameraPair
    ever escapes that lock, so there is no window in which one caller can act
    on a pair another caller is tearing down.

    An earlier version kept a background grabber thread and cached the most
    recent pair so that streams and captures never touched the devices
    directly. It produced four separate concurrency defects, and each fix
    opened a new hole. The cache bought very little - at two MJPEG viewers
    and a twice-a-second sharpness poll this serialises at well under half
    duty - so the optimisation was not worth what it cost to make correct.
    """

    def __init__(self, idle_timeout_s=DEFAULT_IDLE_TIMEOUT_S):
        self.idle_timeout_s = idle_timeout_s
        self._lock = threading.Lock()
        self._pair = None
        self._last_use = 0.0
        self._watchdog = None

    def is_open(self):
        with self._lock:
            return self._pair is not None

    def ensure_open(self, exposure_units=None):
        """Open the cameras if they are not already open.

        Slow on a cold open - around two seconds - and callers are serialised
        behind it. That is the price of never handing out a pair that someone
        else might close.

        exposure_units applies only when this call is the one that opens.
        Against an already-open session it is ignored, silently, because the
        cameras are shared and one caller must not resettle exposure under
        another's feet. To change it, release() first.
        """
        with self._lock:
            self._last_use = time.monotonic()
            if self._pair is None:
                self._pair = CameraPair(exposure_units=exposure_units).open()
            if self._watchdog is None:
                self._watchdog = threading.Thread(target=self._watch, daemon=True)
                self._watchdog.start()

    def grab(self):
        """Return ({camera_number: frame}, skew_seconds), or (None, None).

        (None, None) means the session is closed. Callers decide whether that
        is an error or simply means calibration is not in progress.
        """
        with self._lock:
            if self._pair is None:
                return None, None
            self._last_use = time.monotonic()
            return self._pair.grab_with_skew()

    def release(self):
        """Hand the cameras back. Idempotent.

        The descriptors are closed before the lock drops, so is_open() cannot
        report free while a teardown is still in flight - which is the whole
        point, since pitrac_lm may be waiting to open the same nodes.
        """
        with self._lock:
            pair, self._pair = self._pair, None
            if pair is not None:
                pair.release()

    def _watch(self):
        """Release the cameras once nobody has asked for a frame in a while.

        Lives for the process. Everything it does happens under the same one
        lock, including the close, so it cannot race a caller.
        """
        while True:
            time.sleep(IDLE_CHECK_INTERVAL_S)
            with self._lock:
                if self._pair is None:
                    continue
                if time.monotonic() - self._last_use <= self.idle_timeout_s:
                    continue
                pair, self._pair = self._pair, None
                pair.release()


# One session per process. The dashboard is single-process, and two of these
# on the same devices would only fight.
SESSION = CalibrationSession()
