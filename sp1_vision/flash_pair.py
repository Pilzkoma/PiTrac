#!/usr/bin/env python3
"""One flash-lit stereo pair: the capture strobe_pair has always done, as a
function other tools (the dashboard's setup check) can call.

Capture settings are the ones strobe_runs/README.md settled on: 8 ms
exposure (every flash lands, in both cameras, although they are not in
phase), a short flash, gamma 72, and an auto-exposure pass first to clear the
image processor's stuck states. What callers analyse is the DIFFERENCE flash
minus ambient: everything the flash does not light drops out (on the first
try, 2026-11-11, room lamps on, the patterned carpet in the plain flash frame
gave two "ball-shaped objects").
"""

import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sp1_vision import strobe_capture as sc  # noqa: E402
from sp1_vision.calibration_capture import set_manual_exposure  # noqa: E402

DIFF_TOP = 220.0        # the difference's brightest 0.05 % is stretched to this


class FlashPair:
    """Both cameras' flash frame, ambient frame, difference image and rise."""

    def __init__(self, diff, flash, ambient, rises, pulse_us):
        self.diff = diff
        self.flash = flash
        self.ambient = ambient
        self.rises = rises
        self.pulse_us = pulse_us


def lit_frame(frames, t_fire):
    """Return (flash image, ambient image, rise) for one camera.

    frames: [(kernel_ts, arrival_ts, mjpeg_buffer)] from strobe_capture.one_run.
    The ambient image is the median of the last frames before the fire; the
    rise is the 99th percentile of (flash - ambient) in grey levels.
    """
    decoded = [(ta, sc.decode(b)) for _, ta, b in frames]
    ambient = [img for ta, img in decoded if ta < t_fire - 0.05]
    if len(ambient) < 3:
        raise RuntimeError("too few frames before the flash")
    base = np.median(np.stack(ambient[-5:]), axis=0).astype(np.uint8)
    best, best_rise = None, -1.0
    for ta, img in decoded:
        if ta < t_fire:
            continue
        rise = float(np.percentile(cv2.subtract(img, base), 99))
        if rise > best_rise:
            best, best_rise = img, rise
    return best, base, best_rise


def difference_image(flash, ambient):
    """Flash minus ambient, stretched linearly so its brightest 0.05 % sits
    at DIFF_TOP. Under room lamps the difference is faint (tone curve, see the
    strobe README) and the circle detector's edge threshold is absolute; a
    linear stretch moves no edge, so the geometry is untouched."""
    diff = cv2.subtract(flash, ambient)
    top = max(float(np.percentile(diff, 99.95)), 1.0)
    return np.clip(diff.astype(np.float32) * (DIFF_TOP / top), 0, 255).astype(np.uint8)


def unlit_cameras(rises):
    """Camera numbers whose flash rise is below strobe_capture.LIT_THRESHOLD."""
    return sorted(n for n, r in rises.items() if r < sc.LIT_THRESHOLD)


def capture_flash_pair(pulse_us=100, exposure_units=80, gamma=sc.MEASURE_GAMMA,
                       release=sc.release_dashboard):
    """Fire one flash while both cameras stream; return a FlashPair.

    `release` hands the cameras over first: the default asks the dashboard
    over HTTP; the dashboard itself passes its own session's release.
    """
    release()
    teensy = sc.Teensy(sc.TEENSY)
    fire_pin = sc.FirePin()
    caps = sc.open_cameras()
    try:
        sc.set_gamma(caps, gamma)
        sc.settle_on_auto(caps)
        for _, dev in caps.values():
            set_manual_exposure(dev, exposure_units)
        time.sleep(sc.SETTLE_S)
        pulse = teensy.single_pulse(pulse_us)
        t_fire, got = sc.one_run(caps, fire_pin)
    finally:
        sc.set_gamma(caps, sc.DEFAULT_GAMMA)
        for cap, dev in caps.values():
            cap.release()
            set_manual_exposure(dev, None)
        fire_pin.close()
        teensy.close()

    diff, flash, ambient, rises = {}, {}, {}, {}
    for n in (1, 2):
        flash[n], ambient[n], rises[n] = lit_frame(got[n], t_fire)
        diff[n] = difference_image(flash[n], ambient[n])
    return FlashPair(diff=diff, flash=flash, ambient=ambient, rises=rises, pulse_us=pulse)
