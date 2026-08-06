# Jetson LM — DIY Golf Launch Monitor

## What this project is
Building a custom golf launch monitor on the Jetson Xavier NX, using PiTrac
(open source, Raspberry Pi) as the starting codebase.
PiTrac uses strobe-lit cameras to measure golf ball speed, launch angles, and 3-axis spin.

This is **not** a PiTrac port any more. The RPi→Jetson camera port is complete
(see "Porting status" below); from here PiTrac is a base to build on, not a
specification to match. Where PiTrac's design assumptions do not fit this
hardware, they get changed.

## Target hardware
- NVIDIA Jetson Xavier NX (JetPack 5.1.6, Ubuntu 20.04, CUDA 11.4, OpenCV 4.5.4)
- 2x Arducam B0332 OV9281 mono global shutter, **USB 2.0 UVC**, 70°(H) low-distortion
  M12 lens (≈2.7 mm, interchangeable but staying). 1280x800 @ 120 FPS MJPG measured.
- Cameras mounted **side by side, 80.00 mm baseline**, optical axes parallel at rest,
  each on a 3-point spring/screw kinematic mount so angles stay adjustable.
- 850nm IR LED array (Cenpek) + Teensy 4.0 strobe controller + IRLZ44N MOSFET,
  fired from Jetson Pin 29 (PQ.05)
- No LiDAR in v1 — camera-only trigger
- GSPro/OpenShotGolf running on separate Windows PC, Jetson sends shot JSON over TCP

## Porting status — done
The camera seam is `Software/LMSourceCode/ImageProcessing/v4l2_interface.h` / `.cpp`
(note: directly under `ImageProcessing/`, there is no `src/` subdirectory).
`libcamera_interface.h/.cpp` and `still_image_libcamera_app.hpp` are wrapped in
`#ifndef JETSON_BUILD` and are dead code on this platform. V4L2Capture does mmap
+ libjpeg-turbo decode and sustains 125-130 FPS. See PORTING_TASKS.md for the
per-function record.

Still open on the seam:
- `WaitForCam2Trigger` is a `// JETSON_STUB` returning false — the camera-2 capture
  path does not exist yet. PiTrac drives cam2 from a hardware external trigger
  (`imx296_trigger 4 1`); UVC cameras expose no such pin, so this needs a different
  mechanism, not a translation.
- `CameraHardware::sensor_width_`/`sensor_height_` are still the IMX296 values
  (5.077 x 3.789 mm) while capture is 1280x800 on a 3.84 x 2.40 mm OV9281. The
  aspect mismatch skews the vertical world-coordinate math. Fix pending measurement.

## What NOT to do
- Do not install or reference libcamera — it is RPi-only and does not exist on Jetson
- Do not install or reference LGPIO — it is RPi-only
- Do not write code until the approach has been agreed in plain language first
- Do not suggest hardware or libraries not listed here without asking first

## What you MAY change (updated 2026-08-06)
Ball detection, spin calculation, geometry/coordinate math and GSPro code are all
open for modification. The earlier "do not touch" rule existed to keep the RPi→Jetson
port honest; the port succeeded and dummy shots reach the simulator end to end, so
the rule has been retired. PiTrac's algorithms are a starting point to adapt, not a
contract.

Specifically in scope: PiTrac derives ball distance monocularly from apparent radius,
which suits its optics and not ours. The 80 mm stereo baseline makes triangulation
viable and roughly an order of magnitude more accurate at these distances.

## Build system
- Meson + Ninja
- Main build file: `Software/LMSourceCode/ImageProcessing/meson.build`
- Build command (on Jetson): `meson setup build_jetson --wipe && ninja -C build_jetson`
- PITRAC_ROOT = `Software/LMSourceCode`

## Key dependencies (all must work on JetPack 5.1.6 ARM64)
- OpenCV 4.5.4 with CUDA — already installed on Jetson
- Boost (log, thread, filesystem, system) — apt installable
- msgpack-c — apt installable  
- ActiveMQ-CPP 3.9.5 — must build from source
- Java OpenJDK + Maven — apt installable (for web GUI)
- V4L2 — built into Linux kernel, headers via libv4l-dev

## Known issues — do not try to fix these
1. Spin requires marked balls — accepted, non-negotiable
2. GSPro is Windows-only — Jetson sends data over TCP, not a bug
3. Issue #22: libgpiod chardev does not drive Pin 29 on the Seeed J202 carrier.
   `pulse_strobe_jetson.cpp` shells out to `fire_trigger.py` (Jetson.GPIO) instead.
   Accepted workaround, reliable, no fix planned.
4. Issue #19/#21: HoughCircles jitter during ball stabilization under ambient light.
   Resolved by design — the bypass in `gs_fsm.cpp` is permanent, not a stub.
   The IR array is event-driven, so stabilization frames are always ambient-lit.

## Current task
SP1 calibration. Cameras are mounted and the geometry is fixed; measuring the real
intrinsics (the 2.7 mm figure is derived from the 70° spec, not measured) before
touching any geometry or focal-length config. Checkerboard shots are taken as
simultaneous pairs so the same data also yields stereo extrinsics.
