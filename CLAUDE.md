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
  M12 lens (**measured 2.701 / 2.700 mm**, interchangeable but staying, focus adjustable
  by screwing the lens). 1280x800 @ 120 FPS MJPG measured. The cameras USB-autosuspend
  when idle (`control=auto`, 2 s) and the dashboard hands the V4L2 nodes back after
  120 s idle — they are not powered up between uses.
- Cameras mounted **side by side, measured baseline 78.28 mm** (CAD says 80.00; the
  −2.1 % is print shrinkage), optical axes parallel to within pitch −0.92°, yaw +0.43°,
  roll −0.85°. **The mount is no longer adjustable:** the 3-point spring/screw kinematic
  mount was stripped of its springs on 2026-08-08 and the plate bolted down solid. That
  rebuild *inverted* pitch and roll rather than nulling them, and only improved yaw;
  all three are far under the 3° where rectification starts costing frame height, so
  they stay as they are. Changing the aim is now a rework, not a turn of a screw —
  and it invalidates the stereo extrinsics, so it drags a recalibration with it.
- The unit sits on the floor. The lower image corners cannot be reached with a
  calibration board and are not worth reaching; see
  `sp1_vision/calibration_images/README.md`.
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

## Calibration — done, 2026-08-09. Do not redo it.
Both intrinsics and extrinsics come from **one** 24-pair set in
`sp1_vision/calibration_images/cam1|cam2`, captured after the mount rebuild.
Intrinsics are in `golf_sim_config.json` (2.701 / 2.700 mm, fx 900.38 / 899.99,
cy 420.05 / 421.09, sensor 3.840 x 2.400 mm), extrinsics in
`sp1_vision/calibration_results/stereo_extrinsics.json`. Verified reaching the
C++ in a live trace run.

Two rules that cost a session to learn:
- **Intrinsics and extrinsics must come from the same solve.** `CALIB_FIX_INTRINSIC`
  makes the stereo step absorb whatever error the camera matrices carry into R and T,
  so the pair is only self-consistent together. Mixing sources is the one combination
  that is definitely wrong and it looks fine in the reprojection error.
- **A low RMS does not mean the answer is determined.** Two intrinsic sets gave pitch
  −0.745° and −1.834° at an identical RMS of 0.90, because `cy` was unconstrained.
  To test whether a number is real, re-solve on subsets and against a second
  intrinsics source — not by reading the residual.

`2026-08-06_springs/` is a superseded archive, kept as the record of the pre-rebuild
geometry. It is worse on every figure. Do not solve against it.
The operating detail is in `sp1_vision/calibration_images/README.md`.

## Current task
Next SP1 items, in this order:
1. **World geometry.** Three live constants still hold PiTrac's numbers, and they are
   not equally important:
   - `kCameraNPositionsFromExpectedBallMeters` (cam1 `[-0.200, -0.234, 0.54]`, cam2
     `[0.0, -0.051, 0.45]`). **Note the name** — `kCameraNPositionsFromOriginMeters`
     appears only in PiTrac's `docs/camera/camera-calibration.md` and does not exist
     in this code. The origin is the *expected ball*, not a point on the floor. Only
     the **magnitude** is ever read, at `gs_camera.cpp:455/458` via
     `CvUtils::GetDistance`, as the expected ball distance for the search radius;
     direction and sign go nowhere. Confirmed at runtime: the trace prints
     `distance: 0.621575`, which is exactly the length of cam1's vector. At a 50 cm
     working distance this is currently 24 % too far.
   - `kCameraNAngles` (cam1 `[18.72, -24.18]`, cam2 `[-2.06, 3.83]`), pan/tilt against
     a level bore per `docs/camera/camera-calibration.md:170-173`. These feed
     `camera_angles_` into `AdjustXYZDistancesForCameraAngles` and become HLA and VLA,
     so they are the ones that actually matter.
   - `kCamera2OffsetFromCamera1OriginMeters` = `[0.00, -0.19, 0.0]`, added at
     `gs_camera.cpp:700-703` and `lm_main.cpp:865`. This is PiTrac's **vertical** 19 cm
     camera stacking. Ours sit side by side at 78.28 mm, so until this is changed the
     delta path carries a 19 cm offset that does not exist. Note the axis permutation
     at 701-703: `position_deltas_ball_perspective_` takes offset `[2],[1],[0]`.
2. **Triangulation.** Nothing consumes the extrinsics yet; the ball-position path is
   still PiTrac's monocular radius method. At 50 cm the stereo pair resolves 3.55 mm
   of depth per pixel of disparity error (~1.8 mm at half-pixel matching), which is
   the largest accuracy gain available.
3. `WaitForCam2Trigger`, still a `JETSON_STUB` returning false.

Known small defect, not yet fixed: `cli_calibrate.py --focus` measures the frame
centre (`sharpness_score`) instead of the detected board (`board_sharpness`), unlike
the dashboard. That is the readout that once hid a 5.4x focus error.

To run `pitrac_lm` at all you must pass `--msg_broker_address=tcp://127.0.0.1:61616`
— `kWebActiveMQHostAddress` is absent from the config, and without it the run aborts
in IPC init and segfaults on shutdown.
