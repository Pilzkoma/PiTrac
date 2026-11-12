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
  M12 lens (**calibrated 2.751 / 2.756 mm**, interchangeable but staying, focus adjustable
  by screwing the lens). 1280x800 @ 120 FPS MJPG measured. The cameras USB-autosuspend
  when idle (`control=auto`, 2 s) and the dashboard hands the V4L2 nodes back after
  120 s idle — they are not powered up between uses.
- Cameras mounted **side by side, calibrated baseline 80.47 mm** (CAD says 80.00),
  optical axes parallel to within pitch −0.44°, yaw +0.58°, roll +0.28°
  (2026-11-10, see Calibration). The camera plate is bolted solid (springs removed
  2026-08-08); the individual cameras can still be turned on their screws, which the
  owner did when moving to the reprinted enclosure. Any re-aim invalidates the
  stereo extrinsics and drags a full recalibration with it. All three angles are far
  under the 3° where rectification starts costing frame height.
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
1. ~~Spin requires marked balls~~ — **corrected 2026-11-12, the old assumption was
   never PiTrac's.** PiTrac's spin (`GetBallRotation`, `ball_image_proc.cpp` ~2871)
   reads the **dimples**: Gabor filters in 32 directions, threshold regulated to
   38–45 % white, then a 3D rotation search matching image 1 onto image 2. Marks
   *disturb* it (code comment at 2969–2971; the author on Hackaday: spin "without
   requiring any registration marks"). Open: whether our optics resolve the
   dimples (~7–9 px per dimple at 40–50 cm, ball radius 39–48 px) and how short
   the flash must be (100 µs smears 3 mm at 30 m/s, about one dimple). Marks only
   if the dimples fail - then as our own method, in IR-dark ink (many felt-pen
   inks are transparent at 850 nm). Foam balls have no dimples.
2. GSPro is Windows-only — Jetson sends data over TCP, not a bug
3. Issue #22: libgpiod chardev does not drive Pin 29 on the Seeed J202 carrier.
   `pulse_strobe_jetson.cpp` shells out to `fire_trigger.py` (Jetson.GPIO) instead.
   Accepted workaround, reliable, no fix planned.
4. Issue #19/#21: HoughCircles jitter during ball stabilization under ambient light.
   Resolved by design — the bypass in `gs_fsm.cpp` is permanent, not a stub.
   The IR array is event-driven, so stabilization frames are always ambient-lit.

## Calibration — 2026-11-10, reprinted enclosure
The camera plate moved as one piece into a reprinted enclosure and the owner
re-aimed the individual cameras on their screws, so the pair was recalibrated.
Both intrinsics and extrinsics come from **one** 32-pair set in
`sp1_vision/calibration_images/cam1|cam2` (board glued flat on a rigid plate,
28–100 cm, leans to ~60°, all thirds of the frame covered), solved with
`--square-mm 24.27` straight from the tools, no hand correction:
- Intrinsics in `golf_sim_config.json`: fx 916.85 / 918.70, fy 912.07 / 915.19,
  cx 638.3 / 641.2, cy 386.6 / 389.7 (2.751 / 2.756 mm, sensor 3.840 x 2.400 mm),
  RMS 0.60 / 0.58 px on 29 / 28 images.
- Extrinsics in `sp1_vision/calibration_results/stereo_extrinsics.json`: baseline
  80.47 mm, pitch −0.442°, yaw +0.577°, roll +0.278°, stereo RMS 0.81 px on 31 pairs.
- Not yet verified reaching the C++ in a trace run.

How far to trust it, by the test that matters: each half/odd/even subset
re-solved end to end (both intrinsics + stereo) moves triangulated board
positions by a median 1–5 mm (≤1 % of depth) against the full set; one weak
half (the frontal sweep and tilts only) moves 11 mm. The 2026-08-08 set, put
through the same test, moves 10–12 mm. **Individual parameters still wander
across subsets** (fx 913–934, cy 367–414, pitch −0.65…+0.06°) — they trade off
against each other while the geometry they produce stays put. The old set
wandered as much (fx 895–935, pitch −0.26…−1.08°); its documented "stable"
spreads were measured with the intrinsics held fixed, which hides exactly this.

**The board must be flat.** A first attempt the same day (32 pairs, archived in
`2026-11-10_bent_board/`, do not solve against it) had the print clipped onto a
backing that bowed ~3 mm across its width when leaned back. It drove fx to 951,
which is physically impossible for a lens focused sharp at 50 cm (refocusing
30 cm↔∞ moves the image distance under 1 %). Test: a flat board fits an exact
homography in the image centre where distortion is negligible; the bowed shots
left 1.8–2.3 px against 0.2 px for good ones, identical in both cameras.

The previous set (2026-08-08, fx ≈ 900, baseline 79.64 mm after the 24.27 mm
square correction of 2026-09-24) is in `2026-08-08_bolted/` as a record.

Rules that cost sessions to learn:
- **Intrinsics and extrinsics must come from the same solve.** `CALIB_FIX_INTRINSIC`
  makes the stereo step absorb whatever error the camera matrices carry into R and T,
  so the pair is only self-consistent together. Mixing sources is the one combination
  that is definitely wrong and it looks fine in the reprojection error.
- **A low RMS does not mean the answer is determined.** Two intrinsic sets gave pitch
  −0.745° and −1.834° at an identical RMS of 0.90, because `cy` was unconstrained.
  To test whether a number is real, re-solve on subsets and against a second
  intrinsics source — not by reading the residual. Re-solve the **whole chain**
  per subset and compare triangulated positions; comparing single parameters
  with the intrinsics held fixed overstates the stability.

`2026-08-06_springs/` is a superseded archive, kept as the record of the pre-rebuild
geometry. It is worse on every figure. Do not solve against it.
The operating detail is in `sp1_vision/calibration_images/README.md`.

## Capture: the driver holds a frame back
After a pause, the first read from these UVC cameras returns the frame taken just
after the *previous* read — `CAP_PROP_BUFFERSIZE 1` does not prevent it. Until
`35ca2db` (2026-09-23) this put every measurement shot one position late, and two
past "operator errors" were this defect. `CameraPair.grab_with_skew` now discards
`STALE_FRAMES` by default; only a caller reading back to back (the MJPEG stream)
may pass `fresh=False`. Any new capture path that reads on demand must keep the
default. Test for staleness by changing exposure between grabs, not by comparing
frames of a static scene.

## Current task
Done since 2026-09-24: the strobe circuit is soldered on the perfboard in the
finished enclosure (bypass test passed 2026-11, both arrays fire); the Jetson
runs on WiFi at 192.168.178.43; the dashboard was rebuilt in the Golfinator
look with a power-off button (Golfinator asks on quit); the pair was
recalibrated (see Calibration).

**Attitude against the floor, reprinted enclosure (2026-11-11, strobe-lit
triangulation, `sp1_vision/strobe_runs/2026-11-11_triangulation/`):** pitch
**+1.60°** (nose up), roll +0.36°, camera 1 **111.9 mm** above the floor; scale
against the tape 1.0003 ± 0.0067, residual 1.6 mm over 300–700 mm. Capture a
position with `python3 -m sp1_vision.strobe_pair --out RUNDIR --tape MM
--series d|s|t`, analyse with `cli_triangulate --analyse RUNDIR`. The
ambient-lit runs (up to run 6, old enclosure: pitch −1.55°, 117.5 mm) are
closed and superseded. If a static run is ever needed again: contrast check first
(`contrast_check.py` in the gitignored `.superpowers/sdd/...block1/`), and on a
surround brighter than ~90 grey levels analyse with `--refiner contrast`; never
mix refiners within a run. Results: `sp1_vision/triangulation_run/README.md`.

Next SP1 items, in this order:
1. **Strobe-lit captures** — first run done 2026-11-10, see
   `sp1_vision/strobe_runs/README.md` (tool: `sp1_vision/strobe_capture.py`).
   The flash puts ~50–100× more light on the ball than room lamps; at 1 ms
   exposure the room is black and the ball white. Fire → frame arrival 11–20 ms.
   8 ms exposure catches every flash; short exposures only by chance, and **the
   two cameras are not in phase**, so a short exposure often shows the flash in
   one camera only. 2026-11-11, photocells removed and trigger line
   re-soldered: 12/12 flashes arrive, both cameras see the ball within 1–2 %,
   0.1 ms already puts it mid-range and 0.3 ms clips. Two camera traps
   (details in the strobe README): the module's image processor once **stuck
   cam2 with a dark patch** over the image centre until an auto-exposure pass
   reset it, and the output follows a **compressive tone curve**, so the same
   flash adds fewer grey levels on a brighter background (all lamps on: +72
   instead of +120). `strobe_capture.py` therefore settles on auto exposure
   before going manual and measures at **gamma 72** (the straightest curve
   offered; `pitrac_lm` still runs at the default 100). The 2026-11-10
   calibration reaches the C++ (trace 2026-11-11: matrix 916.85…, focal
   2.751 mm). Still open: garage daylight.
2. **World geometry.** Three live constants still hold PiTrac's numbers, and they are
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
     camera stacking. Ours sit side by side at 80.47 mm, so until this is changed the
     delta path carries a 19 cm offset that does not exist. Note the axis permutation
     at 701-703: `position_deltas_ball_perspective_` takes offset `[2],[1],[0]`.
3. **Triangulation.** Nothing consumes the extrinsics yet; the ball-position path is
   still PiTrac's monocular radius method. At 50 cm the stereo pair resolves 3.49 mm
   of depth per pixel of disparity error (~1.8 mm at half-pixel matching), which is
   the largest accuracy gain available.
4. `WaitForCam2Trigger`, still a `JETSON_STUB` returning false. **Mechanism
   decided and proven on putts (2026-11-12):** reacting to a hit is impossible
   (frames arrive 11-20 ms late, the trigger helper costs 100-200 ms), so the
   Teensy strobes continuously while armed (`RUN`/`STOP`, new firmware), both
   cameras expose ~8 ms of every frame into a ring buffer, and the shot is
   found afterwards: rest ball → impact → reference just before → ball in the
   positive difference → stereo → robust constant-velocity fit. Offline tools
   `sp1_vision/strobe_shot.py` (record) and `strobe_event.py` (find, measure);
   three putts at 1.06-1.39 m/s, rms 7-9 mm (`sp1_vision/strobe_runs/README.md`).
   **Drivers are in scope for v1, and the approach carries them:** with the
   strobe on, the FLASH is the shutter - a ball image's instant is its flash,
   the same for both cameras whatever their frame phase - so stereo pairs
   ball image to ball image by flash, not frame to frame (the 4 ms frame
   offset only limits today's whole-frame pairing), and time resolution is
   the flash rate, not 120 fps. Next session, in this order: (a) short-pulse
   brightness on a static ball, 20/30/50 µs - at 75 m/s a 0.1 ms flash
   smears 7.5 mm, the dimples (what the spin reads, see Known issues 1) need ~25 µs, which gives ~+30 grey levels where
   0.1 ms gave +115; the biggest v1 risk, 15 minutes to settle; (b) chips, to
   build the per-flash matching of several ball images per frame (same image
   row in both cameras, order along the path, an irregular flash pattern);
   (c) full swings - **not possible indoors for now** (no garage for a while,
   nothing to catch the ball): short chips only, plus throws across the view
   onto a blanket (~10-15 m/s); spread the flash interval (e.g. 4 ms) to make
   a chip's images as far apart as a fast ball's. Full swings once there is a
   garage or a net/blanket to hit into; then the live version in `pitrac_lm`
   watching a window round the rest ball. One pattern must serve putts (images overlap at 1 ms)
   and drives (7.5 cm apart): mixed intervals or a fast/slow switch as
   PiTrac has. The
   power LED blinks fast while recording (`sp4_gspro/jetsonlm-led`); slow
   blink for "ball ready" comes with the live version.

   **v2 idea (owner, 2026-11-11):** MIPI-CSI global-shutter cameras with a
   hardware trigger input would sync both cameras exactly and allow an
   exposure as short as the flash (ambient down ~80×, the fix for garage
   daylight). Needs cameras with a Jetson driver that supports the trigger
   (the Pi IMX296 has none) and a check of the J202 carrier's CSI ports.

   **The B0332s have that trigger already (2026-11-12, LOGBOOK).** Pad F on
   the UC-844 board (3.3 V input, ~3 kΩ pull-up; S is dead, L/R are empty
   mic pads) is wired to Teensy pin 4 (cam1, dashboard left) and pin 5
   (cam2), G to GND. UVC `exposure_auto_priority=1` = trigger mode: one
   frame per rising edge, **exposure starts ≈ 0.78 ms after the edge, both
   cameras within 25 µs, jitter < 25 µs, no held-back frame** (measured with
   `sp1_vision/trigger_sweep.py`, firmware v0.2 `TRIG_ARM` / `SHOT`). The
   flash can now be placed inside a known exposure in both cameras at once.
   Pins 4/5 are inputs unless armed, so free-running use is unchanged. MIPI
   cameras drop down the list.

   **Continuous trigger works (same night).** Firmware v0.3 `TRIG_RUN,period_us,
   delay_us,pulse_us[,max_ms]` (stop with `STOP`); `trigger_rate.py`: both
   cameras follow **every edge at 100 fps**, at 105 fps and above exactly
   every other one - so 10 ms is the period. `strobe_shot --trigger`: 0.5 ms
   exposure (room nearly black), edge every 10 ms, 100 µs flash 0.9 ms after
   it. Chips recorded that way: 4512 edges, 4512 frames per camera, and the
   contact sheet shows **one round sharp ball per frame, the ball's print
   visibly rotating** (free-running at 4 ms the chip was an elongated double
   image). **Next session, in this order:** (1) make `strobe_event` read
   triggered recordings - its rest search (tuned to 8 ms frames) found the
   dimmer rest ball at only 4 of ~180 moments (2 of 3 chips), and its flight
   search ran 34 min on chip 1 without output and was stopped (unexamined;
   guess: noise in ball-free positive images scaled up into masses of
   circles); options: bound the search to a window round the expected path,
   a longer flash (200-300 µs costs little blur at chip speed) for a
   brighter rest ball, frame times from the trigger index (10 ms exact)
   instead of arrival. Recording `/home/brain/strobe_raw/2026-11-12_chips_trigger`.
   (2) the short-pulse test (a) above; (3) several flashes per frame for
   fast balls (PiTrac's multi-exposure, now in both cameras at once).

Known small defect, not yet fixed: `cli_calibrate.py --focus` measures the frame
centre (`sharpness_score`) instead of the detected board (`board_sharpness`), unlike
the dashboard. That is the readout that once hid a 5.4x focus error.

To run `pitrac_lm` at all you must pass `--msg_broker_address=tcp://127.0.0.1:61616`
— `kWebActiveMQHostAddress` is absent from the config, and without it the run aborts
in IPC init and segfaults on shutdown.
