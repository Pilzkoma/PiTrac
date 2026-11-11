#!/usr/bin/env python3
"""Record a shot under continuous strobe and find it afterwards.

    python3 -m sp1_vision.strobe_shot --seconds 15 --out /tmp/shot1

The cameras have no trigger input and deliver frames 11-20 ms late, so a hit
cannot be reacted to. Instead: the Teensy strobes continuously (RUN), both
cameras expose ~8 ms of every 8.33 ms frame and stream into memory, and only
afterwards is the recording searched for frames that differ from the still
scene. A moving ball appears in those frames once per flash - a stroboscopic
multi-exposure, like PiTrac's camera 2, but on both cameras and without a
trigger.

First-version tool for looking at the result: it saves, per camera, the
frames with motion (flash frame and difference image) plus a contact sheet,
and prints a motion timeline. Nothing is measured yet.

The still-scene reference is scaled per frame before subtracting: with the
strobe free-running against the exposure, each frame catches a whole number
of flashes that varies by one, so the lit background flickers by that much.
"""

import argparse
import os
import sys
import threading
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sp1_vision import frame_analysis  # noqa: E402
from sp1_vision import strobe_capture as sc  # noqa: E402
from sp1_vision.calibration_capture import set_manual_exposure  # noqa: E402

REFERENCE_SKIP_S = 0.3      # after the strobe starts: still settling, not searched
REFERENCE_STRIDE = 8        # every 8th frame goes into the median reference
MOTION_LEVEL = 25           # grey levels of |frame - reference| counted as motion
MAX_SAVED = 60              # motion frames saved per camera
# Only rows from here down count towards the motion score: the floor, where a
# putt or the start of a chip runs. Above it a running screen and people in
# the room raised false alarms on the first dry run (2026-11-11).
SCORE_TOP_ROW = 350
# A frame is searched for a ball only if at least this many floor pixels
# moved; a ball 25 px in radius alone covers ~2000.
MIN_MOTION_PX = 400


def status_led(mode):
    """The carrier's power LED as status light (sp4_gspro/jetsonlm-led):
    fast blink while recording. Best-effort: without the sudoers entry from
    install_system_permissions.sh nothing happens."""
    import subprocess
    try:
        subprocess.run(["sudo", "-n", "/usr/local/sbin/jetsonlm-led", mode],
                       capture_output=True, timeout=3)
    except (subprocess.TimeoutExpired, OSError):
        pass


def stream(cap, stop, out):
    while not stop.is_set():
        ok, buf = cap.read()
        if ok and buf is not None:
            out.append((time.monotonic(), buf.copy()))


class Reference:
    """The still scene as two images: frames that caught fewer flashes and
    frames that caught one more. A still frame is a mix of the two - ambient
    stays, the flash-lit part steps by one flash - so each frame is fitted as
    a*low + b*high (least squares) and what the fit cannot explain moved.

    Both are temporal medians over the whole recording (every
    REFERENCE_STRIDE-th frame): whatever moves only briefly - the ball, the
    club, the player - drops out. The first version took the first half
    second instead, and on the first putt the player was still in frame
    then, so every later frame differed from it."""

    def __init__(self, frames, t0):
        imgs = [sc.decode(b) for ta, b in frames[::REFERENCE_STRIDE]]
        if len(imgs) < 6:
            raise RuntimeError("too few reference frames")
        means = np.array([im.mean() for im in imgs])
        cut = np.median(means)
        low = [im for im, m in zip(imgs, means) if m <= cut]
        high = [im for im, m in zip(imgs, means) if m > cut] or low
        self.a = np.median(np.stack(low), axis=0).astype(np.float32)
        self.b = np.median(np.stack(high), axis=0).astype(np.float32)
        aa, ab, bb = (self.a * self.a).sum(), (self.a * self.b).sum(), (self.b * self.b).sum()
        self.inv = np.linalg.pinv(np.array([[aa, ab], [ab, bb]], dtype=np.float64))

    def compare(self, buf):
        """(img, diff, score) for one MJPEG frame."""
        img = sc.decode(buf)
        f = img.astype(np.float32)
        ca, cb = self.inv @ np.array([(f * self.a).sum(), (f * self.b).sum()])
        diff = cv2.GaussianBlur(np.abs(f - ca * self.a - cb * self.b), (5, 5), 0)
        score = int((diff[SCORE_TOP_ROW:] > MOTION_LEVEL).sum())
        return img, np.clip(diff, 0, 255).astype(np.uint8), score


def ball_circles(diff):
    """Ball-shaped spots in a difference image, as [(u, v, r)].

    The same detector the triangulation uses (frame_analysis.ball_candidates),
    run on the difference stretched to full contrast - its edge threshold is
    absolute. Area alone could not tell a ball from the player: on the first
    putt recording the player's feet and legs scored highest. Only the floor
    band counts, as for the motion score.
    """
    top = max(float(np.percentile(diff, 99.9)), 1.0)
    stretched = np.clip(diff.astype(np.float32) * (220.0 / top), 0, 255).astype(np.uint8)
    return [(u, v, r) for u, v, r in frame_analysis.ball_candidates(stretched)
            if v >= SCORE_TOP_ROW]


def contact_sheet(items, path, cols=6, width=320):
    if not items:
        return
    h = int(width * 800 / 1280)
    tiles = []
    for item in items:
        t, img, diff, score = item[:4]
        circles = item[4] if len(item) > 4 else []
        shown = diff.copy()
        for u, v, r in circles:
            cv2.circle(shown, (int(u), int(v)), int(r), 255, 2)
        tile = cv2.resize(np.hstack([img, shown]), (2 * width, h))
        cv2.putText(tile, "%.3f s  %d" % (t, score), (6, 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, 255, 1)
        tiles.append(tile)
    while len(tiles) % cols:
        tiles.append(np.zeros_like(tiles[0]))
    rows = [np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]
    cv2.imwrite(path, np.vstack(rows))


def save_raw(out, got, t0):
    """Every frame as the JPEG the camera sent, named by its time after the
    strobe started, so the recording can be analysed again."""
    for n, frames in got.items():
        d = os.path.join(out, "raw", "cam%d" % n)
        os.makedirs(d, exist_ok=True)
        for ta, buf in frames:
            with open(os.path.join(d, "t%08.4f.jpg" % (ta - t0)), "wb") as fh:
                fh.write(buf.tobytes())


def load_raw(out):
    got = {}
    for n in (1, 2):
        d = os.path.join(out, "raw", "cam%d" % n)
        frames = []
        for name in sorted(os.listdir(d)):
            with open(os.path.join(d, name), "rb") as fh:
                frames.append((float(name[1:-4]), np.frombuffer(fh.read(), np.uint8)))
        got[n] = frames
    return got


def analyse(out, got, seconds):
    for n in sorted(got):
        # The first moments are the strobe and exposure still settling.
        frames = [(t, b) for t, b in got[n] if t >= REFERENCE_SKIP_S]
        ref = Reference(frames, 0.0)
        # Pass 1: scores only - keeping every decoded frame of a 15 s
        # recording would take gigabytes.
        scores = np.array([ref.compare(b)[2] for _, b in frames])
        times = np.array([t for t, _ in frames])
        print("cam%d: %d frames, %.1f fps, motion score median %.0f max %d"
              % (n, len(frames), len(frames) / seconds, float(np.median(scores)),
                 scores.max()))
        # Pass 2: only frames where anything moved on the floor are searched
        # for ball-shaped spots, and only those with one are kept.
        keep = []
        for i in np.flatnonzero(scores > MIN_MOTION_PX):
            img, diff, s = ref.compare(frames[i][1])
            circles = ball_circles(diff)
            if circles:
                keep.append((float(times[i]), img, diff, s, circles))
        print("  %d frames with motion, %d with a ball-shaped spot"
              % (int((scores > MIN_MOTION_PX).sum()), len(keep)))
        if keep:
            runs, start = [], keep[0][0]
            for a, b in zip(keep, keep[1:] + [None]):
                if b is None or b[0] - a[0] > 0.1:
                    runs.append((start, a[0]))
                    if b is not None:
                        start = b[0]
            print("  ball seen in: " + " ".join("%.2f-%.2f s" % r for r in runs))
        keep = keep[:MAX_SAVED]
        d = os.path.join(out, "cam%d" % n)
        os.makedirs(d, exist_ok=True)
        for t, img, diff, s, _ in keep:
            stem = "t%07.3f" % t
            cv2.imwrite(os.path.join(d, stem + "_frame.png"), img)
            cv2.imwrite(os.path.join(d, stem + "_diff.png"), diff)
        contact_sheet(keep, os.path.join(out, "cam%d_sheet.png" % n))
        print("  saved %d motion frames to %s" % (len(keep), d))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--seconds", type=float, default=15.0)
    ap.add_argument("--interval-ms", type=float, default=2.0,
                    help="time between flashes (default %(default)s)")
    ap.add_argument("--pulse-us", type=int, default=100)
    ap.add_argument("--exposure", type=int, default=80, help="100 us units")
    ap.add_argument("--gamma", type=int, default=sc.MEASURE_GAMMA)
    ap.add_argument("--out", required=True)
    ap.add_argument("--analyse", action="store_true",
                    help="analyse the recording already in --out, record nothing")
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)

    if args.analyse:
        got = load_raw(args.out)
        span = max(t for frames in got.values() for t, _ in frames)
        analyse(args.out, got, span)
        return 0

    sc.release_dashboard()
    teensy = sc.Teensy(sc.TEENSY)
    caps = sc.open_cameras()
    got = {n: [] for n in caps}
    stop = threading.Event()
    try:
        teensy.cmd("PULSES_FAST,{:g}".format(args.interval_ms))
        teensy.cmd("ON_BITS,{}".format(int(round(args.pulse_us / 100.0))))
        teensy.cmd("BAUD,10000")
        teensy.cmd("MODE,FAST")
        sc.set_gamma(caps, args.gamma)
        sc.settle_on_auto(caps)
        for _, dev in caps.values():
            set_manual_exposure(dev, args.exposure)
        time.sleep(sc.SETTLE_S)
        teensy.cmd("RUN,{}".format(int((args.seconds + 2) * 1000)))
        t0 = time.monotonic()
        threads = [threading.Thread(target=stream, args=(c, stop, got[n]), daemon=True)
                   for n, (c, _) in caps.items()]
        for th in threads:
            th.start()
        status_led("fast")
        print("strobe running, recording %.0f s - GO" % args.seconds, flush=True)
        time.sleep(args.seconds)
        stop.set()
        for th in threads:
            th.join(timeout=2)
        print("Teensy: " + teensy.cmd("STOP", expect=None), flush=True)
    finally:
        stop.set()
        status_led("on")
        try:
            teensy.cmd("STOP", expect=None)
        except Exception:      # noqa: BLE001
            pass
        sc.set_gamma(caps, sc.DEFAULT_GAMMA)
        for cap, dev in caps.values():
            cap.release()
            set_manual_exposure(dev, None)
        teensy.close()

    save_raw(args.out, got, t0)
    analyse(args.out, load_raw(args.out), args.seconds)
    return 0


if __name__ == "__main__":
    sys.exit(main())
