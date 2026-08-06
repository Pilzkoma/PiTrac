# OV9281 Intrinsics + Stereo Extrinsics Calibration Design

**Date:** 2026-08-06
**Sub-project:** SP1 — Core Vision System
**Status:** Draft (pending user review)

## Problem

The cameras are mounted and the enclosure geometry is fixed, but every optical
constant the code uses still describes PiTrac's Raspberry Pi hardware rather
than ours. Three concrete instances:

**Sensor dimensions are wrong.** `CameraHardware::init_camera_parameters`
(`camera_hardware.cpp:249-250`) sets `sensor_width_ = 5.077365371` and
`sensor_height_ = 3.789078635` mm in the `PiGS || InnoMakerIMX296GS_Mono`
branch, which is the branch our cameras fall into
(`gs_camera.cpp:124-128`: `kSystemSlot1CameraType = PiGS`).
`PerformCameraSystemStartup` overrides the *resolution* to 1280×800
(`v4l2_interface.cpp:794-795`) but not the physical sensor size. The result is
an inconsistent aspect ratio:

| | width / height |
|---|---|
| Sensor as configured | 5.0774 / 3.7891 = 1.340 |
| IMX296 image 1456×1088 | 1.338 — consistent |
| Our image 1280×800 | 1.600 — inconsistent |
| OV9281 actual (3.0 µm square pixels) | 3.840 / 2.400 = 1.600 |

`gs_camera.cpp:929` and `:936` convert pixels to world coordinates using
`sensor_width_ / focal_length_` and `sensor_height_ / focal_length_`
respectively. A focal-length calibration absorbs an error in the absolute
sensor width, because the two appear as a product at `gs_camera.cpp:924`. It
does **not** absorb the aspect error. Vertical world coordinates — and
therefore launch angle — would be systematically off by roughly 19%, in a way
that is consistent enough to be easy to miss.

**Focal length is wrong.** `Lens_6mm` is configured, giving
`focal_length_ = 6.0f`. The Arducam B0332 ships a 70°(H) low-distortion M12
lens. From a 3.84 mm sensor width, `f = 1.92 / tan(35°) = 2.74 mm` — a factor
of 2.2 off. This figure is *derived from a manufacturer FOV spec, not
measured*, which is precisely why measuring it is the goal of this work.

**Expected ball radius is wrong.** `expected_ball_radius_pixels_at_40cm_ = 87`
is the IMX296 + 6 mm value. The config override is also ineffective: the code
reads `kExpectedBallRadiusPixelsAt40cmCamera1` / `...Camera2`, but
`golf_sim_config.json:124` only defines `kExpectedBallRadiusPixelsAt40cm`
without the camera suffix, so the lookup fails and the hardcoded default wins.
This value drives the Hough search radius.

**The two cameras are not distinguishable by identity.** Confirmed on hardware
2026-08-06 via `/sys/bus/usb/devices/*/serial`: both modules report
`0c45:6366` (Microdia bridge chip), `bcdDevice 1.00`, and `iSerial = UC762` —
Arducam's SKU code, written as a constant, not a per-unit serial.
`/dev/v4l/by-id/` consequently holds a single colliding entry.

`PerformCameraSystemStartup` hardcodes `/dev/video0` and `/dev/video2`
(`v4l2_interface.cpp:776-786`). Those numbers are assigned in enumeration
order. If the two swap across a reboot or replug, the stereo baseline changes
sign and depth comes out mirrored, with nothing visibly wrong in either image.

This has already happened once: the comment in that same block records the
cameras on `xhci-2.2.4` and `xhci-2.3`, while the hardware now enumerates them
on `2.3` and `2.4`. Calibration is precisely the work that bakes in an
assumption about which camera is which, so the binding has to be made stable
before, not after.

The one stable discriminator is the USB port path, exposed as
`/dev/v4l/by-path/platform-3610000.xhci-usb-0:2.3:1.0-video-index0` and
`...usb-0:2.4:1.0-video-index0`.

Separately, the tooling PiTrac ships for this job does not run here.
`Software/CalibrateCameraDistortions/take_calibration_shots.sh` is built on
`rpicam-still`; `CameraTools/previewGS.sh` on `libcamera-hello`. Neither exists
on Jetson. `CameraCalibration.py` is portable OpenCV but has `frameSize`
hardcoded to the IMX296's 1456×1088.

### Model validation

Before trusting any of the numbers above, the underlying model was checked
against PiTrac's own documented measurements. For the IMX296 at 5.077 mm /
1456 px = 3.487 µm per pixel with a 6 mm lens, `f_px = 1721`. A golf ball of
radius 21.335 mm at 0.550 m should image at `1721 × 21.335 / 550 = 66.8 px`.
`docs/camera/camera-calibration.md:104` logs `Radius: 67.741455` at exactly
that distance — a 1.4% match. The model is sound; the constants are not.

## Goal

Measure the true optical parameters of both cameras, and produce the data
needed to decide whether to triangulate.

1. Per-camera intrinsics: camera matrix and distortion vector, at the real
   1280×800 capture resolution.
2. True focal length in mm, derived as `fx × 3.0 µm` from measurement rather
   than from the manufacturer's FOV figure.
3. Stereo extrinsics: rotation and translation between the two cameras.
4. A reusable capture tool, since calibration will be repeated whenever the
   kinematic mounts are adjusted.

### Why stereo, and why now

The cameras sit side by side with an **80.00 mm baseline**, optical axes
parallel, at identical height and depth. These figures are read from
`Hardware/JetsonLM.step`: the two M12 lens barrels (r = 7.000 mm) have
placements at `(-4.00, -76.00, 87.00)` and `(76.00, -76.00, 87.00)`, both with
axis `(0, 1, 0)`.

That is a stereo rig. PiTrac's is not — it stacks its cameras 19 cm vertically
(`golf_sim_config.json:324-328`) and estimates depth monocularly from apparent
ball radius, `Z = f_px · r_ball / r_px`. That method's relative error is
`σ_r / r_px`, which is why PiTrac is sensitive to having many pixels on the
ball.

Triangulation depends instead on disparity, with
`σ_Z = Z² · σ_d / (f_px · B)`. At `f_px ≈ 913` and `B = 0.08 m`:

| Distance | Stereo (σ_d = 0.5 px) | Monocular radius (σ_r = 1 px) |
|---|---|---|
| 0.5 m | 1.7 mm | ~14 mm |
| 1.0 m | 6.8 mm | ~57 mm |
| 1.5 m | 15.4 mm | ~130 mm |

Roughly an order of magnitude, and it depends on the ball's *centroid* rather
than its *edge*. A centroid is sub-pixel recoverable even from a small blob;
a radius is exactly the quantity that degrades when the ball is small. Our
wide lens puts relatively few pixels on the ball, so this matters.

This spec does not implement triangulation. It produces the calibration data
without which triangulation is impossible, and it does so at no extra capture
cost — the same image pairs yield both per-camera intrinsics and stereo
extrinsics. The decision to build a triangulation path is deliberately
deferred until the measured numbers are in hand.

**The one irreversible choice here is capturing image pairs simultaneously.**
Sequential per-camera series can never yield stereo extrinsics; the shots
would have to be retaken from scratch. Paired capture costs nothing extra —
the `threading.Barrier` pattern in `sp1_vision/dual_camera_test.py:136-141`
already does it.

## Non-goals

- Triangulation in the ball-position path — separate sub-project, gated on
  these results.
- `WaitForCam2Trigger` and the camera-2 capture path — a design problem
  (UVC has no external trigger pin), not a calibration problem.
- Tape-measure geometry: camera positions relative to the tee, pan/tilt
  angles, `kCameraNPositionsFromOriginMeters`. These depend on where the unit
  is placed, which is an open design question.
- Focal-length calibration via `runCamNCalibration.sh`, and
  `expected_ball_radius`. Both become computable from `fx`, but belong with
  the geometry session.
- Working-distance recommendation. Depends on mount aiming; needs the measured
  `fx` and a look at the real setup first.
- Dual-process shakedown against ActiveMQ.

## Architecture

Calibration is not a one-off. Every adjustment to a camera mount invalidates
it, so the tool has to be genuinely easy to re-run — a button in the dashboard
that already runs on the Jetson, not a remembered command line. That drives
the structure: the capture logic is a **module**, with two front ends over it.

### `sp1_vision/calibration_capture.py` — the module

Device binding resolves through `/dev/v4l/by-path/`, never `/dev/videoN`, for
the identity reason above. The mapping from logical camera (1, 2) to USB port
path lives in one place and is the single thing to change if a cable moves.

Capture setup is lifted from `dual_camera_test.py`: `CAP_V4L2`, MJPG FOURCC
set before resolution, `BUFFERSIZE 1`, warm-up frames discarded. Exposure is
forced manual via `v4l2-ctl` so a series is consistently exposed.

Two operations:

- **Paired grab** — one frame from each camera behind a `threading.Barrier`,
  returned together. This is the primitive both front ends build on.
- **Sharpness** — Laplacian variance over a centre ROI, for focusing.

### Dashboard page — the primary front end

A calibration page added to `sp4_gspro/dashboard.py`, the Flask app already
running as `jetson-lm-dashboard.service` on port 5000. (The upstream PiTrac
FastAPI server under `Software/web-server/`, which ships its own
`calibration_manager.py`, is not running and is not the target — useful only
as a reference for how PiTrac models calibration state.)

Having a browser makes focusing strictly better than the headless design this
spec originally carried. Rather than reading a number in a terminal and
guessing, the page streams **live video** from each camera via
`multipart/x-mixed-replace` — the cameras already emit MJPEG, so the frames
pass through nearly untouched — with the sharpness score overlaid. Focusing an
M12 lens becomes looking at the picture, which is what it should have been.

The page offers: live view per camera, a capture button that takes one
checkerboard pair and immediately reports whether
`cv.findChessboardCorners` succeeded on each, a running count of good pairs,
and a run-calibration button that reports `fx`, `fy`, reprojection error, and
the stereo result.

Per-pair feedback matters more than it sounds: unusable shots surface while
the board is still in hand, instead of twenty shots later.

### CLI — the fallback

The same module exposed as `python3 -m sp1_vision.calibration_capture`, with
`--focus` and `--shots N --out DIR`. Keeps calibration possible when the
dashboard is down, and keeps the module testable without a browser in the
loop.

### `Software/CalibrateCameraDistortions/CameraCalibration.py` — patch

- `frameSize` 1456×1088 → 1280×800.
- Image directory and undistortion test image as CLI arguments, replacing the
  hardcoded `./images/cam1/*.png` and `./test_image_for_undistortion.png`.
- Per-image reprojection error in addition to the mean, so outlier shots can
  be identified and dropped.
- Emit results as a ready-to-paste JSON block in `golf_sim_config.json`'s
  format, rather than `.txt` files whose 3×3 matrix and 5-vector are
  transcribed by hand.
- Add a `stereoCalibrate` path over the image pairs, with the per-camera
  intrinsics as input, producing R and T.
- Fix a bug in the existing code: line 51 computes `corners2` via
  `cv.cornerSubPix`, and line 52 appends the unrefined `corners`. The
  sub-pixel refinement is calculated and discarded. This costs accuracy for
  nothing, and matters more here than upstream because sub-pixel precision is
  what makes the stereo result trustworthy.

### Sensor parameter override

Once `fx` and `fy` are measured, `focal_length_` and the sensor dimensions
follow as a consistent pair rather than two independent guesses. The mechanism
mirrors the one the port already uses for resolution: `sensor_width_override_`
and `sensor_height_override_` statics on `CameraHardware`, set in
`PerformCameraSystemStartup`. This keeps the change inside `v4l2_interface.cpp`
— the porting seam — instead of forking the camera model table or hiding
values under an `#ifdef` in the middle of a shared branch.

### Stable device binding

`PerformCameraSystemStartup` moves from hardcoded `/dev/video0` /
`/dev/video2` to the `by-path` symlinks, matching the Python module. The
existing `probe_v4l2_capture_device` VIDIOC_QUERYCAP check stays as-is and
still runs; only the path it is handed changes.

Failing loudly is the point. If an expected port path is absent, startup should
refuse rather than fall back to whatever `/dev/video0` happens to be — a silent
fallback here produces mirrored depth, which is worse than not starting.

## Phases

| Phase | Content | Output |
|---|---|---|
| 1a | `calibration_capture.py` module + CLI | Tooling, no C++ rebuild |
| 1b | Calibration page in `sp4_gspro/dashboard.py` (live view, capture, run) | Clickable from port 5000 |
| 1c | Patch `CameraCalibration.py`: resolution, CLI args, per-image error, JSON output, `stereoCalibrate`, `cornerSubPix` fix | Analysis step |
| 2 | Focus both lenses; capture ~20 simultaneous checkerboard pairs | `images/cam1/`, `images/cam2/` |
| 3 | Run calibration; evaluate against acceptance criteria | `fx`, `fy`, distortion, R, T, reprojection error |
| 4 | Write results into `golf_sim_config.json`; sensor override and `by-path` binding in `v4l2_interface.cpp` | Config + C++ change, needs rebuild |

Phase 1a and 1c are independent of each other and of the hardware; 1b depends
on 1a. Phase 2 is the only step that needs the user physically present with a
checkerboard.

Checkerboard is `Software/CalibrateCameraDistortions/checkerboard.png`, 9×6
inner corners. Print scale is irrelevant to the intrinsics — square size only
scales the translation vectors, not the camera matrix — but the squares must
stay square, so printing must not be aspect-scaled to fit the page. Board
should be held at roughly working distance, reaching the image corners as well
as the centre, ordinary room light.

## Acceptance criteria

1. Both cameras calibrate with mean reprojection error **≤ 0.5 px**. Above
   that, retake rather than proceed.
2. `fx ≈ fy` within ~1%. A larger gap falsifies the 3.0 µm square-pixel
   assumption and the sensor arithmetic has to be revisited before anything is
   written to config.
3. `fx × 3.0 µm` is reported alongside the 2.74 mm derived figure. Agreement
   confirms the model; disagreement means the measurement wins.
4. `stereoCalibrate` translation magnitude is compared against the STEP's
   80.00 mm, and the rotation against the STEP's parallel axes. This is an
   independent check on both the calibration and the physical mount.

   R is reported decomposed into roll / pitch / yaw in degrees, because the
   three are not equally costly. Yaw (toe-in/out) feeds horizontal disparity
   and is absorbed as an offset. Pitch and roll produce *vertical* disparity,
   which is what makes correspondence search two-dimensional. `stereoRectify`
   removes all of it; the only cost is edge crop, at roughly
   `f_px × tan(angle)` pixels of vertical shift — about 2% of frame height per
   degree. Under 2-3° needs no action. Beyond ~5°, shimming the offending
   camera is worth it before accepting the calibration.

   A discrepancy is a finding, not a failure.
5. Undistortion is verified visually: straight edges are straight in the
   rectified image.

## Risks

- **Focus and depth of field.** At ~2.7 mm the depth of field is deep, which
  makes focus forgiving but also makes the Laplacian score flat and harder to
  peak precisely. If the score does not discriminate, fall back to inspecting
  a saved frame.
- **Board detection at 1280×800 mono.** Untested on these cameras. Phase 2's
  per-shot feedback is what surfaces this immediately rather than at the end.
- **Both cameras on USB 2.0.** Simultaneous single-frame grabs are far below
  the throughput already sustained at 120 FPS on both cameras in parallel, so
  no issue is expected — but paired capture is new and worth confirming.
- **`fx` may not match the derived 2.74 mm.** That is the point of measuring.
  Every downstream number in this spec that depends on `f_px = 913` —
  including the stereo error table — is provisional until Phase 3.
- **`golf_sim_config.json` on the Jetson carries an uncommitted diff**, and
  Phase 4 writes to that same file. The diff is deliberate: it is the Phase C
  bench configuration, `kBaudRateForFastPulses` 115200→1000 and
  `number_bits_for_fast_on_pulse_` 2→32, which stretches the strobe to 32 ms
  pulses so the LED is visible to the eye. Production is 17 µs. Phase 4 must
  not sweep those values into a commit as though they were calibration
  results, and the strobe must be returned to production values before the
  first real shot.
