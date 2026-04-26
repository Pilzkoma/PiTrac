#!/usr/bin/env python3
"""
SP1 — Dual-camera simultaneous capture test for OV9281.

Confirms both USB cameras sustain 120 FPS at 1280x800 MJPG in parallel.
Cameras sit on separate USB buses (xhci-2.2.4 and xhci-2.3) so no shared
USB3 bandwidth conflict is expected — this test proves it.

Run on Jetson:
    python3 sp1_vision/dual_camera_test.py
"""

import threading
import time
from dataclasses import dataclass

import cv2

DEVICES = [0, 2]              # odd-numbered /dev/video* are UVC metadata, skip them
TARGET_W, TARGET_H = 1280, 800
TARGET_FPS = 120
DURATION_S = 5.0
FOURCC = cv2.VideoWriter_fourcc('M', 'J', 'P', 'G')


@dataclass
class CameraResult:
    device: int
    opened: bool = False
    actual_w: int = 0
    actual_h: int = 0
    actual_fps_reported: float = 0.0
    fourcc_reported: str = ""
    frames_captured: int = 0
    frames_failed: int = 0
    elapsed_s: float = 0.0
    error: str = ""


def fourcc_to_str(code: float) -> str:
    code = int(code)
    return "".join(chr((code >> (8 * i)) & 0xFF) for i in range(4))


def capture_worker(device: int, duration_s: float,
                   start_barrier: threading.Barrier, result: CameraResult):
    cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
    if not cap.isOpened():
        result.error = f"failed to open /dev/video{device}"
        start_barrier.wait()
        return

    # FOURCC must be set before resolution/fps on most UVC drivers, otherwise
    # the format negotiation falls back to YUYV which is capped at ~10 FPS.
    cap.set(cv2.CAP_PROP_FOURCC, FOURCC)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, TARGET_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, TARGET_H)
    cap.set(cv2.CAP_PROP_FPS, TARGET_FPS)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    result.opened = True
    result.actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    result.actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    result.actual_fps_reported = cap.get(cv2.CAP_PROP_FPS)
    result.fourcc_reported = fourcc_to_str(cap.get(cv2.CAP_PROP_FOURCC))

    for _ in range(5):
        cap.read()

    start_barrier.wait()
    t0 = time.perf_counter()
    deadline = t0 + duration_s
    frames = 0
    failed = 0
    while time.perf_counter() < deadline:
        ok, frame = cap.read()
        if ok and frame is not None:
            frames += 1
        else:
            failed += 1
    result.elapsed_s = time.perf_counter() - t0
    result.frames_captured = frames
    result.frames_failed = failed
    cap.release()


def main():
    results = [CameraResult(device=d) for d in DEVICES]
    barrier = threading.Barrier(len(DEVICES))
    threads = [
        threading.Thread(target=capture_worker,
                         args=(d, DURATION_S, barrier, r), daemon=False)
        for d, r in zip(DEVICES, results)
    ]

    print(f"Dual-camera test: {len(DEVICES)} cameras, "
          f"target {TARGET_FPS} FPS @ {TARGET_W}x{TARGET_H} MJPG, "
          f"duration {DURATION_S}s")
    print("Starting capture in parallel...")

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print()
    print("=" * 70)
    any_error = False
    for r in results:
        print(f"/dev/video{r.device}:")
        if r.error:
            print(f"  ERROR: {r.error}")
            any_error = True
            continue
        eff_fps = r.frames_captured / r.elapsed_s if r.elapsed_s > 0 else 0.0
        target_pct = (eff_fps / TARGET_FPS) * 100
        print(f"  configured: {r.actual_w}x{r.actual_h} "
              f"@ {r.actual_fps_reported:.0f} FPS, fourcc={r.fourcc_reported}")
        print(f"  captured:   {r.frames_captured} frames in {r.elapsed_s:.2f}s "
              f"(failed reads: {r.frames_failed})")
        print(f"  effective:  {eff_fps:.1f} FPS "
              f"({target_pct:.0f}% of {TARGET_FPS} target)")
    print("=" * 70)

    if any_error:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
