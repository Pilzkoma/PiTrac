#!/usr/bin/env python3
"""First strobe-lit captures: where does a single flash land in free-running
UVC frames, and how bright is it against ambient?

The OV9281 modules have no trigger input. They run at 120 fps on their own
clock, so a flash fired from the Jetson lands at an arbitrary phase of the
frame cycle. This tool measures that instead of assuming it.

Per run: both cameras stream continuously; a quarter second in, the Teensy
fires ONE pulse (configured over USB serial, triggered on Pin 29 exactly like
the production path); a quarter second later the stream stops. Frames are
kept as raw MJPEG while capturing (decoding two 120 fps streams in Python
would drop frames) and decoded afterwards.

Delays are measured from the fire to each frame's arrival in Python
(time.monotonic on both ends). The V4L2 buffer timestamp (CAP_PROP_POS_MSEC)
is recorded too but is useless here: it comes in 4 ms steps and jumps by
hundreds of ms now and then (2026-11-10), while arrival times run at a steady
8.0 ms. Arrival includes a constant transfer + decode latency, so it gives the
spread and the frame assignment exactly, the absolute offset only to within
that latency.

A frame counts as flash-lit by how much it rises above the run's own
ambient baseline (difference image), not by its absolute brightness: lamps
and windows saturate long before the ball does.

Usage (on the Jetson, dashboard cameras are released automatically):
    python3 sp1_vision/strobe_capture.py --exposures 80,40 --pulses-us 100,500 --repeats 6

Output: one directory with flash/baseline PNGs per run, frames.csv (every
frame: run, camera, timestamp, delay after fire, brightness) and a printed
summary.
"""

import argparse
import csv
import os
import subprocess
import sys
import threading
import time
import urllib.request

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sp1_vision import camera_paths  # noqa: E402
from sp1_vision.calibration_capture import (  # noqa: E402
    FOURCC, FRAME_HEIGHT, FRAME_RATE, FRAME_WIDTH, set_manual_exposure)

TEENSY = "/dev/serial/by-id/usb-Teensyduino_USB_Serial_19530120-if00"
FIRE_PIN_BOARD = 29
DASHBOARD_RELEASE = "http://127.0.0.1:5000/calibration/release"

PRE_S = 0.25            # streaming before the fire
AUTO_SETTLE_S = 3.0     # streaming on auto exposure before going manual

# The modules' output follows a compressive tone curve: the higher the ambient
# level on the ball, the fewer grey levels the same flash adds. gamma=72, the
# control's minimum, is the straightest curve on offer (a doubled flash gives
# 1.75x the grey levels, against 1.65x at the default 100 and 1.47x at 500;
# 2026-11-11). Measurements run at 72; the default is restored afterwards.
MEASURE_GAMMA = 72
DEFAULT_GAMMA = 100
POST_S = 0.25           # streaming after it
SETTLE_S = 0.6          # after an exposure change, before the first run
TEENSY_BAUD_UNIT = 10000  # BAUD 10000 -> ON_BITS counts 100 us steps

# A frame counts as flash-lit when the 99th percentile of (frame - baseline)
# exceeds the same figure between two ambient frames by this many grey levels.
LIT_THRESHOLD = 8.0

# Half-size of the square patch at the ball centre used for its brightness
# (the ball's radius is ~45 px at the working distance).
BALL_PATCH = 18


# ----------------------------------------------------------------- hardware

class Teensy:
    def __init__(self, path):
        import serial
        self.ser = serial.Serial(path, 115200, timeout=2)
        time.sleep(0.3)
        self.ser.reset_input_buffer()

    def cmd(self, line, expect="OK"):
        self.ser.write((line + "\n").encode())
        reply = self.ser.readline().decode(errors="replace").strip()
        if expect and reply != expect:
            raise RuntimeError("Teensy: {} -> {!r}".format(line, reply))
        return reply

    def single_pulse(self, pulse_us):
        bits = int(round(pulse_us / (1e6 / TEENSY_BAUD_UNIT)))
        if not 1 <= bits <= 64:
            raise ValueError("pulse {} us out of range 100..6400".format(pulse_us))
        self.cmd("PULSES_FAST,0")       # one ON pulse, no gap after it
        self.cmd("ON_BITS,{}".format(bits))
        self.cmd("BAUD,{}".format(TEENSY_BAUD_UNIT))
        self.cmd("MODE,FAST")
        status = self.cmd("STATUS", expect=None)
        if "STATE=READY" not in status:
            raise RuntimeError("Teensy not ready: " + status)
        return bits * 100

    def close(self):
        self.ser.close()


class FirePin:
    def __init__(self):
        import Jetson.GPIO as GPIO
        self.GPIO = GPIO
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(FIRE_PIN_BOARD, GPIO.OUT, initial=GPIO.LOW)

    def fire(self):
        t = time.monotonic()
        self.GPIO.output(FIRE_PIN_BOARD, self.GPIO.HIGH)
        time.sleep(0.0005)
        self.GPIO.output(FIRE_PIN_BOARD, self.GPIO.LOW)
        return t

    def close(self):
        self.GPIO.cleanup(FIRE_PIN_BOARD)


def release_dashboard():
    try:
        req = urllib.request.Request(DASHBOARD_RELEASE, data=b"", method="POST")
        urllib.request.urlopen(req, timeout=5).read()
    except Exception:       # noqa: BLE001 - no dashboard is fine
        pass


def open_cameras():
    caps = {}
    for n, dev in camera_paths.all_devices().items():
        cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)
        if not cap.isOpened():
            raise RuntimeError("camera {} ({}) would not open".format(n, dev))
        cap.set(cv2.CAP_PROP_FOURCC, FOURCC)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, FRAME_RATE)
        # Two buffers, not one: with BUFFERSIZE 1 the frame arriving while
        # Python fetches the previous one has nowhere to go and the stream
        # halves to ~68 fps (measured 2026-11-10). The held-back-frame defect
        # CameraPair guards against only matters for on-demand reads; this
        # reads back to back.
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
        cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)     # raw MJPEG, decode later
        for _ in range(5):
            cap.read()
        caps[n] = (cap, dev)
    return caps


def set_gamma(caps, value):
    for _, dev in caps.values():
        try:
            subprocess.run(["v4l2-ctl", "--device={}".format(dev),
                            "--set-ctrl=gamma={}".format(int(value))],
                           check=False, capture_output=True, timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            pass


def settle_on_auto(caps, seconds=AUTO_SETTLE_S):
    """Let each module's image processor re-converge on auto exposure.

    The modules keep adapting internally with exposure on manual and can get
    stuck: on 2026-11-11 cam2 sat with a dark patch over the image centre and
    reported a sixth of the flash, while every visible V4L2 control was
    identical to cam1. One auto-exposure pass reset it. So every switch to
    manual is preceded by a few seconds of streaming on auto.
    """
    for _, dev in caps.values():
        set_manual_exposure(dev, None)
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        for cap, _ in caps.values():
            cap.read()


# ------------------------------------------------------------------ capture

def stream(cap, stop, out):
    while not stop.is_set():
        ok, buf = cap.read()
        if ok and buf is not None:
            out.append((cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0, time.monotonic(), buf.copy()))


def one_run(caps, fire_pin):
    stop = threading.Event()
    got = {n: [] for n in caps}
    threads = [threading.Thread(target=stream, args=(cap, stop, got[n]), daemon=True)
               for n, (cap, _) in caps.items()]
    for t in threads:
        t.start()
    time.sleep(PRE_S)
    t_fire = fire_pin.fire()
    time.sleep(POST_S)
    stop.set()
    for t in threads:
        t.join(timeout=2)
    return t_fire, got


def decode(buf):
    if buf.ndim == 2 and buf.shape[0] == 1 or buf.ndim == 1:
        img = cv2.imdecode(buf.reshape(-1), cv2.IMREAD_GRAYSCALE)
    elif buf.ndim == 3:
        img = cv2.cvtColor(buf, cv2.COLOR_BGR2GRAY)
    else:
        img = buf
    return img


# ----------------------------------------------------------------- analysis

def analyse(run_id, exposure_units, pulse_us, t_fire, got, outdir, rows):
    summary = {}
    for n, frames in got.items():
        stats = []
        for ts_kernel, ts_arrive, buf in frames:
            img = decode(buf)
            if img is None:
                continue
            stats.append((ts_kernel, ts_arrive, img,
                          float(img.mean()), float(np.percentile(img, 99.9))))
        if len(stats) < 10:
            summary[n] = {"error": "only {} frames".format(len(stats))}
            continue
        ta_all = np.array([s[1] for s in stats])
        gaps = int(np.sum(np.diff(ta_all) > 1.5 / FRAME_RATE))
        # Baseline: frames well before the fire (arrival time, see docstring).
        base_idx = [i for i, s in enumerate(stats) if s[1] < t_fire - 0.05]
        if len(base_idx) < 4:
            base_idx = list(range(min(6, len(stats))))
        base_mean = float(np.median([stats[i][3] for i in base_idx]))
        base_p = float(np.median([stats[i][4] for i in base_idx]))
        base_img = np.median(np.stack([stats[i][2] for i in base_idx[-5:]]), axis=0).astype(np.uint8)
        # Frame-to-frame noise of the rise metric, from two ambient frames.
        noise = float(np.percentile(cv2.subtract(stats[base_idx[0]][2], base_img), 99))

        lit = []
        for i, (tk, ta, img, mean, p) in enumerate(stats):
            delay = ta - t_fire
            rise = float(np.percentile(cv2.subtract(img, base_img), 99))
            is_lit = rise - noise > LIT_THRESHOLD
            rows.append([run_id, n, exposure_units * 100, pulse_us, "%.3f" % tk, "%.2f" % (delay * 1000),
                         "%.2f" % rise, "%.2f" % mean, "%.1f" % p, int(is_lit)])
            if is_lit:
                lit.append((i, delay, img, mean, rise))

        name = "run%02d_cam%d" % (run_id, n)
        cv2.imwrite(os.path.join(outdir, name + "_baseline.png"), base_img)
        if lit:
            peak = max(lit, key=lambda x: x[4])
            cv2.imwrite(os.path.join(outdir, name + "_flash.png"), peak[2])
            diff = cv2.subtract(peak[2], base_img)
            cv2.imwrite(os.path.join(outdir, name + "_diff.png"), diff)
            # The ball is the most flash-lit compact spot: it is white and the
            # nearest thing to the arrays. Its centre patch gives the flash's
            # contribution on the ball (flash minus ambient).
            blur = cv2.GaussianBlur(diff.astype(np.float32), (0, 0), 25)
            by, bx = np.unravel_index(int(np.argmax(blur)), blur.shape)
            y0, y1 = max(0, by - BALL_PATCH), by + BALL_PATCH
            x0, x1 = max(0, bx - BALL_PATCH), bx + BALL_PATCH
            ball_ambient = float(base_img[y0:y1, x0:x1].mean())
            ball_flash = float(peak[2][y0:y1, x0:x1].mean())
            summary[n] = {
                "frames": len(stats), "gaps": gaps,
                "lit": len(lit),
                "delays_ms": [round(d * 1000, 2) for _, d, _, _, _ in lit],
                "rises": [round(r, 1) for _, _, _, _, r in lit],
                "base_mean": base_mean, "base_p999": base_p,
                "flash_mean": peak[3],
                "diff_p999": float(np.percentile(diff, 99.9)),
                "diff_max": int(diff.max()),
                "ball_xy": (int(bx), int(by)),
                "ball_ambient": ball_ambient,
                "ball_flash": ball_flash,
            }
        else:
            summary[n] = {"frames": len(stats), "gaps": gaps, "lit": 0,
                          "base_mean": base_mean, "base_p999": base_p}
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--exposures", default="80,40",
                    help="exposure_absolute values, 100 us units (default 80,40)")
    ap.add_argument("--pulses-us", default="100,500",
                    help="single flash length(s) in us, 100..6400 in 100 us steps")
    ap.add_argument("--repeats", type=int, default=6)
    ap.add_argument("--out", default=None, help="output directory (default /tmp/strobe_<time>)")
    ap.add_argument("--label", default="", help="free text stored with the run, e.g. 'lights off'")
    ap.add_argument("--gamma", type=int, default=MEASURE_GAMMA,
                    help="V4L2 gamma during the run, 72..500 (default %(default)s, the most "
                         "linear); " + str(DEFAULT_GAMMA) + " is restored afterwards")
    args = ap.parse_args()

    exposures = [int(x) for x in args.exposures.split(",") if x]
    pulses = [int(x) for x in args.pulses_us.split(",") if x]
    outdir = args.out or time.strftime("/tmp/strobe_%Y%m%d_%H%M%S")
    os.makedirs(outdir, exist_ok=True)

    release_dashboard()
    teensy = Teensy(TEENSY)
    fire_pin = FirePin()
    caps = open_cameras()
    rows = []
    results = []
    run_id = 0
    try:
        set_gamma(caps, args.gamma)
        for e in exposures:
            settle_on_auto(caps)
            for _, dev in caps.values():
                set_manual_exposure(dev, e)
            time.sleep(SETTLE_S)
            for p in pulses:
                p_real = teensy.single_pulse(p)
                for _ in range(args.repeats):
                    run_id += 1
                    t_fire, got = one_run(caps, fire_pin)
                    s = analyse(run_id, e, p_real, t_fire, got, outdir, rows)
                    results.append((run_id, e, p_real, s))
                    line = "run %2d  exp %5.1f ms  pulse %4d us " % (run_id, e / 10.0, p_real)
                    for n in sorted(s):
                        d = s[n]
                        if "error" in d:
                            line += "| cam%d %s " % (n, d["error"])
                        elif d["lit"]:
                            line += ("| cam%d lit %d at %s ms  ball %3.0f->%3.0f (%+4.0f) at %s  gaps %d "
                                     % (n, d["lit"], ",".join("%.1f" % x for x in d["delays_ms"]),
                                        d["ball_ambient"], d["ball_flash"],
                                        d["ball_flash"] - d["ball_ambient"],
                                        "%d,%d" % d["ball_xy"], d["gaps"]))
                        else:
                            line += "| cam%d NOT LIT  base %3.0f  gaps %d " % (n, d["base_p999"], d["gaps"])
                    print(line, flush=True)
                    time.sleep(0.2)
    finally:
        set_gamma(caps, DEFAULT_GAMMA)
        for cap, dev in caps.values():
            cap.release()
            set_manual_exposure(dev, None)
        fire_pin.close()
        teensy.close()

    with open(os.path.join(outdir, "frames.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["run", "camera", "exposure_us", "pulse_us", "kernel_ts_s", "arrival_delay_ms",
                    "rise_p99", "mean", "p999", "lit"])
        w.writerows(rows)
    with open(os.path.join(outdir, "label.txt"), "w") as fh:
        fh.write(args.label + "\n")
    print("\nwritten to", outdir)


if __name__ == "__main__":
    main()
