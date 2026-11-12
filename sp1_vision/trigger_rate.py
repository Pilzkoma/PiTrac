#!/usr/bin/env python3
"""How fast can the B0332s be triggered without dropping frames?

    python3 -m sp1_vision.trigger_rate
    python3 -m sp1_vision.trigger_rate --periods-ms 10 8.33 7 6 5 --seconds 3

For each period the Teensy runs TRIG_RUN (firmware v0.3, no flash) for a few
seconds with both cameras in trigger mode; the frames each camera delivers
are counted against the edges the Teensy reports. Frames per edge below 1
means the camera skipped triggers at that rate. Arducam says ~100 fps in
trigger mode; the exposure is kept short (default 0.5 ms) as their note
asks.
"""

import argparse
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sp1_vision import strobe_capture as sc  # noqa: E402
from sp1_vision.calibration_capture import set_manual_exposure  # noqa: E402


def counter(cap, stop, counts, key):
    while not stop.is_set():
        ok, _ = cap.read()
        if ok and counts["live"]:
            counts[key] += 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--periods-ms", type=float, nargs="+", default=[10, 8.33, 7, 6, 5])
    ap.add_argument("--seconds", type=float, default=3.0)
    ap.add_argument("--exposure", type=int, default=5, help="100 us units")
    args = ap.parse_args(argv)

    sc.release_dashboard()
    teensy = sc.Teensy(sc.TEENSY)
    caps = sc.open_cameras()
    counts = {"live": False}
    for n in caps:
        counts[n] = 0
    stop = threading.Event()
    threads = []
    rows = []
    try:
        sc.settle_on_auto(caps)
        for _, dev in caps.values():
            set_manual_exposure(dev, args.exposure)
        time.sleep(sc.SETTLE_S)
        teensy.cmd("TRIG_ARM")
        sc.set_trigger_mode(caps, True)
        threads = [threading.Thread(target=counter, args=(c, stop, counts, n), daemon=True)
                   for n, (c, _) in caps.items()]
        for th in threads:
            th.start()
        time.sleep(0.5)
        for period_ms in args.periods_ms:
            period_us = int(round(period_ms * 1000))
            for n in caps:
                counts[n] = 0
            counts["live"] = True
            teensy.cmd("TRIG_RUN,{},900,0,{}".format(period_us, int(args.seconds * 1000) + 5000))
            time.sleep(args.seconds)
            reply = teensy.cmd("STOP", expect=None)
            time.sleep(0.15)                 # last frames still in flight
            counts["live"] = False
            edges = int(reply.split()[-1]) if reply.startswith("OK") else -1
            row = (period_ms, edges, {n: counts[n] for n in caps})
            rows.append(row)
            print("period %5.2f ms (%5.1f fps): %4d edges, " % (period_ms, 1000 / period_ms, edges)
                  + ", ".join("cam%d %4d frames (%.3f per edge)" % (n, c, c / max(edges, 1))
                              for n, c in row[2].items()), flush=True)
            time.sleep(0.3)
    finally:
        stop.set()
        sc.set_trigger_mode(caps, False)
        for th in threads:
            th.join(timeout=3)
        try:
            teensy.cmd("STOP", expect=None)
            teensy.cmd("TRIG_DISARM")
        except Exception:        # noqa: BLE001
            pass
        for cap, dev in caps.values():
            cap.release()
            set_manual_exposure(dev, None)
        teensy.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
